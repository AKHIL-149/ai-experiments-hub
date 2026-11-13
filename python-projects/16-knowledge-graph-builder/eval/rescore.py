"""Score saved extraction results again (after fixing the gold file) without calling the model:
   python3 -m eval.rescore eval/results_default.json"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_eval import show  # noqa: E402
from eval.scoring import combine, score_document  # noqa: E402

if __name__ == "__main__":
    saved = json.loads(Path(sys.argv[1]).read_text())
    gold = json.loads((ROOT / "eval" / "gold.json").read_text())
    per_doc = {n: score_document(f, gold[n]) for n, f in saved["extracted"].items()}
    print(f"model={saved['model']} verify={saved['verify']} gleaning={saved.get('gleaning')}")
    show(per_doc, combine(per_doc), saved.get("rejected", {}), saved.get("elapsed", {}), verbose="--quiet" not in sys.argv)
