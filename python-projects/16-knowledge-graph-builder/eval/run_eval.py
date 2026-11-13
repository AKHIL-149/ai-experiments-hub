"""Run the extractor on the labelled documents and print precision / recall.

  python3 -m eval.run_eval --model llama3.1:8b --verify
  python3 -m eval.run_eval --model llama3.1:8b --no-verify --json eval/results_noverify.json
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.scoring import combine, score_document  # noqa: E402
from src.core.config import get_settings  # noqa: E402
from src.services.chunker import chunk_text  # noqa: E402
from src.services.extraction import extract_chunk  # noqa: E402
from src.services.llm import OllamaClient  # noqa: E402
from src.services.readers import clean_text  # noqa: E402


def run(model: str, verify: bool, docs: list[str] | None = None, gleaning: int = 0):
    s = get_settings()
    llm = OllamaClient(s.ollama_base_url, model, s.ollama_num_ctx, s.ollama_timeout)
    gold = json.loads((ROOT / "eval" / "gold.json").read_text())
    per_doc, rejected, extracted_all, elapsed = {}, Counter(), {}, {}
    adjusted = Counter()
    for name, g in gold.items():
        if docs and name not in docs:
            continue
        text = clean_text((ROOT / "eval" / "docs" / name).read_text())
        t0 = time.time()
        facts = []
        for ch in chunk_text(text, s.chunk_chars, s.chunk_overlap_chars):
            r = extract_chunk(llm, ch.text, verify, gleaning_passes=gleaning)
            rejected.update(r.rejected)
            adjusted.update(r.adjusted)
            facts += [{"subject": f.subject, "predicate": f.predicate, "object": f.object, "valid_from": f.valid_from,
                       "valid_to": f.valid_to, "evidence": f.evidence} for f in r.facts]
        elapsed[name] = round(time.time() - t0, 1)
        extracted_all[name] = facts
        per_doc[name] = score_document(facts, g)
    rejected = {**dict(rejected), **{'(adjusted) ' + k: v for k, v in adjusted.items()}}
    return per_doc, combine(per_doc), rejected, extracted_all, elapsed


def show(per_doc, total, rejected, elapsed, verbose=True):
    for name, r in per_doc.items():
        print(f"\n== {name}  ({elapsed.get(name)}s)  matched {r['matched']}/{r['required']}  predicate ok {r['predicate_ok']}  "
              f"dates ok {r['date_ok']}/{r['dated']}  good {r['good_unique']}  bad {r['bad']}")
        if verbose:
            for m in r["missed"]:
                print(f"   MISSED   {m['subject'][0]} -> {m['object'][0]}  {m['from']}..{m['to']}" + ("  (pronoun)" if m["pronoun"] else ""))
            for b in r["bad_facts"]:
                print(f"   BAD      {b['subject']} | {b['predicate']} | {b['object']}  {b['valid_from']}..{b['valid_to']}  <- {b['why']}")
    print("\nTOTAL", json.dumps({k: v for k, v in total.items() if not k.startswith("k_") and k not in
                                 ("matched_non_pronoun", "required_non_pronoun", "good_unique")}))
    print("kinds:", {k[2:]: v for k, v in total.items() if k.startswith("k_")}, "| rejected by the checks:", rejected)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=get_settings().ollama_model)
    ap.add_argument("--verify", dest="verify", action="store_true", default=True)
    ap.add_argument("--no-verify", dest="verify", action="store_false")
    ap.add_argument("--docs", nargs="*")
    ap.add_argument("--gleaning", type=int, default=0)
    ap.add_argument("--json")
    a = ap.parse_args()
    per_doc, total, rejected, extracted, elapsed = run(a.model, a.verify, a.docs, a.gleaning)
    print(f"model={a.model} verify={a.verify} gleaning={a.gleaning}")
    show(per_doc, total, rejected, elapsed)
    if a.json:
        Path(a.json).write_text(json.dumps({"model": a.model, "verify": a.verify, "gleaning": a.gleaning, "total": total, "rejected": rejected,
                                            "per_doc": per_doc, "extracted": extracted, "elapsed": elapsed}, indent=1, default=str))
