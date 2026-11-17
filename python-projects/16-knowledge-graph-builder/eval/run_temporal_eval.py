"""Questions that name a time ("in 2018", "after 2018", "currently") over a small corpus of dated documents (eval/temporal).

  python3 -m eval.run_temporal_eval build /path/to/t.db
  python3 -m eval.run_temporal_eval run /path/to/t.db vector graph --json eval/temporal/results.json [--questions questions_heldout.json]

`today` is fixed so "currently" does not change with the day the evaluation is run.
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import run_qa_eval as qa  # noqa: E402

qa.QA = ROOT / "eval" / "temporal"
TODAY = date(2026, 11, 17)


def summarise(results, modes):
    out = {}
    for mode in modes:
        rs = [r for r in results if mode in r]
        out[mode] = {"all": f"{sum(r[mode]['correct'] for r in rs)}/{len(rs)}"}
        for kind in sorted({r["kind"] for r in rs}):
            k = [r for r in rs if r["kind"] == kind]
            out[mode][kind] = f"{sum(r[mode]['correct'] for r in k)}/{len(k)}"
        out[mode]["avg seconds"] = round(sum(r[mode]["seconds"] for r in rs) / len(rs), 1)
    return out


if __name__ == "__main__":
    qa.summarise = summarise
    import src.services.ask as ask_service
    orig = ask_service.ask
    ask_service.ask = lambda *a, **kw: orig(*a, today=TODAY, **kw)
    cmd = sys.argv[1]
    if cmd == "build":
        qa.build(sys.argv[2])
    elif cmd == "run":
        args = sys.argv[3:]
        out = args[args.index("--json") + 1] if "--json" in args else None
        only = args[args.index("--only") + 1].split(",") if "--only" in args else None
        qfile = args[args.index("--questions") + 1] if "--questions" in args else "questions.json"
        qa.run(sys.argv[2], [a for a in args if a in ("vector", "subgraph", "graph", "hybrid")], out, only, qfile)
