"""Graph questions against passage search on a multi-document corpus (eval/qa).

  python3 -m eval.run_qa_eval build /path/to/qa.db             # read the 18 documents with the real model (a few minutes)
  python3 -m eval.run_qa_eval run /path/to/qa.db vector graph hybrid --json eval/qa/results.json
"""
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.core import database  # noqa: E402
from src.core.config import Settings  # noqa: E402

QA = ROOT / "eval" / "qa"


def attach(db_path: str, fresh: bool = False):
    p = Path(db_path)
    if fresh:
        for f in p.parent.glob(p.name + "*"):
            f.unlink()
    engine = database.make_engine(f"sqlite:///{p}")
    from src import models  # noqa: F401
    database.Base.metadata.create_all(bind=engine)
    database.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return engine


def build(db_path: str):
    from src.models.graph import Document, Entity, Fact
    from src.services import pipeline
    from src.services.readers import clean_text
    attach(db_path, fresh=True)
    s = Settings(_env_file=None)
    for f in sorted((QA / "docs").glob("*.txt")):
        t = clean_text(f.read_text())
        with database.SessionLocal() as db:
            d = Document(title=f.stem, text=t, char_count=len(t))
            db.add(d)
            db.commit()
            did = d.id
        t0 = time.time()
        pipeline.process_document(did, None, s)
        with database.SessionLocal() as db:
            d = db.get(Document, did)
            print(f"{f.stem} {d.status.value} {time.time() - t0:.0f}s accepted={d.stats.get('accepted')} {d.error or ''}", flush=True)
    with database.SessionLocal() as db:
        print("entities", db.scalar(select(func.count()).select_from(Entity)), "facts", db.scalar(select(func.count()).select_from(Fact)))
        for fct in db.execute(select(Fact)).scalars():
            print("  ", fct.subject.name, "|", fct.predicate, "|", fct.object.name if fct.object else fct.object_value, "|", fct.valid_from, fct.valid_to)


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text).replace("  ", " ").strip()


NOT_FOUND = ("not found", "no information", "not mentioned", "cannot be determined", "does not say", "unknown")


def judge(q: dict, result: dict) -> dict:
    ans = norm(result["answer"] + " " + result.get("time_caveat", ""))
    if q["kind"] == "undated":  # the text gives no date: refusing is right, so is the name with the caveat that nothing dates it
        ok = (not result["found"]) or (all(norm(g) in ans for g in q["gold"]) and bool(re.search(r"undated|no date|not stated|does not (say|state)|no end|unknown when", ans)))
    elif not q["gold"]:  # must refuse
        ok = (not result["found"]) or any(p in ans for p in NOT_FOUND)
    else:
        ok = result["found"] and all(norm(g) in ans for g in q["gold"])
    cited_docs = {c.get("document_title") for c in result["citations"] if c.get("document_title")}
    evidence = set(result["reasoning"].get("evidence_documents", []))
    support = set(q["support"])
    return {"correct": ok, "retrieved_all_support": support <= evidence if support else None,
            "cited_all_support": support <= cited_docs if support else None, "uncited": result["found"] and not result["citations"]}


def run(db_path: str, modes: list[str], out: str | None, only: list[str] | None = None, qfile: str = "questions.json"):
    from src.services import ask as ask_service
    from src.services.embedding import get_embedder
    from src.services.llm import get_llm
    attach(db_path)
    s = Settings(_env_file=None)
    llm, emb = get_llm(s), get_embedder(s)
    questions = json.loads((QA / qfile).read_text())["questions"]
    results = []
    for q in questions:
        if only and q["id"] not in only:
            continue
        row = {"id": q["id"], "hops": q["hops"], "kind": q["kind"], "question": q["question"], "gold": q["gold"]}
        for mode in modes:
            t0 = time.time()
            with database.SessionLocal() as db:
                try:
                    res = ask_service.ask(db, q["question"], mode=mode, llm=llm, embedder=emb, settings=s)
                    db.commit()
                except Exception as exc:  # keep going; the failure is part of the result
                    res = {"found": False, "answer": f"ERROR {type(exc).__name__}: {exc}", "citations": [], "reasoning": {}}
            j = judge(q, res)
            row[mode] = {"answer": res["answer"], "found": res["found"], **j, "seconds": round(time.time() - t0, 1),
                         "fallback": res["reasoning"].get("fallback"), "plan": res["reasoning"].get("plan"),
                         "evidence_documents": res["reasoning"].get("evidence_documents")}
            print(f"{q['id']} {mode:9s} {'OK ' if j['correct'] else 'BAD'} {row[mode]['seconds']:5.1f}s  {res['answer'][:90]!r}"
                  + (f"  [fallback: {row[mode]['fallback']}]" if row[mode]["fallback"] else ""), flush=True)
        results.append(row)
    summary = summarise(results, modes)
    print("\n" + json.dumps(summary, indent=1))
    if out:
        Path(out).write_text(json.dumps({"modes": modes, "summary": summary, "results": results}, indent=1))


def summarise(results, modes):
    out = {}
    groups = {"all": lambda r: True, "1 hop": lambda r: r["kind"] in ("lookup", "list") and r["hops"] == 1,
              "2 hops": lambda r: r["hops"] == 2 and r["kind"] != "path", "3+ hops": lambda r: r["hops"] >= 3,
              "path": lambda r: r["kind"] == "path", "answerable": lambda r: r["kind"] != "unanswerable",
              "unanswerable": lambda r: r["kind"] == "unanswerable"}
    for mode in modes:
        out[mode] = {}
        for g, f in groups.items():
            rs = [r for r in results if f(r) and mode in r]
            if rs:
                out[mode][g] = f"{sum(r[mode]['correct'] for r in rs)}/{len(rs)}"
        ans = [r for r in results if r["kind"] != "unanswerable" and mode in r]
        if ans:
            out[mode]["support documents retrieved"] = f"{sum(bool(r[mode]['retrieved_all_support']) for r in ans)}/{len(ans)}"
            out[mode]["avg seconds"] = round(sum(r[mode]["seconds"] for r in results if mode in r) / sum(1 for r in results if mode in r), 1)
    return out


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "build":
        build(sys.argv[2])
    elif cmd == "run":
        args = sys.argv[3:]
        out = args[args.index("--json") + 1] if "--json" in args else None
        only = args[args.index("--only") + 1].split(",") if "--only" in args else None
        qfile = args[args.index("--questions") + 1] if "--questions" in args else "questions.json"
        modes = [a for a in args if a in ("vector", "subgraph", "graph", "hybrid")]
        run(sys.argv[2], modes, out, only, qfile)
