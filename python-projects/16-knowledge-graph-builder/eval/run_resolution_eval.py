"""Score entity resolution on hand-labelled entity clusters (eval/entities.json).

  python3 -m eval.run_resolution_eval            # the rules only (instant)
  python3 -m eval.run_resolution_eval --llm      # plus the model's second opinion on suggested pairs
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.config import get_settings  # noqa: E402
from src.services import resolution  # noqa: E402
from src.services.llm import OllamaClient  # noqa: E402


def load():
    data = json.loads((ROOT / "eval" / "entities.json").read_text())["entities"]
    infos, cluster = {}, {}
    for i, e in enumerate(data):
        eid = f"e{i}"
        links = frozenset((p, "out", o) for p, o in e["facts"])
        infos[eid] = resolution.EntityInfo(eid, e["name"], e["type"], resolution.canonical_tokens(e["name"], e["type"]),
                                           resolution.qualifier_of(e["name"], e["type"]), resolution.initials_of(e["name"], e["type"]),
                                           n_facts=len(e["facts"]), docs=frozenset(e["docs"]), links=links)
        cluster[eid] = e["cluster"]
    return data, infos, cluster


def facts_text(e):
    return "\n".join(f"- {e['name']} {p} {o}" for p, o in e["facts"]) or "(no facts)"


def score(llm=None):
    """Pairs of entities are scored after the automatic merges are applied: 'Acme Corp', 'ACME' and 'Acme Inc.' become
    one group, so one unsure link from that group to 'Acme Labs' is one suggestion, not three."""
    data, infos, cluster = load()
    decisions = resolution.evaluate(infos)
    parent = {i: i for i in infos}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    auto = {p for p, d in decisions.items() if d.kind == "auto"}
    for x, y in auto:
        parent[find(x)] = find(y)
    groups = {}
    for i in infos:
        groups.setdefault(find(i), []).append(i)
    # pairs inside one automatic group, against pairs that really are the same thing
    inside = {tuple(sorted(p)) for g in groups.values() for p in itertools.combinations(g, 2)}
    true_pairs = {tuple(sorted(p)) for p in itertools.combinations(infos, 2) if cluster[p[0]] == cluster[p[1]]}
    # one decision per pair of groups: the best scoring one
    suggest = {}
    for (x, y), d in decisions.items():
        if d.kind != "suggest" or find(x) == find(y):
            continue
        key = tuple(sorted((find(x), find(y))))
        if key not in suggest or d.score > suggest[key][1].score:
            suggest[key] = ((x, y), d)
    kept, verdicts = {}, {}
    for key, ((x, y), d) in suggest.items():
        score = d.score
        if llm is not None:
            a_, b_ = data[int(x[1:])], data[int(y[1:])]
            v = resolution.judge_text(llm, a_["name"], a_["type"], facts_text(a_), b_["name"], b_["type"], facts_text(b_))
            verdicts[key] = ((x, y), v)
            score = resolution.apply_verdict(score, v)
        if score >= resolution.MIN_SUGGESTION_SCORE:
            kept[key] = (x, y)
    same_groups = lambda key: cluster[key[0]] == cluster[key[1]]  # noqa: E731  (groups are pure unless an automatic merge was wrong)
    true_group_pairs = {tuple(sorted((find(x), find(y)))) for x, y in itertools.combinations(infos, 2)
                        if cluster[x] == cluster[y] and find(x) != find(y)}
    name = lambda p: f"{infos[p[0]].name!r} ~ {infos[p[1]].name!r}"  # noqa: E731
    good_sugg = {k for k in kept if cluster[kept[k][0]] == cluster[kept[k][1]]}
    out = {
        "entities": len(infos), "true_pairs": len(true_pairs),
        "auto_pairs": len(inside), "auto_pairs_correct": len(inside & true_pairs), "auto_wrong": sorted(name(p) for p in inside - true_pairs),
        "unsure_pairs_left": len(true_group_pairs), "suggested": len(kept), "suggested_correct": len(good_sugg),
        "suggested_wrong": sorted(name(kept[k]) for k in set(kept) - good_sugg),
        "missed": sorted(name(next(iter(((x, y) for x, y in itertools.combinations(infos, 2) if tuple(sorted((find(x), find(y)))) == k)))) for k in true_group_pairs - set(kept)),
    }
    out["auto_precision"] = round(len(inside & true_pairs) / len(inside), 3) if inside else None
    out["auto_share_of_true_pairs"] = round(len(inside & true_pairs) / len(true_pairs), 3)
    out["suggestion_precision"] = round(len(good_sugg) / len(kept), 3) if kept else None
    out["suggestion_recall"] = round(len(good_sugg & true_group_pairs) / len(true_group_pairs), 3) if true_group_pairs else None
    out["verdicts"] = {name(v[0]): v[1] for v in verdicts.values()}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--model", default=get_settings().ollama_model)
    a = ap.parse_args()
    llm = OllamaClient(get_settings().ollama_base_url, a.model, 8192, 300) if a.llm else None
    r = score(llm)
    print(json.dumps({k: v for k, v in r.items() if k not in ("auto_wrong", "suggested_wrong", "missed", "verdicts")}, indent=1))
    for k in ("auto_wrong", "suggested_wrong", "missed"):
        print(f"\n{k}:")
        for x in r[k]:
            print("  ", x)
    if r["verdicts"]:
        print("\nmodel verdicts:")
        for k, v in r["verdicts"].items():
            print("  ", v, k)
