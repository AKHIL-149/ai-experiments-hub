"""The labelled entity clusters (eval/entities.json) as a regression test for the rules (no model involved)"""
from eval.run_resolution_eval import score


def test_rules_never_merge_wrongly_and_find_most_true_pairs():
    r = score()
    assert r["auto_wrong"] == [] and r["auto_precision"] == 1.0         # an automatic merge is never wrong on this set
    assert r["auto_pairs_correct"] >= 18                                  # and it covers the safe cases
    assert r["suggestion_recall"] >= 0.9                                  # unsure pairs left for a person are mostly found
    assert r["suggestion_precision"] >= 0.7
    assert len(r["missed"]) <= 1


def test_the_hard_cases_stay_apart():
    r = score()
    merged = " ".join(r["auto_wrong"]) + " ".join(r["suggested_wrong"])
    # numbered or lettered look-alikes are never even suggested
    for name in ("Widget-W", "Zeta-8", "Henric II'", "Apollo 13"):
        assert name not in merged, name
