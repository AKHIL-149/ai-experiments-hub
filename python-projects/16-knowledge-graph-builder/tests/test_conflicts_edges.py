"""The edges of conflict detection, settling and claim checking (added after break-testing found them unguarded)"""
import pytest
from sqlalchemy import select

from src.models.conflict import Conflict, ConflictStatus
from src.services import conflicts as cf
from src.services import pipeline
from src.services.temporal import overlap_status
from tests.conftest import FakeEmbedder
from tests.test_conflicts import Classifier, client, conflict_of, disputes, pairs  # noqa: F401  (fixtures and helpers)
from tests.test_factcheck import ClaimLLM, check, firm, parsed  # noqa: F401


# ---------------------------------------------------------------- dates written to different precision

def test_a_month_and_a_year_are_compared_as_years():
    assert overlap_status("2012", "2019-06", "2019", "2022") == "none"            # ended in 2019, the other began in 2019: a handover
    assert overlap_status("2012", "2019", "2019-06", "2022") == "none"
    assert overlap_status("2012", "2020-06", "2019", "2022") == "certain"


# ---------------------------------------------------------------- the built-in list in other words

def test_president_and_became_are_understood():
    assert cf.lexicon_lookup("president of") == ("president", "one_subject") and cf.lexicon_lookup("presided over") == ("president", "one_subject")
    assert cf.normalize_predicate("became CTO of") == "cto of" and cf.normalize_predicate("was the CTO of") == "cto of"
    assert cf.normalize_predicate("currently chair of") == "chair of"


def test_a_word_is_asked_about_directly_only_once(db):
    llm = Classifier("one_object")
    assert cf.classify_predicate(db, llm, "born at") == "one_object" and cf.classify_predicate(db, llm, "born at") == "one_object"
    assert len(llm.asked) == 1


def test_values_are_compared_by_their_first_number():
    assert cf._value_key("1,200 people") == "1200" and cf._value_key("about 12 of 340") == "12" and cf._value_key("Four Hundred") == "four hundred"


# ---------------------------------------------------------------- what is and is not a pair

def test_the_same_value_stated_twice_is_not_a_conflict(world):
    w = world
    acme = w.ent("Acme")
    w.fact(acme, "employs", value="340 people", frm="2020", title="a")
    w.fact(acme, "employs", value="340 people", frm="2021", title="b")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0


def test_a_value_and_an_entity_for_one_relation_are_not_compared(world):
    w = world
    acme, beta = w.ent("Acme"), w.ent("Beta")
    w.fact(acme, "employs", value="340 people", title="a")
    w.fact(acme, "employs", beta, title="b")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0


def test_one_person_holding_a_role_twice_is_not_a_conflict(world):
    w = world
    acme, maria = w.ent("Acme"), w.ent("Maria Lopez", "person")
    w.fact(maria, "was CTO of", acme, frm="2012", to="2015", title="a")
    w.fact(maria, "was CTO of", acme, frm="2017", to="2019", title="b")
    w.fact(maria, "was CTO of", acme, frm="2013", to="2018", title="c")       # even overlapping: the same holder
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0


def test_the_same_direction_stated_twice_is_not_reversed(world):
    w = world
    a, b = w.ent("Veltra"), w.ent("Soro")
    w.fact(a, "acquired", b, frm="2001", title="x")
    w.fact(a, "acquired", b, frm="2005", title="y")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0


def test_a_pair_is_always_stored_with_the_smaller_fact_id_first(disputes):
    for _, _, a, b, _ in cf.find_pairs(disputes.db, None):
        assert a.fact.id < b.fact.id
    cf.run_detection(disputes.db, owner_id=None)
    assert all(c.fact_a_id < c.fact_b_id for c in disputes.db.execute(select(Conflict)).scalars())


# ---------------------------------------------------------------- facts a person left out stay out

def test_a_fact_left_out_is_not_compared_with_new_facts(disputes):
    d = disputes
    c = conflict_of(d, d.e1, d.e2)
    cf.resolve(d.db, c.id, "keep_a" if c.fact_a_id == d.e1.id else "keep_b")           # e1 (340) is kept, e2 (400) left out
    third = d.fact(d.acme, "employs", value="500 people", title="c")
    d.db.commit()
    cf.run_detection(d.db, owner_id=None)
    got = pairs(d)
    assert frozenset((d.e1.id, third.id)) in got and frozenset((d.e2.id, third.id)) not in got


def test_only_choosing_a_side_leaves_a_fact_out(disputes):
    d = disputes
    cf.resolve(d.db, conflict_of(d, d.e1, d.e2).id, "both")
    cf.resolve(d.db, conflict_of(d, d.c3, d.c4).id, "succession")
    cf.resolve(d.db, conflict_of(d, d.hq1, d.hq3).id, "keep_a" if conflict_of(d, d.hq1, d.hq3).fact_a_id == d.hq1.id else "keep_b")
    assert cf.overruled_ids(d.db, None) == {d.hq3.id}


def test_running_again_refreshes_an_open_conflict(disputes):
    d = disputes
    c = conflict_of(d, d.hq2, d.hq3)
    assert c.severity == "possible"
    d.hq3.valid_to = "2015"                                  # now Brindle 2010-2015 and Valcross since 2012: dates surely overlap
    d.db.commit()
    cf.run_detection(d.db, owner_id=None)
    d.db.refresh(c)
    assert c.severity == "certain" and "their dates share time" in c.reasons[1]


# ---------------------------------------------------------------- the model's opinion

def test_only_a_given_opinion_is_counted(disputes):
    class Unusable(Classifier):
        def generate_json(self, system, prompt, schema, max_tokens=None):
            if system == cf.JUDGE_SYSTEM:
                return {"contradict": "maybe"}
            return super().generate_json(system, prompt, schema, max_tokens)
    s = cf.run_detection(disputes.db, owner_id=None, llm=Unusable(), judge=True)
    assert s.judged == 0 and {c.llm_verdict for c in pairs(disputes).values()} == {None}


# ---------------------------------------------------------------- undoing

def test_reopening_clears_the_decision(disputes):
    d = disputes
    c = conflict_of(d, d.e1, d.e2)
    cf.resolve(d.db, c.id, "keep_a")
    cf.reopen(d.db, c.id)
    assert (c.status, c.resolution, c.data, c.decided_at) == (ConflictStatus.OPEN, None, {}, None)


def test_a_succession_cannot_be_undone_over_a_fact_that_now_has_the_old_dates(disputes):
    d = disputes
    c = conflict_of(d, d.c3, d.c4)
    cf.resolve(d.db, c.id, "succession")
    d.fact(d.omar, "chief technology officer of", d.acme, frm="2021", title="twin")          # the old dates exist again
    d.db.commit()
    with pytest.raises(cf.ConflictError, match="cannot be restored"):
        cf.reopen(d.db, c.id)
    assert d.c4.valid_to == "2023" and c.status == ConflictStatus.RESOLVED


def test_ending_the_earlier_one_needs_both_to_have_a_start(disputes):
    d = disputes
    undated = d.fact(d.imani, "chief technology officer of", d.acme, title="u")
    d.db.commit()
    assert cf.succession_order(undated, d.c3) is None and cf.succession_order(d.c3, undated) is None


# ---------------------------------------------------------------- what the readers show once a fact is left out

def test_the_stats_and_the_entity_leave_out_what_lost(client):
    d = client.d
    client.post("/api/conflicts/run")
    cs = client.get("/api/conflicts").json()["conflicts"]
    holders = next(c for c in cs if c["kind"] == "different_holder" and "Omar" in (c["a"]["text"] + c["b"]["text"]) and "Dana" in (c["a"]["text"] + c["b"]["text"]))
    loser = holders["b"] if "Dana" in holders["a"]["text"] else holders["a"]
    client.post(f"/api/conflicts/{holders['id']}/resolve", json={"resolution": "keep_a" if loser is holders["b"] else "keep_b"})
    detail = client.get(f"/api/entities/{d.acme.id}").json()
    assert loser["id"] not in {f["id"] for f in detail["incoming"]}
    assert client.get("/api/graph/stats").json()["time"]["dated_facts"] == 6      # 7 dated facts, one left out


def test_a_fact_shows_its_partner_whichever_side_it_is_on(client):
    d = client.d
    client.post("/api/conflicts/run")
    first = client.get(f"/api/facts/{d.e1.id}").json()["conflicts"][0]["other"]["id"]
    second = client.get(f"/api/facts/{d.e2.id}").json()["conflicts"][0]["other"]["id"]
    assert {first, second} == {d.e1.id, d.e2.id} and first != d.e1.id and second != d.e2.id


def test_the_list_says_when_the_earlier_fact_can_be_ended(client):
    client.post("/api/conflicts/run")
    cs = client.get("/api/conflicts").json()["conflicts"]
    by_kind = {(c["kind"], c["severity"]): c["can_end_earlier"] for c in cs}
    assert by_kind[("different_holder", "possible")] is True              # Omar since 2021, Kim since 2023: one can end where the other began
    assert by_kind[("different_value", "possible")] is False


def test_settling_waits_for_a_document_being_read(client):
    client.post("/api/conflicts/run")
    cid = client.get("/api/conflicts").json()["conflicts"][0]["id"]
    lock = pipeline.owner_lock(None)
    assert lock.acquire(blocking=False)
    try:
        assert client.post(f"/api/conflicts/{cid}/resolve", json={"resolution": "both"}).status_code == 409
        assert client.post(f"/api/conflicts/{cid}/reopen").status_code == 409
        assert client.post("/api/conflicts/run").status_code == 409
    finally:
        lock.release()
    assert client.post(f"/api/conflicts/{cid}/resolve", json={"resolution": "both"}).status_code == 200


def test_the_list_puts_certain_conflicts_before_possible_ones(client):
    client.post("/api/conflicts/run")
    sev = [c["severity"] for c in client.get("/api/conflicts").json()["conflicts"]]
    assert sev == sorted(sev) and sev[0] == "certain"


# ---------------------------------------------------------------- claims

def test_a_different_object_clashes_even_when_the_documents_know_the_place(firm):
    firm.fact(firm.val, "is a city in", firm.ent("Dravia", "place"), title="geo")
    firm.db.commit()
    r = check(firm, "Quillon Systems is headquartered in Valcross.", {"Quillon Systems is headquartered in Valcross.": parsed("Quillon Systems", "is headquartered in", "Valcross")})
    assert r["verdict"] == "contradicted" and "something else" in r["summary"] and "Dunmere" in r["summary"]


def test_the_same_relation_in_other_words_still_supports(firm):
    r = check(firm, "Dana Reyes held the chief technology officer role of Acme Corp in 2021.",
              {"Dana Reyes held the chief technology officer role of Acme Corp in 2021.": parsed("Dana Reyes", "chief technology officer of", "Acme Corp", "2021")})
    assert r["verdict"] == "supported"


def test_a_part_of_a_name_is_enough_to_find_the_subject(firm):
    r = check(firm, "Lopez works at Quillon Systems.", {"Lopez works at Quillon Systems.": parsed("Lopez", "works at", "Quillon Systems")})
    assert r["verdict"] == "supported" and r["parsed"]["subject"] == "Lopez"


def test_a_claim_with_a_bad_reading_twice_is_unclear(firm):
    from src.services.llm import LLMBadOutput
    r = check(firm, "Gibberish claim here.", {"Gibberish claim here.": LLMBadOutput("x")})
    assert r["verdict"] == "unclear" and r["parsed"] is None


# ---------------------------------------------------------------- values read from one sentence are a list, not a disagreement

LIST_SENTENCE = "The pilot was tested on a simulated cohort of 100 patients, 12 providers, and 8 pharmacies."


def _list_doc(w, text):
    from src.models.graph import Document
    w.db.get(Document, w.doc).text = text
    w.db.commit()


def test_values_read_from_one_sentence_are_a_list_not_a_conflict(world):
    w = world
    pilot = w.ent("Pilot")
    w.fact(pilot, "tested", value="100 patients", quote=LIST_SENTENCE)
    w.fact(pilot, "tested", value="12 providers", quote=LIST_SENTENCE)
    w.fact(pilot, "tested", value="8 pharmacies", quote=LIST_SENTENCE)
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0


def test_the_same_quote_with_other_spacing_is_still_the_same_quote(world):
    w = world
    pilot = w.ent("Pilot")
    w.fact(pilot, "tested", value="100 patients", quote="tested on 100 patients,\n12 providers")
    w.fact(pilot, "tested", value="12 providers", quote="tested on 100  patients, 12 providers")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0


def test_one_quote_cut_shorter_than_the_other_is_the_same_place(world):
    w = world
    pilot = w.ent("Pilot")
    w.fact(pilot, "tested", value="100 patients", quote="Adherence rose in 45 (64.3%), and the mean change was +8.4 points.")
    w.fact(pilot, "tested", value="12 providers", quote="Adherence rose in 45 (64.3%),")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0


def test_two_different_quotes_inside_one_sentence_are_one_sentence(world):
    w = world
    pilot = w.ent("Pilot")
    _list_doc(w, "Intro text. " + LIST_SENTENCE + " Next sentence follows.")
    w.fact(pilot, "tested", value="100 patients", quote="a simulated cohort of 100 patients")
    w.fact(pilot, "tested", value="12 providers", quote="12 providers, and 8 pharmacies")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0


def test_different_values_in_different_sentences_of_one_document_are_still_flagged(world):
    w = world
    acme = w.ent("Acme")
    _list_doc(w, "Acme employs 340 people. Later on, Acme employs 410 people. That is all.")
    w.fact(acme, "employs", value="340 people", quote="Acme employs 340 people.")
    w.fact(acme, "employs", value="410 people", quote="Later on, Acme employs 410 people.")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 1


def test_a_decimal_point_or_an_abbreviation_does_not_end_a_sentence_but_a_full_stop_does(world):
    w = world
    pilot = w.ent("Pilot")
    _list_doc(w, "Adherence was 44.4 at the start and 64.3 at the end, as Dr. Lee noted. Another sentence.")
    w.fact(pilot, "adherence", value="44.4", quote="Adherence was 44.4 at the start")
    w.fact(pilot, "adherence", value="64.3", quote="64.3 at the end, as Dr. Lee noted.")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0
    from src.models.graph import FactSource
    # the same two facts, read from two sentences: flagged
    _list_doc(w, "Adherence was 44.4 at the start. Adherence was 64.3 at the end.")
    for src, q in zip(w.db.execute(select(FactSource).order_by(FactSource.created_at)).scalars(), ("Adherence was 44.4 at the start.", "Adherence was 64.3 at the end.")):
        src.evidence = q
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 1


def test_the_same_sentence_in_two_documents_is_still_a_conflict_between_documents(world):
    w = world
    acme = w.ent("Acme")
    w.fact(acme, "employs", value="340 people", quote="Acme employs a number of people.", title="a")
    w.fact(acme, "employs", value="410 people", quote="Acme employs a number of people.", title="b")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 1


def test_a_quote_that_is_not_in_the_document_text_is_compared_as_written(world):
    w = world
    acme = w.ent("Acme")
    _list_doc(w, "Something else entirely.")
    w.fact(acme, "employs", value="340 people", quote="Acme employs 340 people.")
    w.fact(acme, "employs", value="410 people", quote="Acme employs 410 people.")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 1


def test_a_reversed_pair_with_one_quote_is_still_flagged(world):
    w = world
    a, b = w.ent("Veltra"), w.ent("Soro")
    q = "Veltra and Soro: one bought the other."
    w.fact(a, "acquired", b, quote=q)
    w.fact(b, "acquired", a, quote=q)
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 1


def test_same_quote_holders_and_places_are_not_flagged_either(world):
    w = world
    acme, quillon = w.ent("Acme"), w.ent("Quillon")
    d, v = w.ent("Dunmere", "place"), w.ent("Valcross", "place")
    m, k = w.ent("Maria", "person"), w.ent("Kim", "person")
    q = "Quillon has offices in Dunmere and Valcross and Acme is led by Maria and Kim."
    w.fact(quillon, "headquartered in", d, quote=q)
    w.fact(quillon, "headquartered in", v, quote=q)
    w.fact(m, "was CEO of", acme, quote=q)
    w.fact(k, "was CEO of", acme, quote=q)
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0


@pytest.mark.parametrize("between", ["Is that so? ", "It rose! ", "Was it a no? ", "Was it Dr! ", "\n\n"])
def test_a_question_mark_an_exclamation_mark_or_a_blank_line_ends_a_sentence(world, between):
    w = world
    acme = w.ent("Acme")
    _list_doc(w, f"Acme employs 340 people{between}Acme employs 410 people.")
    w.fact(acme, "employs", value="340 people", quote="Acme employs 340 people")
    w.fact(acme, "employs", value="410 people", quote="Acme employs 410 people.")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 1
