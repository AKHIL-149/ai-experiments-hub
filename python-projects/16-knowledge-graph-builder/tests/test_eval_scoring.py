from eval.scoring import combine, score_document


def F(subj, obj, preds=("found",), frm="", to="", sym=False, pronoun=False, value=False):
    return {"subject": subj, "object": obj, "predicates": list(preds), "from": frm, "to": to, "symmetric": sym,
            "pronoun": pronoun, "value": value}


def X(subject, predicate, obj, frm="", to=""):
    return {"subject": subject, "predicate": predicate, "object": obj, "valid_from": frm, "valid_to": to}


GOLD = {"required": [F(["Maria"], ["Acme"], frm="2010"), F(["Ann"], ["Bob"], ["married"], sym=True),
                     F(["Acme"], ["12M"], ["revenue"], value=True), F(["Dan"], ["Acme"], pronoun=True)],
        "optional": [F(["Acme"], ["Oslo"])],
        "traps": [{"note": "negated", "subject": ["Acme"], "object": ["Zed"], "any_direction": True}]}


def test_perfect_match_scores_one():
    facts = [X("Maria", "founded", "Acme", "2010"), X("Bob", "married to", "Ann"), X("Acme", "reported revenue", "12M euros"),
             X("Dan", "founded", "Acme")]
    r = score_document(facts, GOLD)
    assert (r["matched"], r["predicate_ok"], r["date_ok"], r["dated"], r["bad"]) == (4, 4, 1, 1, 0)


def test_reversed_direction_is_counted_separately_and_does_not_match():
    r = score_document([X("Acme", "founded", "Maria", "2010")], GOLD)
    assert r["matched"] == 0 and r["kinds"] == {"reversed": 1}


def test_traps_optional_and_unlisted():
    facts = [X("Acme", "bought", "Zed"), X("Zed", "bought", "Acme"), X("Acme", "based in", "Oslo"), X("Acme", "likes", "Tea")]
    r = score_document(facts, GOLD)
    assert r["kinds"] == {"trap_hit": 2, "optional_match": 1, "unlisted": 1} and r["bad"] == 3 and r["good_unique"] == 1


def test_wrong_predicate_and_wrong_dates_are_visible():
    r = score_document([X("Maria", "adopted", "Acme", "2011")], GOLD)
    assert r["matched"] == 1 and r["predicate_ok"] == 0 and r["date_ok"] == 0 and r["dated"] == 1


def test_descriptor_words_do_not_change_the_entity():
    gold = {"required": [F(["Widget-X"], ["ISO 13849"], ["compl"])], "optional": [], "traps": []}
    assert score_document([X("Widget-X Sensor", "complies with", "ISO 13849 safety standard")], gold)["matched"] == 1
    gold = {"required": [F(["Aldermoor"], ["Spain"], ["in"])], "optional": [], "traps": []}
    assert score_document([X("University of Aldermoor", "in", "Spain")], gold)["matched"] == 0


def test_duplicates_count_once_and_combine_computes_rates():
    facts = [X("Maria", "founded", "Acme", "2010"), X("Maria", "created", "Acme", "2010")]
    r = score_document(facts, GOLD)
    assert r["matched"] == 1 and r["bad"] == 0 and r["good_unique"] == 1
    total = combine({"d": r})
    assert total["recall"] == 0.25 and total["precision"] == 1.0 and total["recall_non_pronoun"] == round(1 / 3, 3)
    assert combine({})["recall"] is None
