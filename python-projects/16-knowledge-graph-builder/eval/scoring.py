"""Score extracted facts against hand-labelled gold facts (link level, predicate level, dates, traps)"""
from collections import Counter

from src.services.text_utils import core_words


# words that describe an entity without changing which one it is ("Widget-X sensor" = "Widget-X")
DESCRIPTORS = {"journal", "sensor", "processor", "standard", "safety", "professor", "dr", "king", "queen", "company", "city"}


def _core(name: str) -> list[str]:
    ws = [w for w in core_words(name) if w not in DESCRIPTORS]
    return ws or core_words(name)


def _same_name(extracted: str, aliases: list[str], value: bool = False) -> bool:
    x = _core(extracted)
    for a in aliases:
        ca = _core(a)
        if x == ca:
            return True
        if value and ca and (set(ca) <= set(x) or set(x) <= set(ca)):
            return True
    return False


def _pred_ok(predicate: str, accepted: list[str]) -> bool:
    p = predicate.casefold()
    return any(w in p for w in accepted)


def _link(fact, g, reverse: bool = False) -> bool:
    subj, obj = (g["object"], g["subject"]) if reverse else (g["subject"], g["object"])
    if reverse and g.get("value"):
        return False
    return _same_name(fact["subject"], subj) and _same_name(fact["object"], obj, value=bool(g.get("value")) and not reverse)


def score_document(facts: list[dict], gold: dict) -> dict:
    """facts: [{subject, predicate, object, valid_from, valid_to}]"""
    required, optional, traps = gold["required"], gold.get("optional", []), gold.get("traps", [])
    hit = {i: [] for i in range(len(required))}
    good_optional, kinds = set(), Counter()
    bad = []
    for f in facts:
        placed = False
        for i, g in enumerate(required):
            if _link(f, g) or (g.get("symmetric") and _link(f, g, reverse=True)):
                hit[i].append(f)
                placed = True
                break
        if placed:
            continue
        for j, g in enumerate(optional):
            if _link(f, g) or (g.get("symmetric") and _link(f, g, reverse=True)):
                good_optional.add(j)
                kinds["optional_match"] += 1
                placed = True
                break
        if placed:
            continue
        trap = next((t for t in traps if (_same_name(f["subject"], t["subject"]) and _same_name(f["object"], t["object"]))
                     or (t.get("any_direction") and _same_name(f["subject"], t["object"]) and _same_name(f["object"], t["subject"]))), None)
        if trap:
            bad.append({**f, "why": "trap: " + trap["note"]})
            kinds["trap_hit"] += 1
            continue
        if any(_link(f, g, reverse=True) for g in required + optional if not g.get("symmetric")):
            bad.append({**f, "why": "reversed direction"})
            kinds["reversed"] += 1
            continue
        bad.append({**f, "why": "not in gold (check by hand)"})
        kinds["unlisted"] += 1

    matched = [i for i, fs in hit.items() if fs]
    pred_ok = [i for i in matched if any(_pred_ok(f["predicate"], required[i]["predicates"]) for f in hit[i])]
    dated = [i for i in matched if required[i]["from"] or required[i]["to"]]
    date_ok = [i for i in dated if any(f["valid_from"] == required[i]["from"] and f["valid_to"] == required[i]["to"] for f in hit[i])]
    good = len(matched) + len(good_optional) + (kinds["optional_match"] - len(good_optional))  # duplicates of a good fact still good
    unique_good = len(matched) + len(good_optional)
    non_pron = [i for i, g in enumerate(required) if not g["pronoun"]]
    return {
        "required": len(required), "matched": len(matched), "predicate_ok": len(pred_ok),
        "dated": len(dated), "date_ok": len(date_ok),
        "matched_non_pronoun": len([i for i in matched if i in non_pron]), "required_non_pronoun": len(non_pron),
        "good_unique": unique_good, "bad": len(bad), "kinds": dict(kinds), "bad_facts": bad,
        "missed": [required[i] for i in range(len(required)) if i not in matched],
    }


def combine(per_doc: dict[str, dict]) -> dict:
    t = Counter()
    for r in per_doc.values():
        for k in ("required", "matched", "predicate_ok", "dated", "date_ok", "matched_non_pronoun", "required_non_pronoun", "good_unique", "bad"):
            t[k] += r[k]
        for k, v in r["kinds"].items():
            t["k_" + k] += v
    div = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
    return {**t,
            "recall": div(t["matched"], t["required"]),
            "recall_non_pronoun": div(t["matched_non_pronoun"], t["required_non_pronoun"]),
            "precision": div(t["good_unique"], t["good_unique"] + t["bad"]),
            "predicate_accuracy": div(t["predicate_ok"], t["matched"]),
            "date_accuracy": div(t["date_ok"], t["dated"])}
