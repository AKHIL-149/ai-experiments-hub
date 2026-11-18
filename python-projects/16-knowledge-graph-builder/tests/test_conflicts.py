"""Facts that cannot both be true: finding them, settling them, undoing it, and what they do to answers"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.core import config
from src.core.database import get_db
from src.models.conflict import Conflict, ConflictStatus, PredicateKind
from src.models.graph import Fact
from src.services import ask as ask_mod
from src.services import conflicts as cf
from src.services import graph_query as gq
from src.services import graph_store
from src.services.llm import LLMBadOutput, LLMError
from src.services.temporal import overlap_status
from tests.conftest import FakeEmbedder, FakeLLM, ScriptedLLM


# ---------------------------------------------------------------- two periods

@pytest.mark.parametrize("a,b,expected", [
    (("2012", "2019"), ("2019", "2022"), "none"),           # a handover
    (("2012", "2019"), ("2023", ""), "none"),
    (("2023", ""), ("2012", "2019"), "none"),
    (("2012", "2020"), ("2019", "2022"), "certain"),
    (("2012", "2020"), ("2019", ""), "certain"),
    (("2019", "2022"), ("2021", ""), "certain"),
    (("2020", ""), ("2023", ""), "possible"),                # neither states an end
    (("", ""), ("2020", ""), "possible"),                    # one has no date
    (("", "2020"), ("2019", "2021"), "possible"),            # no start to compare
    (("", ""), ("", ""), "unknown"),
    (("2019-03", ""), ("2019", "2020"), "certain"),
    (("2019-06", "2020-03"), ("2020-03", "2021"), "none"),   # ends the month the other begins
    (("2019-06", "2020-04"), ("2020-03", "2021"), "certain"),
])
def test_can_two_facts_have_held_at_once(a, b, expected):
    assert overlap_status(*a, *b) == expected


def test_a_missing_date_is_the_same_as_an_empty_one():
    assert overlap_status(None, None, "2020", None) == "possible" and overlap_status(None, None, None, None) == "unknown"


# ---------------------------------------------------------------- the built-in list of relations

@pytest.mark.parametrize("predicate,family,kind", [
    ("led", "leader", "one_subject"), ("served as chief executive of", "leader", "one_subject"), ("was CEO of", "leader", "one_subject"),
    ("head of", "leader", "one_subject"), ("became CTO of", "cto", "one_subject"), ("chief technology officer of", "cto", "one_subject"),
    ("chaired", "chair", "one_subject"), ("is the mayor of", "mayor", "one_subject"), ("served as mayor of", "mayor", "one_subject"),
    ("its headquarters in", "headquarters", "one_object"), ("moved its headquarters to", "headquarters", "one_object"),
    ("headquartered in", "headquarters", "one_object"), ("based in", "headquarters", "one_object"),
    ("born in", "birthplace", "one_object"), ("died in", "deathplace", "one_object"),
])
def test_relations_the_list_knows(predicate, family, kind):
    assert cf.lexicon_lookup(predicate) == (family, kind)


@pytest.mark.parametrize("predicate", ["founded", "acquired", "employs", "located in", "is a city in", "studied at", "works at", "invested in", "makes", "meets in"])
def test_relations_that_may_have_several_are_not_in_the_list(predicate):
    assert cf.lexicon_lookup(predicate) is None


def test_the_same_relation_in_different_words_is_one_group():
    assert cf.predicate_kind(None, "was CTO of") == cf.predicate_kind(None, "became CTO of") == ("cto", "one_subject")
    assert cf.normalize_predicate("is a city in") == "city in" and cf.normalize_predicate("served as chief executive of") == "chief executive of"


def test_an_unknown_relation_is_many_and_never_flagged(db):
    assert cf.predicate_kind(db, "owned by") == ("owned by", "many")


# ---------------------------------------------------------------- the model classifies a word once

class Classifier(FakeLLM):
    name = "fake:classifier"

    def __init__(self, kind="one_subject", fail=False):
        super().__init__()
        self.kind, self.fail, self.asked = kind, fail, []

    def generate_json(self, system, prompt, schema, max_tokens=None):
        if system == cf.CLASSIFY_SYSTEM:
            self.asked.append(prompt)
            if self.fail:
                raise LLMBadOutput("x")
            return {"kind": self.kind}
        if system == cf.JUDGE_SYSTEM:
            self.asked.append(prompt)
            return {"contradict": self.kind}
        raise AssertionError("unexpected")


def test_a_new_relation_word_is_asked_once_and_remembered(db):
    llm = Classifier("one_subject")
    assert cf.predicate_kind(db, "owned by", llm) == ("owned by", "one_subject")
    assert cf.predicate_kind(db, "was owned by", llm) == ("owned by", "one_subject")           # same word after normalising
    assert len(llm.asked) == 1 and llm.asked[0] == 'Relation: "owned by"'
    assert db.get(PredicateKind, "owned by").model == "fake:classifier"
    assert cf.predicate_kind(db, "owned by") == ("owned by", "one_subject")                    # remembered without a model


def test_a_bad_or_failed_answer_means_many_and_is_not_remembered(db):
    assert cf.predicate_kind(db, "owned by", Classifier(fail=True)) == ("owned by", "many")
    assert db.get(PredicateKind, "owned by") is None
    assert cf.predicate_kind(db, "owned by", Classifier(kind="whatever")) == ("owned by", "many")


def test_the_list_wins_over_the_model(db):
    llm = Classifier("many")
    assert cf.predicate_kind(db, "was CEO of", llm) == ("leader", "one_subject") and llm.asked == []


# ---------------------------------------------------------------- finding conflicts

@pytest.fixture
def disputes(world):
    w, db = world, world.db
    w.acme, w.quillon, w.veltra, w.soro = (w.ent(n) for n in ("Acme Corp", "Quillon Systems", "Veltra Dynamics", "Soro Labs"))
    w.maria, w.dana, w.kim, w.omar, w.imani, w.ravi = (w.ent(n, "person") for n in ("Maria Lopez", "Dana Reyes", "Kim Soto", "Omar Haddad", "Imani Okafor", "Ravi Anand"))
    w.dunmere, w.valcross, w.brindle = (w.ent(n, "place") for n in ("Dunmere", "Valcross", "Brindle"))
    # headquarters: Dunmere 2004-2012, then Valcross (a handover), and a third place that overlaps Dunmere
    w.hq1 = w.fact(w.quillon, "has its headquarters in", w.dunmere, frm="2004", to="2012", title="a")
    w.hq2 = w.fact(w.quillon, "moved its headquarters to", w.valcross, frm="2012", title="a")
    w.hq3 = w.fact(w.quillon, "is headquartered in", w.brindle, frm="2010", title="b")
    # CTOs: Maria 2012-2019, Dana 2019-2022 (handover), Kim from 2023 (after Dana), Omar from 2021 (overlaps Dana)
    w.c1 = w.fact(w.maria, "was CTO of", w.acme, frm="2012", to="2019", title="hist")
    w.c2 = w.fact(w.dana, "was CTO of", w.acme, frm="2019", to="2022", title="hist")
    w.c3 = w.fact(w.kim, "became CTO of", w.acme, frm="2023", title="news")
    w.c4 = w.fact(w.omar, "chief technology officer of", w.acme, frm="2021", title="other")
    # a value that differs, a pair written both ways round, relations that can have several
    w.e1 = w.fact(w.acme, "employs", value="340 people", title="a")
    w.e2 = w.fact(w.acme, "employs", value="400 people", title="b")
    w.r1 = w.fact(w.veltra, "acquired", w.soro, title="a")
    w.r2 = w.fact(w.soro, "acquired", w.veltra, title="b")
    w.f1 = w.fact(w.imani, "founded", w.soro, title="a")
    w.f2 = w.fact(w.ravi, "founded", w.soro, title="b")
    w.p1 = w.fact(w.veltra, "partnered with", w.acme, title="a")
    w.p2 = w.fact(w.acme, "partnered with", w.veltra, title="b")
    db.commit()
    return w


def pairs(d):
    return {frozenset((c.fact_a_id, c.fact_b_id)): c for c in d.db.execute(select(Conflict)).scalars()}


def test_the_conflicts_that_exist_and_none_of_the_look_alikes(disputes):
    d = disputes
    s = cf.run_detection(d.db, owner_id=None)
    d.db.commit()
    got = pairs(d)
    assert set(got) == {frozenset((d.hq1.id, d.hq3.id)), frozenset((d.c2.id, d.c4.id)), frozenset((d.c3.id, d.c4.id)),
                        frozenset((d.e1.id, d.e2.id)), frozenset((d.r1.id, d.r2.id)), frozenset((d.hq2.id, d.hq3.id))}
    assert s.new == 6 and s.open == 6 and s.removed == 0
    assert got[frozenset((d.hq2.id, d.hq3.id))].severity == "possible"      # Brindle since 2010 and Valcross since 2012: neither states an end
    assert got[frozenset((d.hq1.id, d.hq3.id))].kind == "different_object" and got[frozenset((d.hq1.id, d.hq3.id))].severity == "certain"
    assert got[frozenset((d.c2.id, d.c4.id))].kind == "different_holder" and got[frozenset((d.c2.id, d.c4.id))].severity == "certain"
    assert got[frozenset((d.c3.id, d.c4.id))].severity == "possible"          # neither states an end
    assert got[frozenset((d.e1.id, d.e2.id))].kind == "different_value" and got[frozenset((d.e1.id, d.e2.id))].severity == "possible"
    assert got[frozenset((d.r1.id, d.r2.id))].kind == "reversed"


def test_handovers_founders_and_symmetric_relations_are_not_conflicts(disputes):
    cf.run_detection(disputes.db, owner_id=None)
    ids = {i for p in pairs(disputes) for i in p}
    assert not ({disputes.c1.id, disputes.f1.id, disputes.f2.id, disputes.p1.id, disputes.p2.id} & ids)


def test_reasons_say_what_clashes_and_where_it_was_stated(disputes):
    d = disputes
    cf.run_detection(d.db, owner_id=None)
    c = pairs(d)[frozenset((d.hq1.id, d.hq3.id))]
    assert c.reasons[0].startswith("Both say where or what Quillon Systems is") and "2004 to 2012" in c.reasons[1] and "since 2010, no end stated" in c.reasons[1]
    assert c.reasons[2] == "stated in different documents"
    v = pairs(d)[frozenset((d.e1.id, d.e2.id))].reasons
    assert ("340 people / 400 people" in v[0] or "400 people / 340 people" in v[0]) and v[1] == "neither has a date, so they may refer to different times"
    hist = pairs(d)[frozenset((d.c2.id, d.c4.id))].reasons
    assert hist[0].startswith("Both say who “") and hist[2] == "stated in different documents"


def test_two_facts_in_one_document_are_flagged_as_possibly_misread(world):
    w = world
    a, c, p, q = w.ent("Acme"), w.ent("Dunmere", "place"), w.ent("Valcross", "place"), None
    w.fact(a, "headquartered in", c, title="same")
    w.fact(a, "headquartered in", p, title="same")
    w.db.commit()
    cf.run_detection(w.db, owner_id=None)
    assert "both in the same document (check that it was read correctly)" in w.db.execute(select(Conflict)).scalar().reasons


def test_running_again_adds_nothing_and_keeps_what_was_decided(disputes):
    d = disputes
    cf.run_detection(d.db, owner_id=None)
    c = pairs(d)[frozenset((d.e1.id, d.e2.id))]
    cf.resolve(d.db, c.id, "both")
    s = cf.run_detection(d.db, owner_id=None)
    assert s.new == 0 and s.removed == 0 and s.open == 5
    assert d.db.get(Conflict, c.id).status == ConflictStatus.DISMISSED


def test_an_open_conflict_that_no_longer_applies_is_removed(disputes):
    d = disputes
    cf.run_detection(d.db, owner_id=None)
    d.hq3.valid_from = "2013"                                   # now it began after Dunmere ended: a handover
    d.db.commit()
    s = cf.run_detection(d.db, owner_id=None)
    assert s.removed == 1 and frozenset((d.hq1.id, d.hq3.id)) not in pairs(d) and frozenset((d.hq2.id, d.hq3.id)) in pairs(d)


def test_a_relation_the_model_classified_is_used_on_the_next_run(world):
    w = world
    house, ann, bob = w.ent("Elm House", "product"), w.ent("Ann", "person"), w.ent("Bob", "person")
    w.fact(ann, "owned by", house, frm="2010", to="2020")
    w.fact(bob, "owned by", house, frm="2015", to="2022")
    w.db.commit()
    assert cf.run_detection(w.db, owner_id=None).new == 0                     # unknown word: never flagged
    llm = Classifier("one_subject")
    assert cf.run_detection(w.db, owner_id=None, llm=llm).new == 1
    assert cf.run_detection(w.db, owner_id=None).open == 1                    # and it is remembered without the model


def test_the_model_can_give_an_opinion_on_each_new_pair(disputes):
    llm = Classifier("yes")
    s = cf.run_detection(disputes.db, owner_id=None, llm=llm, judge=True)
    assert s.judged == 6 and {c.llm_verdict for c in pairs(disputes).values()} == {"yes"}
    assert any("A: Quillon Systems" in p and 'the text says: "' in p for p in llm.asked)
    again = Classifier("no")
    cf.run_detection(disputes.db, owner_id=None, llm=again, judge=True)
    assert again.asked == [] or all("Relation" in p for p in again.asked)       # an opinion already given is not asked for again


def test_an_unusable_opinion_is_none(disputes):
    class Bad(Classifier):
        def generate_json(self, system, prompt, schema, max_tokens=None):
            if system == cf.JUDGE_SYSTEM:
                raise LLMError("down")
            return super().generate_json(system, prompt, schema, max_tokens)
    cf.run_detection(disputes.db, owner_id=None, llm=Bad(), judge=True)
    assert {c.llm_verdict for c in pairs(disputes).values()} == {None}


# ---------------------------------------------------------------- settling them

def conflict_of(d, a, b):
    cf.run_detection(d.db, owner_id=None)
    d.db.commit()
    return pairs(d)[frozenset((a.id, b.id))]


def test_choosing_a_fact_leaves_the_other_out_everywhere_until_undone(disputes):
    d = disputes
    c = conflict_of(d, d.hq1, d.hq3)
    keep_a = c.fact_a_id == d.hq1.id
    cf.resolve(d.db, c.id, "keep_a" if keep_a else "keep_b")
    d.db.commit()
    loser = d.hq3.id
    assert cf.overruled_ids(d.db, None) == {loser}
    assert loser not in gq.GraphIndex(d.db).facts and d.hq1.id in gq.GraphIndex(d.db).facts
    g = graph_store.build_graph(d.db)
    assert loser not in {k for *_, k in g.edges(keys=True)}
    assert d.db.get(Fact, loser) is not None                                    # never deleted
    assert d.db.get(Conflict, c.id).status == ConflictStatus.RESOLVED
    cf.reopen(d.db, c.id)
    d.db.commit()
    assert cf.overruled_ids(d.db, None) == set() and loser in gq.GraphIndex(d.db).facts


def test_a_left_out_fact_is_not_flagged_again(disputes):
    d = disputes
    c = conflict_of(d, d.e1, d.e2)
    cf.resolve(d.db, c.id, "keep_a")
    s = cf.run_detection(d.db, owner_id=None)
    assert s.new == 0 and d.db.get(Conflict, c.id).status == ConflictStatus.RESOLVED


def test_both_true_dismisses_and_leaves_both_facts_in(disputes):
    d = disputes
    c = conflict_of(d, d.e1, d.e2)
    cf.resolve(d.db, c.id, "both")
    assert d.db.get(Conflict, c.id).status == ConflictStatus.DISMISSED and cf.overruled_ids(d.db, None) == set()
    assert {d.e1.id, d.e2.id} <= set(gq.GraphIndex(d.db).facts)


def test_the_earlier_holder_can_be_ended_when_the_later_one_began_and_it_can_be_undone(disputes):
    d = disputes
    c = conflict_of(d, d.c3, d.c4)                                              # Omar since 2021, Kim since 2023, no ends
    assert cf.succession_order(d.c3, d.c4) == (d.c4, d.c3)
    cf.resolve(d.db, c.id, "succession")
    d.db.commit()
    assert d.c4.valid_from == "2021" and d.c4.valid_to == "2023"
    assert d.db.get(Conflict, c.id).resolution == "succession" and d.db.get(Conflict, c.id).data["old_valid_to"] == ""
    cf.reopen(d.db, c.id)
    d.db.commit()
    assert d.c4.valid_to == "" and d.db.get(Conflict, c.id).status == ConflictStatus.OPEN


def test_succession_needs_two_starts_that_differ(disputes):
    d = disputes
    c = conflict_of(d, d.e1, d.e2)                                              # undated values
    with pytest.raises(cf.ConflictError, match="which came first"):
        cf.resolve(d.db, c.id, "succession")
    assert cf.succession_order(d.e1, d.e2) is None
    same = d.fact(d.imani, "led", d.acme, frm="2020", title="x"), d.fact(d.ravi, "led", d.acme, frm="2020", title="y")
    assert cf.succession_order(*same) is None


def test_succession_is_refused_when_the_earlier_one_already_ended(disputes):
    d = disputes
    assert cf.succession_order(d.c1, d.c3) is None                              # Maria ended 2019, Kim began 2023: nothing to settle


def test_succession_that_would_duplicate_a_fact_is_refused(disputes):
    d = disputes
    c = conflict_of(d, d.c3, d.c4)
    d.fact(d.omar, "chief technology officer of", d.acme, frm="2021", to="2023", title="twin")
    d.db.commit()
    with pytest.raises(cf.ConflictError, match="already exists"):
        cf.resolve(d.db, c.id, "succession")
    assert d.c4.valid_to == ""


def test_decisions_are_checked(disputes):
    d = disputes
    c = conflict_of(d, d.e1, d.e2)
    with pytest.raises(cf.ConflictError, match="must be one of"):
        cf.resolve(d.db, c.id, "shrug")
    cf.resolve(d.db, c.id, "keep_a")
    with pytest.raises(cf.ConflictError, match="already decided"):
        cf.resolve(d.db, c.id, "keep_b")
    with pytest.raises(cf.ConflictError, match="still open"):
        cf.reopen(d.db, conflict_of(d, d.hq1, d.hq3).id)
    with pytest.raises(cf.ConflictError, match="not found"):
        cf.resolve(d.db, "nope", "both")
    with pytest.raises(cf.ConflictError, match="not found"):
        cf.resolve(d.db, c.id, "both", owner_id=999)


def test_deleting_a_fact_removes_its_conflicts(disputes):
    d = disputes
    cid = conflict_of(d, d.e1, d.e2).id
    from sqlalchemy import text
    d.db.execute(text("PRAGMA foreign_keys=ON"))
    d.db.delete(d.db.get(Fact, d.e2.id))
    d.db.commit()
    d.db.expire_all()
    assert d.db.get(Conflict, cid) is None


# ---------------------------------------------------------------- answers

def asked(d, question, llm, mode="subgraph"):
    return ask_mod.ask(d.db, question, mode=mode, llm=llm, embedder=FakeEmbedder(), settings=ask_mod.Settings(_env_file=None))


def test_an_answer_built_on_conflicting_facts_says_so(disputes):
    d = disputes
    conflict_of(d, d.e1, d.e2)
    llm = ScriptedLLM(answer=lambda p: {"found": True, "answer": "340 or 400", "cited": ["F1", "F2"]})
    r = asked(d, "How many people does Acme Corp employ?", llm)
    prompt = llm.prompts["answer"][0]
    assert "contradict each other" in prompt and "say that the documents disagree" in prompt
    values = [c for c in r["conflicts"] if c["kind"] == "different_value"]
    assert len(values) == 1
    assert sorted(t for t in values[0]["texts"]) == ["Acme Corp employs 340 people", "Acme Corp employs 400 people"]


def test_a_settled_conflict_no_longer_disturbs_the_answer(disputes):
    d = disputes
    c = conflict_of(d, d.e1, d.e2)
    cf.resolve(d.db, c.id, "keep_a")
    d.db.commit()
    llm = ScriptedLLM(answer=lambda p: {"found": True, "answer": "x", "cited": ["F1"]})
    r = asked(d, "How many people does Acme Corp employ?", llm)
    prompt = llm.prompts["answer"][0]
    assert not [c for c in r.get("conflicts", []) if c["kind"] == "different_value"]
    assert ("340" in prompt) != ("400" in prompt)                               # only the fact that was kept is shown


def test_questions_without_conflicts_have_no_conflict_field(disputes):
    llm = ScriptedLLM(answer=lambda p: {"found": True, "answer": "x", "cited": ["F1"]})
    assert "conflicts" not in asked(disputes, "Who founded Soro Labs?", llm)


# ---------------------------------------------------------------- the API

@pytest.fixture
def client(factory, disputes, monkeypatch):
    import server

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    server.app.dependency_overrides[get_db] = override
    monkeypatch.setattr("src.api.conflicts.get_settings", lambda: config.Settings(_env_file=None))
    monkeypatch.setattr("src.api.conflicts.get_embedder", lambda settings=None: FakeEmbedder())
    c = TestClient(server.app)
    c.d = disputes
    yield c
    server.app.dependency_overrides.clear()


def test_run_then_list(client):
    r = client.post("/api/conflicts/run")
    assert r.status_code == 200 and r.json() == {"new": 6, "removed": 0, "open": 6, "judged": 0}
    body = client.get("/api/conflicts").json()["conflicts"]
    assert len(body) == 6 and [c["severity"] for c in body] == sorted(c["severity"] for c in body)
    c = next(c for c in body if c["kind"] == "different_object")
    assert c["status"] == "open" and {c["a"]["text"], c["b"]["text"]} == {"Quillon Systems has its headquarters in Dunmere", "Quillon Systems is headquartered in Brindle"}
    assert {(c["a"]["valid_from"], c["a"]["valid_to"]), (c["b"]["valid_from"], c["b"]["valid_to"])} == {("2004", "2012"), ("2010", None)}
    assert c["a"]["sources"][0]["quote"] and c["reasons"] and c["resolution"] is None and c["llm_verdict"] is None


def test_list_filters_by_status_and_checks_it(client):
    client.post("/api/conflicts/run")
    assert client.get("/api/conflicts?status=resolved").json() == {"conflicts": []}
    assert client.get("/api/conflicts?status=nonsense").status_code == 422


def test_resolve_and_reopen_over_http(client):
    client.post("/api/conflicts/run")
    c = next(c for c in client.get("/api/conflicts").json()["conflicts"] if c["kind"] == "different_value")
    r = client.post(f"/api/conflicts/{c['id']}/resolve", json={"resolution": "keep_a"})
    assert r.status_code == 200 and r.json()["status"] == "resolved" and r.json()["resolution"] == "keep_a"
    assert client.post(f"/api/conflicts/{c['id']}/resolve", json={"resolution": "keep_b"}).status_code == 409
    assert len(client.get("/api/conflicts?status=resolved").json()["conflicts"]) == 1
    assert client.get("/api/graph/stats").json()["facts"] == 14                  # 15 facts, one left out
    r = client.post(f"/api/conflicts/{c['id']}/reopen")
    assert r.status_code == 200 and r.json()["status"] == "open"
    assert client.get("/api/graph/stats").json()["facts"] == 15
    assert client.post(f"/api/conflicts/{c['id']}/reopen").status_code == 409


def test_resolve_errors(client):
    client.post("/api/conflicts/run")
    c = client.get("/api/conflicts").json()["conflicts"][0]
    assert client.post(f"/api/conflicts/{c['id']}/resolve", json={"resolution": "shrug"}).status_code == 422
    assert client.post("/api/conflicts/nope/resolve", json={"resolution": "both"}).status_code == 404
    assert client.post("/api/conflicts/nope/reopen").status_code == 404
    assert client.post(f"/api/conflicts/{c['id']}/resolve", json={}).status_code == 422


def test_the_entity_timeline_and_detail_leave_out_a_fact_that_lost(client):
    d = client.d
    client.post("/api/conflicts/run")
    c = next(c for c in client.get("/api/conflicts").json()["conflicts"] if c["kind"] == "different_value")
    client.post(f"/api/conflicts/{c['id']}/resolve", json={"resolution": "keep_a"})
    kept = c["a"]["text"]
    detail = client.get(f"/api/entities/{d.acme.id}").json()
    employs = [f["object"] for f in detail["outgoing"] if f["predicate"] == "employs"]
    assert employs == [kept.split("employs ")[1]]
    tl = client.get(f"/api/entities/{d.acme.id}/timeline").json()
    assert len([f for f in tl["facts"] if f["predicate"] == "employs"]) == 1


def test_a_run_with_the_model_judges_pairs(client, monkeypatch):
    monkeypatch.setattr("src.api.conflicts.get_llm", lambda settings=None: Classifier("yes"))
    assert client.post("/api/conflicts/run", json={"use_llm": True}).json()["judged"] == 6
    assert {c["llm_verdict"] for c in client.get("/api/conflicts").json()["conflicts"]} == {"yes"}


def test_a_run_with_an_unreachable_model_says_so(client, monkeypatch):
    def broken(settings=None):
        raise LLMError("Ollama is not running")
    monkeypatch.setattr("src.api.conflicts.get_llm", broken)
    r = client.post("/api/conflicts/run", json={"use_llm": True})
    assert r.status_code == 503 and "Ollama" in r.json()["detail"]


def test_a_fact_says_which_open_conflicts_it_is_in_and_whether_it_was_left_out(client):
    d = client.d
    client.post("/api/conflicts/run")
    fact = client.get(f"/api/facts/{d.e1.id}").json()
    assert fact["left_out"] is False and len(fact["conflicts"]) == 1
    c = fact["conflicts"][0]
    assert c["kind"] == "different_value" and c["other"]["text"] == "Acme Corp employs 400 people"
    assert client.get(f"/api/facts/{d.f1.id}").json()["conflicts"] == []
    cid = c["id"]
    keep = "keep_a" if client.get("/api/conflicts").json()["conflicts"] and next(x for x in client.get("/api/conflicts").json()["conflicts"] if x["id"] == cid)["a"]["id"] == d.e1.id else "keep_b"
    client.post(f"/api/conflicts/{cid}/resolve", json={"resolution": keep})
    after = client.get(f"/api/facts/{d.e2.id}").json()
    assert after["left_out"] is True and after["conflicts"] == []
    assert client.get(f"/api/facts/{d.e1.id}").json()["left_out"] is False
