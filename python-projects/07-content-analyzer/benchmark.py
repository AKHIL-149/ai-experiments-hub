#!/usr/bin/env python3
"""One-shot benchmark: runs several test suites against the live server and
compares the result with the previous run.

    python3 benchmark.py                      # health + vision + compare + ocr (subset)
    python3 benchmark.py --suites vision      # just one suite
    python3 benchmark.py --limit 5            # first 5 items per suite (quick check)
    python3 benchmark.py --ocr-all            # all 12 OCR images (slow: ~2.5 min each on CPU)

Needs the server running (python3 server.py) and the test images in
data/test_images/ (see benchmarks/image_sources/ for where they came from).
Results go to data/benchmarks/run_<timestamp>.json and .md.
"""
import argparse
import io
import json
import re
import statistics
import sys
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageOps

ROOT = Path(__file__).parent
IMAGES = ROOT / "data" / "test_images"
OUT_DIR = ROOT / "data" / "benchmarks"
EXPECT = json.loads((ROOT / "benchmarks" / "expectations.json").read_text())
REQUEST_TIMEOUT = 420


def image_path(rel, suite):
    base = IMAGES / "ocr" if suite == "ocr" else IMAGES
    return base / rel


def check_text(text, spec):
    """Every 'must' group needs a hit; no 'must_not' phrase may appear."""
    low = (text or "").lower()
    missing = [g[0] for g in spec.get("must", []) if not any(w.lower() in low for w in g)]
    bad = [w for w in spec.get("must_not", []) if w.lower() in low]
    problems = [f"missing '{m}'" for m in missing] + [f"hallucinated '{b}'" for b in bad]
    return not problems, "; ".join(problems) or "ok"


def looks_like_loop(text):
    """True when one 3-word phrase makes up a big share of the output."""
    words = re.findall(r"\S+", text or "")
    if len(words) < 30:
        # CJK output has no spaces: fall back to repeated character chunks
        chunks = [text[i:i + 6] for i in range(0, len(text or ""), 6)]
        return len(chunks) > 20 and Counter(chunks).most_common(1)[0][1] / len(chunks) > 0.3
    grams = Counter(tuple(words[i:i + 3]) for i in range(len(words) - 2))
    return grams.most_common(1)[0][1] * 3 / len(words) > 0.3


class HealthProbe(threading.Thread):
    """Polls /api/health during a run to prove the server stays responsive."""

    def __init__(self, base):
        super().__init__(daemon=True)
        self.base, self.stop_flag, self.latencies, self.failures = base, threading.Event(), [], 0

    def run(self):
        while not self.stop_flag.is_set():
            t = time.time()
            try:
                requests.get(f"{self.base}/api/health", timeout=10)
                self.latencies.append(time.time() - t)
            except requests.RequestException:
                self.failures += 1
            self.stop_flag.wait(2)


def post(base, path, files, data):
    t = time.time()
    r = requests.post(f"{base}{path}", files=files, data=data, timeout=REQUEST_TIMEOUT)
    return r.json(), time.time() - t


def run_vision(base, limit):
    results = []
    items = list(EXPECT["vision"].items())[:limit]
    for i, (rel, spec) in enumerate(items, 1):
        print(f"  vision {i}/{len(items)} {rel}", flush=True)
        try:
            with open(image_path(rel, "vision"), "rb") as f:
                j, secs = post(base, "/api/analyze", {"file": (Path(rel).name, f, "image/jpeg")},
                               {"enable_cache": "false", "max_tokens": "300"})
            if not j.get("success"):
                results.append(dict(suite="vision", id=rel, passed=False, detail=f"error: {j.get('error')}", secs=secs, text=""))
                continue
            ok, detail = check_text(j["result"], spec)
            results.append(dict(suite="vision", id=rel, passed=ok, detail=detail, secs=secs, text=j["result"][:1500]))
        except Exception as e:
            results.append(dict(suite="vision", id=rel, passed=False, detail=f"exception: {e}", secs=0, text=""))
    return results


def run_ocr(base, limit, ocr_all):
    keys = list(EXPECT["ocr"]) if ocr_all else EXPECT["ocr_default_subset"]
    results = []
    for i, rel in enumerate(keys[:limit], 1):
        print(f"  ocr {i}/{len(keys[:limit])} {rel}", flush=True)
        try:
            with open(image_path(rel, "ocr"), "rb") as f:
                j, secs = post(base, "/api/ocr", {"file": (Path(rel).name, f, "image/jpeg")},
                               {"method": "vision", "fallback": "false"})
            if not j.get("success"):
                results.append(dict(suite="ocr", id=rel, passed=False, detail=f"error: {j.get('error')}", secs=secs, text=""))
                continue
            text = j.get("text") or ""
            ok, detail = check_text(text, EXPECT["ocr"][rel])
            loop = looks_like_loop(text)
            if loop:
                ok, detail = False, f"repetition loop; {detail}"
            results.append(dict(suite="ocr", id=rel, passed=ok, detail=detail, secs=secs, text=text[:1500], loop=loop))
        except Exception as e:
            results.append(dict(suite="ocr", id=rel, passed=False, detail=f"exception: {e}", secs=0, text=""))
    return results


def run_compare(base, use_ai):
    results = []

    def cmp(name, img1, img2, ai, check):
        print(f"  compare {name}", flush=True)
        try:
            j, secs = post(base, "/api/compare",
                           {"file1": ("a.jpg", img1, "image/jpeg"), "file2": ("b.jpg", img2, "image/jpeg")},
                           {"use_ai": str(ai).lower(), "mode": "content"})
            if not j.get("success"):
                return results.append(dict(suite="compare", id=name, passed=False, detail=f"error: {j.get('error')}", secs=secs, text=""))
            r = j["result"]
            ai_err = (r.get("ai_analysis") or {}).get("error")
            ok, detail = (False, f"AI error: {ai_err}") if ai and ai_err else check(r)
            results.append(dict(suite="compare", id=name, passed=ok, detail=detail, secs=secs,
                                text=json.dumps({k: r.get(k) for k in ("identical", "similar_dimensions", "similarity_score")})))
        except Exception as e:
            results.append(dict(suite="compare", id=name, passed=False, detail=f"exception: {e}", secs=0, text=""))

    src = (IMAGES / "picsum_1.jpg").read_bytes()
    buf = io.BytesIO()
    ImageOps.mirror(Image.open(IMAGES / "picsum_1.jpg")).save(buf, "JPEG")
    mirrored = buf.getvalue()
    other = (IMAGES / "picsum_2.jpg").read_bytes()

    cmp("identical_images", src, src, False,
        lambda r: (r["identical"] and r["similarity_score"] == 100, f"identical={r['identical']} score={r['similarity_score']}"))
    if use_ai:
        cmp("mirrored_same_scene_ai", src, mirrored, True,
            lambda r: ((not r["identical"]) and r["similar_dimensions"] and r["similarity_score"] >= 50,
                       f"identical={r['identical']} dims_same={r['similar_dimensions']} score={r['similarity_score']} (want >=50)"))
        cmp("different_scenes_ai", src, other, True,
            lambda r: (r["similarity_score"] <= 40, f"score={r['similarity_score']} (want <=40)"))
    return results


def summarize(results):
    out = {}
    for suite in sorted({r["suite"] for r in results}):
        rs = [r for r in results if r["suite"] == suite]
        out[suite] = dict(passed=sum(r["passed"] for r in rs), total=len(rs),
                          median_secs=round(statistics.median(r["secs"] for r in rs), 1) if rs else 0)
    return out


def best_previous(current_path, results):
    """Earlier run sharing the most tests with this one (ties -> most recent), so a
    quick partial run in between doesn't shrink what the next full run is compared to."""
    ids = {(r["suite"], r["id"]) for r in results}
    best, best_overlap = None, 0
    for p in sorted(OUT_DIR.glob("run_*.json")):
        if p == current_path:
            continue
        run = json.loads(p.read_text())
        overlap = len(ids & {(r["suite"], r["id"]) for r in run["results"]})
        if overlap >= best_overlap and overlap > 0:
            best, best_overlap = run, overlap
    return best


def compare_runs(prev, cur):
    lines = [f"## Comparison with previous run ({prev['meta']['timestamp']})", ""]
    pmap = {(r["suite"], r["id"]): r for r in prev["results"]}
    cmap = {(r["suite"], r["id"]): r for r in cur["results"]}
    both = [k for k in cmap if k in pmap]
    lines.append("| Suite | Previous | Now | Change | Median secs prev -> now |")
    lines.append("|---|---|---|---|---|")
    for suite in cur["summary"]:
        keys = [k for k in both if k[0] == suite]
        if not keys:
            continue
        pp = sum(pmap[k]["passed"] for k in keys)
        cp = sum(cmap[k]["passed"] for k in keys)
        pm = statistics.median(pmap[k]["secs"] for k in keys)
        cm = statistics.median(cmap[k]["secs"] for k in keys)
        lines.append(f"| {suite} | {pp}/{len(keys)} | {cp}/{len(keys)} | {cp - pp:+d} | {pm:.1f}s -> {cm:.1f}s |")
    regress = [k for k in both if pmap[k]["passed"] and not cmap[k]["passed"]]
    fixed = [k for k in both if not pmap[k]["passed"] and cmap[k]["passed"]]
    lines += ["", f"**Regressions (pass -> fail): {len(regress)}**"]
    lines += [f"- {k[0]}/{k[1]}: {cmap[k]['detail']}" for k in regress] or ["- none"]
    lines += ["", f"**Improvements (fail -> pass): {len(fixed)}**"]
    lines += [f"- {k[0]}/{k[1]}" for k in fixed] or ["- none"]
    lines += ["", f"Compared {len(both)} shared tests; {len(cmap) - len(both)} new in this run."]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # 127.0.0.1, not localhost: on macOS the resolver can stall ~5s per lookup, which showed up as a
    # false "server unresponsive" reading in the health probe.
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--suites", default="health,vision,compare,ocr")
    ap.add_argument("--limit", type=int, default=999, help="max items per vision/ocr suite")
    ap.add_argument("--ocr-all", action="store_true")
    ap.add_argument("--no-ai-compare", action="store_true")
    args = ap.parse_args()
    suites = set(args.suites.split(","))

    try:
        health = requests.get(f"{args.base_url}/api/health", timeout=5).json()
    except requests.RequestException:
        sys.exit(f"Server not reachable at {args.base_url} - start it with: python3 server.py")

    results, started = [], time.time()
    probe = HealthProbe(args.base_url)
    probe.start()

    if "health" in suites:
        prov = health.get("providers", {})
        ok = health.get("status") == "healthy" and bool(health.get("default_provider")) and prov.get(health["default_provider"], {}).get("available")
        results.append(dict(suite="health", id="default_provider_available", passed=bool(ok), secs=0, text="",
                            detail=f"default={health.get('default_provider')} providers={json.dumps(prov)}"))
    if "vision" in suites:
        print("Vision suite...", flush=True); results += run_vision(args.base_url, args.limit)
    if "compare" in suites:
        print("Compare suite...", flush=True); results += run_compare(args.base_url, not args.no_ai_compare)
    if "ocr" in suites:
        print("OCR suite...", flush=True); results += run_ocr(args.base_url, args.limit, args.ocr_all)

    probe.stop_flag.set()
    if "health" in suites and probe.latencies:
        worst = max(probe.latencies)
        results.append(dict(suite="health", id="responsive_during_model_calls", secs=round(worst, 3), text="",
                            passed=worst < 2 and probe.failures == 0,
                            detail=f"{len(probe.latencies)} probes, worst {worst:.3f}s, {probe.failures} failures"))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUT_DIR / f"run_{stamp}.json"
    run = dict(meta=dict(timestamp=stamp, provider=health.get("default_provider"), suites=sorted(suites),
                         total_secs=round(time.time() - started)), results=results, summary=summarize(results))
    prev = best_previous(path, results)
    path.write_text(json.dumps(run, indent=1, ensure_ascii=False))

    md = [f"# Benchmark {stamp} (provider: {run['meta']['provider']}, {run['meta']['total_secs']}s)", "",
          "| Suite | Passed | Median secs |", "|---|---|---|"]
    md += [f"| {s} | {v['passed']}/{v['total']} | {v['median_secs']} |" for s, v in run["summary"].items()]
    fails = [r for r in results if not r["passed"]]
    md += ["", f"## Failures ({len(fails)})"] + [f"- **{r['suite']}/{r['id']}**: {r['detail']}" for r in fails]
    md += ["", compare_runs(prev, run) if prev else "No previous run found - this run is the baseline."]
    report = "\n".join(md)
    path.with_suffix(".md").write_text(report)
    print("\n" + report + f"\n\nSaved: {path}")


if __name__ == "__main__":
    main()
