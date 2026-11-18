"""Conflicts and claim checks on a small corpus with planted conflicts (eval/conflicts), read by the real model.

  python3 -m eval.run_conflict_eval build /path/to/c.db
  python3 -m eval.run_conflict_eval detect /path/to/c.db [--llm] [--json out.json]
  python3 -m eval.run_conflict_eval claims /path/to/c.db [--questions claims_heldout.json] [--json out.json]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from eval import run_qa_eval as qa  # noqa: E402
from src.core import database  # noqa: E402
from src.core.config import Settings  # noqa: E402

DIR = ROOT / "eval" / "conflicts"
qa.QA = DIR


def texts(db, c):
    from src.models.graph import Fact

    def t(fid):
        f = db.get(Fact, fid)
        return f"{f.subject.name} {f.predicate} {f.object.name if f.object else f.object_value} ({f.valid_from}..{f.valid_to})"
    return t(c.fact_a_id), t(c.fact_b_id)


def has(words, a, b, must=None):
    both = a + " | " + b
    return all(w in both for w in words) and (must is None or must in both)


def detect(db_path: str, use_llm: bool, out: str | None):
    from src.models.conflict import Conflict
    from src.services import conflicts as cf
    from src.services.llm import get_llm
    qa.attach(db_path)
    s = Settings(_env_file=None)
    llm = get_llm(s) if use_llm else None
    with database.SessionLocal() as db:
        # start from nothing: the pipeline may already have found some while reading
        for c in db.execute(select(Conflict)).scalars():
            db.delete(c)
        db.commit()
        summary = cf.run_detection(db, owner_id=None, llm=llm, judge=use_llm)
        db.commit()
        found = [(c, *texts(db, c)) for c in db.execute(select(Conflict)).scalars()]
        gold = json.loads((DIR / "gold.json").read_text())
        report = {"summary": summary.as_dict(), "expected": {}, "lookalikes": {}, "unexpected": []}
        matched = set()
        for e in gold["expected"]:
            hit = [(c, a, b) for c, a, b in found if has(e["words"], a, b, e.get("must_contain"))]
            report["expected"][e["id"]] = {"found": bool(hit), "kind": hit[0][0].kind if hit else None, "severity": hit[0][0].severity if hit else None,
                                           "kind_ok": bool(hit) and hit[0][0].kind == e["kind"], "llm": hit[0][0].llm_verdict if hit else None}
            matched.update(c.id for c, *_ in hit)
        for l in gold["lookalikes"]:
            hit = [(c, a, b) for c, a, b in found if has(l["words"], a, b, l.get("must_contain"))]
            report["lookalikes"][l["id"]] = {"flagged": bool(hit), "what": l["what"]}
            matched.update(c.id for c, *_ in hit)
        report["unexpected"] = [{"kind": c.kind, "severity": c.severity, "a": a, "b": b} for c, a, b in found if c.id not in matched]
        report["all"] = [{"kind": c.kind, "severity": c.severity, "a": a, "b": b, "llm": c.llm_verdict} for c, a, b in found]
    print(json.dumps(report, indent=1))
    ex = report["expected"]
    print(f"\nexpected found: {sum(v['found'] for v in ex.values())}/{len(ex)}   right kind: {sum(v['kind_ok'] for v in ex.values())}/{len(ex)}   "
          f"look-alikes wrongly flagged: {sum(v['flagged'] for v in report['lookalikes'].values())}/{len(report['lookalikes'])}   unexpected: {len(report['unexpected'])}")
    if out:
        Path(out).write_text(json.dumps(report, indent=1))


def claims(db_path: str, qfile: str, out: str | None):
    import time
    from src.services import factcheck
    from src.services.embedding import get_embedder
    from src.services.llm import get_llm
    qa.attach(db_path)
    s = Settings(_env_file=None)
    llm, emb = get_llm(s), get_embedder(s)
    rows, ok = [], 0
    for c in json.loads((DIR / qfile).read_text())["claims"]:
        t0 = time.time()
        with database.SessionLocal() as db:
            r = factcheck.check(db, c["claim"], llm=llm, embedder=emb, settings=s)
            db.commit()
        good = r["verdict"] == c["gold"]
        ok += good
        rows.append({"id": c["id"], "claim": c["claim"], "gold": c["gold"], "verdict": r["verdict"], "ok": good, "summary": r["summary"], "parsed": r["parsed"], "seconds": round(time.time() - t0, 1)})
        print(f"{c['id']} {'OK ' if good else 'BAD'} {r['verdict']:22s} (gold {c['gold']}) {r['summary'][:90]!r}  parsed={r['parsed']}", flush=True)
    print(f"\n{ok}/{len(rows)} verdicts as expected")
    if out:
        Path(out).write_text(json.dumps({"correct": ok, "total": len(rows), "results": rows}, indent=1))


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    path = args[0]
    get = lambda flag: args[args.index(flag) + 1] if flag in args else None  # noqa: E731
    if cmd == "build":
        qa.build(path)
    elif cmd == "detect":
        detect(path, "--llm" in args, get("--json"))
    elif cmd == "claims":
        claims(path, get("--questions") or "claims.json", get("--json"))
