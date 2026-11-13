import pytest
from sqlalchemy import func, select

from src.core.config import Settings
from src.models.graph import Chunk, Document, DocumentStatus, Entity, Fact, FactSource
from src.models.resolution import EntityAlias, MergeRecord, MergeSuggestion, SuggestionStatus
from src.services import pipeline, resolution
from src.services.resolution import (EntityInfo, MergeError, canonical_tokens, decide, id_tokens, initials_of, qualifier_of)
from tests.conftest import FakeLLM, rel


def info(name, etype="organization", i=None, **kw):
    return EntityInfo(i or name, name, etype, canonical_tokens(name, etype), qualifier_of(name, etype), initials_of(name, etype), **kw)


# ---------------------------------------------------------------- names

@pytest.mark.parametrize("name,etype,expected", [
    ("Acme Corp", "organization", ["acme"]),
    ("The Acme Company", "organization", ["acme"]),
    ("ACME, Inc.", "organization", ["acme"]),
    ("Corp", "organization", ["corp"]),                                  # never stripped to nothing
    ("Acme Corp", "person", ["acme", "corp"]),                           # suffixes only come off organizations
    ("Dr. Alan M. Turing", "person", ["alan", "turing"]),
    ("King Henric III of Vestland", "person", ["henric", "iii"]),
    ("King Henric III of Vestland", "place", ["king", "henric", "iii", "of", "vestland"]),
    ("ETH Zürich", "organization", ["eth", "zurich"]),
    ("Widget-X", "product", ["widget", "x"]),
    ("A. Turing", "person", ["turing"]),
])
def test_canonical_tokens(name, etype, expected):
    assert canonical_tokens(name, etype) == expected


def test_id_tokens_and_helpers():
    assert id_tokens(["widget", "x"], "product") == {"x"}
    assert id_tokens(["henric", "iii"], "person") == {"iii"}
    assert id_tokens(["apollo", "11"], "product") == {"11"}
    assert id_tokens(["alan", "m", "turing"], "person") == frozenset()      # a middle initial is not an identifier
    assert id_tokens(["civic", "center"], "place") == frozenset()
    assert initials_of("Alan M. Turing", "person") == ["m"] and initials_of("Alan M. Turing", "organization") == []
    assert qualifier_of("Henric III of Vestland", "person") == ("vestland",) and qualifier_of("Of Mice", "person") == ()


# ---------------------------------------------------------------- decisions

@pytest.mark.parametrize("a,b,ta,tb,kind", [
    ("Acme Corp", "Acme Inc.", "organization", "organization", "auto"),
    ("Acme Corp", "ACME", "organization", "organization", "auto"),
    ("ETH Zurich", "ETH Zürich", "organization", "organization", "auto"),
    ("Alan M. Turing", "Alan Turing", "person", "person", "auto"),
    ("Henric III", "King Henric III of Vestland", "person", "person", "auto"),
    ("Acme", "Acme", "concept", "organization", "auto"),                         # a vague type fits any type
    ("Widget-X", "Widget-W", "product", "product", "never"),
    ("Henric II", "Henric III", "person", "person", "never"),
    ("Henric III of Vestland", "Henric III of Karelia", "person", "person", "never"),
    ("Apollo 11", "Apollo 13", "event", "event", "never"),
    ("Oslo", "Oslo", "place", "organization", "never"),
    ("Windows", "Windows 11", "product", "product", "never"),
    ("B. Turing", "Alan Turing", "person", "person", "never"),
    ("A. Turing", "Alan Turing", "person", "person", "suggest"),
    ("Turing", "Alan Turing", "person", "person", "suggest"),
    ("Acme", "Acme Labs", "organization", "organization", "suggest"),
    ("IBM", "International Business Machines", "organization", "organization", "suggest"),
    ("MIT", "Massachusetts Institute of Technology", "organization", "organization", "suggest"),
    ("Nordwind Robotics", "Nordwin Robotics", "organization", "organization", "suggest"),
    ("Acme", "Beta", "organization", "organization", "none"),
    ("Ana", "Anna", "person", "person", "none"),                                  # short names differ by too much to count as alike
])
def test_decisions(a, b, ta, tb, kind):
    assert decide(info(a, ta, "1"), info(b, tb, "2")).kind == kind


def test_a_fact_between_two_entities_means_they_are_different():
    a, b = info("Acme", i="1"), info("Acme Corp", i="2", neighbors=frozenset({"1"}))
    d = decide(a, b)
    assert d.kind == "never" and "links" in d.reasons[0]


def test_same_document_surname_is_merged_only_when_unambiguous_and_for_people():
    turing, full = info("Turing", "person", "1", docs=frozenset({"d1"})), info("Alan Turing", "person", "2", docs=frozenset({"d1"}))
    assert decide(turing, full).kind == "auto" and decide(turing, full).score == 0.9
    other_doc = info("Alan Turing", "person", "2", docs=frozenset({"d2"}))
    assert decide(turing, other_doc).kind == "suggest"
    assert decide(turing, full, ambiguous_with=1, ambiguity_names=["Bob Turing"]).kind == "suggest"
    assert decide(turing, full, same_document_rule=False).kind == "suggest"
    acme, labs = info("Acme", i="1", docs=frozenset({"d1"})), info("Acme Labs", i="2", docs=frozenset({"d1"}))
    assert decide(acme, labs).kind == "suggest"  # companies are never merged on a shared word alone


def test_ambiguity_lowers_the_score_and_names_the_alternatives():
    plain = decide(info("Brandt", "person", "1"), info("Jonas Brandt", "person", "2"))
    amb = decide(info("Brandt", "person", "1"), info("Jonas Brandt", "person", "2"), ambiguous_with=1, ambiguity_names=["Elena Brandt"])
    assert plain.score == 0.75 and amb.score == 0.5 and "Elena Brandt" in amb.reasons[-1]
    too_amb = decide(info("Acme", i="1"), info("Acme Labs", i="2"), ambiguous_with=1, ambiguity_names=["Acme Group"])
    assert too_amb.kind == "none"  # 0.55 - 0.25 is below the bar


def test_shared_links_raise_the_score_up_to_a_limit():
    links = lambda n: frozenset(("acquired", "out", f"x{i}") for i in range(n))  # noqa: E731
    base = decide(info("Acme", i="1"), info("Acme Labs", i="2")).score
    one = decide(info("Acme", i="1", links=links(1)), info("Acme Labs", i="2", links=links(1)))
    five = decide(info("Acme", i="1", links=links(5)), info("Acme Labs", i="2", links=links(5)))
    assert base == 0.55 and one.score == pytest.approx(0.70) and five.score == pytest.approx(0.85)
    assert "shared link" in one.reasons[-1]


def test_fuzzy_spelling_needs_enough_letters_and_a_high_ratio():
    assert decide(info("Nordwind Robotics", i="1"), info("Nordwin Robotics", i="2")).kind == "suggest"
    assert decide(info("Nordwind Robotics", i="1"), info("Nordwind Logistics", i="2")).kind == "none"


# ---------------------------------------------------------------- database helpers

@pytest.fixture
def world(db):
    doc = Document(title="D", text="x" * 50, char_count=50, status=DocumentStatus.COMPLETED)
    db.add(doc)
    db.flush()
    chunk = Chunk(document_id=doc.id, index=0, start=0, end=50, text="x" * 50)
    db.add(chunk)
    db.commit()

    class W:
        pass
    w = W()
    w.doc, w.chunk, w.db = doc.id, chunk.id, db

    def ent(name, etype="organization"):
        e = Entity(name=name, key=resolution.entity_key(name), type=etype)
        db.add(e)
        db.flush()
        return e

    def fact(s, p, o=None, value="", frm="", to="", quote=None, doc=None, chunk=None, id=None):
        f = Fact(subject_id=s.id, predicate=p, object_id=o.id if o else None, object_value=value, valid_from=frm, valid_to=to,
                 **({"id": id} if id else {}))
        db.add(f)
        db.flush()
        db.add(FactSource(fact_id=f.id, document_id=doc or w.doc, chunk_id=chunk or w.chunk, evidence=quote or f"{s.name} {p} {o.name if o else value}"))
        db.flush()
        return f

    w.ent, w.fact = ent, fact
    return w


def snapshot(db):
    return {
        "entities": sorted((e.id, e.name, e.key, e.type) for e in db.execute(select(Entity)).scalars()),
        "facts": sorted((f.id, f.subject_id, f.predicate, f.object_id, f.object_value, f.valid_from, f.valid_to) for f in db.execute(select(Fact)).scalars()),
        "sources": sorted((s.id, s.fact_id, s.chunk_id, s.evidence) for s in db.execute(select(FactSource)).scalars()),
        "aliases": sorted((a.entity_id, a.key, a.name) for a in db.execute(select(EntityAlias)).scalars()),
    }


# ---------------------------------------------------------------- merging

def test_merge_moves_facts_collapses_copies_and_keeps_every_source(world):
    db = world.db
    acme, acme_corp, beta, gamma = (world.ent(n) for n in ("ACME", "Acme Corp", "Beta", "Gamma"))
    f1 = world.fact(acme_corp, "acquired", beta, quote="Acme Corp acquired Beta.")
    f2 = world.fact(acme, "acquired", beta, quote="ACME bought Beta.")              # same statement, other wording
    f3 = world.fact(acme, "founded in", value="2010")
    f4 = world.fact(gamma, "supplies", acme)
    rec = resolution.merge_entities(db, acme_corp.id, acme.id, "manual")
    db.commit()
    assert db.get(Entity, acme.id) is None
    assert {(f.subject.name, f.predicate, f.object.name if f.object else f.object_value) for f in db.execute(select(Fact)).scalars()} == {
        ("Acme Corp", "acquired", "Beta"), ("Acme Corp", "founded in", "2010"), ("Gamma", "supplies", "Acme Corp")}
    survivor = db.execute(select(Fact).where(Fact.predicate == "acquired")).scalar_one()
    assert sorted(s.evidence for s in survivor.sources) == ["ACME bought Beta.", "Acme Corp acquired Beta."]
    assert db.execute(select(EntityAlias.name)).scalars().all() == ["ACME"]
    assert rec.how == "manual" and rec.keep_name == "Acme Corp" and rec.absorbed_name == "ACME"


def test_merge_prefers_the_dated_copy_and_keeps_different_periods(world):
    db = world.db
    a, b, c = world.ent("Acme"), world.ent("Acme Corp"), world.ent("Beta")
    world.fact(a, "acquired", c, id="a1")                           # undated (and sorts first by id)
    world.fact(b, "acquired", c, frm="2020-03", id="b2")            # dated
    world.fact(a, "worked with", c, frm="2010")
    world.fact(b, "worked with", c, frm="2015")                     # a different period: stays a different fact
    resolution.merge_entities(db, b.id, a.id)
    db.commit()
    acquired = db.execute(select(Fact).where(Fact.predicate == "acquired")).scalars().all()
    assert len(acquired) == 1 and acquired[0].valid_from == "2020-03" and len(acquired[0].sources) == 2
    assert db.scalar(select(func.count()).select_from(Fact).where(Fact.predicate == "worked with")) == 2


def test_merge_refuses_unsafe_requests(world):
    db = world.db
    a, b, person = world.ent("Acme"), world.ent("Acme Corp"), world.ent("Acme", "person") if False else world.ent("Ann", "person")
    world.fact(a, "owns", b)
    with pytest.raises(MergeError, match="links"):
        resolution.merge_entities(db, a.id, b.id)
    with pytest.raises(MergeError, match="types"):
        resolution.merge_entities(db, a.id, person.id)
    with pytest.raises(MergeError, match="itself"):
        resolution.merge_entities(db, a.id, a.id)
    with pytest.raises(MergeError, match="not found"):
        resolution.merge_entities(db, a.id, "nope")
    assert db.scalar(select(func.count()).select_from(Entity)) == 3


def test_merge_takes_the_more_specific_type_and_a_chosen_name(world):
    db = world.db
    vague, specific = world.ent("Acme", "concept"), world.ent("Acme Corp", "organization")
    resolution.merge_entities(db, vague.id, specific.id, new_name="Acme Corporation")
    db.commit()
    e = db.get(Entity, vague.id)
    assert e.type == "organization" and e.name == "Acme Corporation"


def test_merge_moves_aliases_of_the_absorbed_entity(world):
    db = world.db
    a, b, c = world.ent("Acme"), world.ent("Acme Corp"), world.ent("ACME Group")
    resolution.merge_entities(db, b.id, a.id)
    resolution.merge_entities(db, c.id, b.id)  # b already has the alias 'Acme'; it must follow
    db.commit()
    assert sorted(db.execute(select(EntityAlias.name)).scalars().all()) == ["Acme", "Acme Corp"]
    assert {x.entity_id for x in db.execute(select(EntityAlias)).scalars()} == {c.id}


# ---------------------------------------------------------------- undo

def test_undo_restores_exactly_what_was_there(world):
    db = world.db
    acme, acme_corp, beta, gamma = (world.ent(n) for n in ("ACME", "Acme Corp", "Beta", "Gamma"))
    world.fact(acme_corp, "acquired", beta, quote="Acme Corp acquired Beta.")
    world.fact(acme, "acquired", beta, quote="ACME bought Beta.")
    world.fact(acme_corp, "bought", beta, quote="same quote")
    world.fact(acme, "bought", beta, quote="same quote")                              # identical quote on both copies
    world.fact(acme, "founded in", value="2010")
    world.fact(gamma, "supplies", acme)
    db.commit()
    before = snapshot(db)
    rec = resolution.merge_entities(db, acme_corp.id, acme.id)
    db.commit()
    assert snapshot(db) != before
    resolution.undo_merge(db, rec.id)
    db.commit()
    assert snapshot(db) == before
    assert db.get(MergeRecord, rec.id).undone_at is not None


def test_undo_with_a_name_change_and_type_upgrade(world):
    db = world.db
    a, b = world.ent("Turing", "concept"), world.ent("Alan Turing", "person")
    world.fact(a, "worked at", world.ent("Bletchley Park", "place"))
    db.commit()
    before = snapshot(db)
    rec = resolution.merge_entities(db, a.id, b.id, new_name="Alan Turing")
    db.commit()
    assert db.get(Entity, a.id).name == "Alan Turing" and db.get(Entity, a.id).type == "person"
    resolution.undo_merge(db, rec.id)
    db.commit()
    assert snapshot(db) == before


def test_undo_refusals(world):
    db = world.db
    a, b = world.ent("Acme"), world.ent("Acme Corp")
    rec = resolution.merge_entities(db, b.id, a.id)
    db.commit()
    with pytest.raises(MergeError, match="not found"):
        resolution.undo_merge(db, "nope")
    resolution.undo_merge(db, rec.id)
    with pytest.raises(MergeError, match="already undone"):
        resolution.undo_merge(db, rec.id)
    rec2 = resolution.merge_entities(db, b.id, a.id)
    db.add(Entity(name="Acme again", key="acme", type="organization"))   # the old name is taken again
    db.flush()
    with pytest.raises(MergeError, match="exists again"):
        resolution.undo_merge(db, rec2.id)
    db.rollback()


def test_undo_when_the_kept_entity_is_gone(world):
    db = world.db
    a, b = world.ent("Acme"), world.ent("Acme Corp")
    rec = resolution.merge_entities(db, b.id, a.id)
    db.commit()
    db.delete(db.get(Entity, b.id))
    db.commit()
    with pytest.raises(MergeError, match="no longer exists"):
        resolution.undo_merge(db, rec.id)


def test_undo_skips_facts_deleted_in_the_meantime(world):
    db = world.db
    a, b, c = world.ent("Acme"), world.ent("Acme Corp"), world.ent("Beta")
    f = world.fact(a, "acquired", c)
    rec = resolution.merge_entities(db, b.id, a.id)
    db.commit()
    db.delete(db.get(Fact, f.id))
    db.commit()
    resolution.undo_merge(db, rec.id)
    db.commit()
    assert db.get(Entity, a.id) is not None and db.scalar(select(func.count()).select_from(Fact)) == 0


# ---------------------------------------------------------------- finding candidates

def test_candidate_pairs_are_found_by_shared_word_acronym_and_spelling_but_not_everything(world):
    db = world.db
    names = ["Acme Corp", "Acme Labs", "IBM", "International Business Machines", "Nordwind Robotics", "Nordwin Robotics",
             "Orbis Logistics", "Zeta Foods"]
    ents = {n: world.ent(n) for n in names}
    db.commit()
    infos = resolution.load_infos(db)
    pairs = resolution.candidate_pairs(infos)
    idp = lambda a, b: tuple(sorted((ents[a].id, ents[b].id)))  # noqa: E731
    assert idp("Acme Corp", "Acme Labs") in pairs and idp("IBM", "International Business Machines") in pairs
    assert idp("Nordwind Robotics", "Nordwin Robotics") in pairs
    assert idp("Orbis Logistics", "Zeta Foods") not in pairs and idp("Acme Corp", "IBM") not in pairs


def test_load_infos_counts_facts_documents_and_links(world):
    db = world.db
    a, b = world.ent("Acme"), world.ent("Beta")
    world.fact(a, "owns", b)
    world.fact(a, "founded in", value="2010")
    db.commit()
    infos = resolution.load_infos(db)
    assert infos[a.id].n_facts == 2 and infos[b.id].n_facts == 1
    assert infos[a.id].docs == {world.doc} and infos[a.id].neighbors == {b.id} and ("owns", "out", b.id) in infos[a.id].links
    assert ("owns", "in", a.id) in infos[b.id].links


# ---------------------------------------------------------------- the run

def test_run_merges_safe_pairs_and_suggests_unsure_ones(world):
    db = world.db
    acme, acme_corp, labs, ibm, full = (world.ent(n) for n in ("ACME", "Acme Corp", "Acme Labs", "IBM", "International Business Machines"))
    beta = world.ent("Beta")
    for e in (acme, acme_corp, labs, ibm, full):
        world.fact(e, "partnered with", beta)
    db.commit()
    s = resolution.run_resolution(db)
    db.commit()
    assert s.auto_merged == 1 and s.merges[0]["kept"] == "Acme Corp" and s.merges[0]["absorbed"] == "ACME"
    pairs = {frozenset((x.entity_a_id, x.entity_b_id)) for x in db.execute(select(MergeSuggestion)).scalars()}
    assert frozenset((acme_corp.id, labs.id)) in pairs and frozenset((ibm.id, full.id)) in pairs
    assert db.get(Entity, acme.id) is None


def test_run_is_repeatable(world):
    db = world.db
    a, b, c = world.ent("Acme"), world.ent("Acme Labs"), world.ent("Beta")
    world.fact(a, "x", c), world.fact(b, "x", c)
    db.commit()
    first = resolution.run_resolution(db)
    db.commit()
    second = resolution.run_resolution(db)
    db.commit()
    assert first.suggestions_new == 1 and second.suggestions_new == 0 and second.suggestions_updated == 1
    assert db.scalar(select(func.count()).select_from(MergeSuggestion)) == 1


def test_run_without_auto_only_suggests(world):
    db = world.db
    world.ent("ACME"), world.ent("Acme Corp")
    db.commit()
    s = resolution.run_resolution(db, auto=False)
    assert s.auto_merged == 0 and db.scalar(select(func.count()).select_from(Entity)) == 2


def test_rejected_pairs_are_never_suggested_again(world):
    db = world.db
    a, b = world.ent("Acme"), world.ent("Acme Labs")
    db.commit()
    resolution.run_resolution(db)
    sug = db.execute(select(MergeSuggestion)).scalar_one()
    resolution.reject_suggestion(db, sug.id)
    db.commit()
    s = resolution.run_resolution(db)
    db.commit()
    assert s.suggestions_new == 0 and db.execute(select(MergeSuggestion)).scalar_one().status == SuggestionStatus.REJECTED
    with pytest.raises(MergeError, match="already rejected"):
        resolution.reject_suggestion(db, sug.id)
    with pytest.raises(MergeError, match="already rejected"):
        resolution.accept_suggestion(db, sug.id)


def test_accepting_a_suggestion_merges_and_can_choose_the_survivor(world):
    db = world.db
    a, b = world.ent("Acme"), world.ent("Acme Labs")
    db.commit()
    resolution.run_resolution(db)
    sug = db.execute(select(MergeSuggestion)).scalar_one()
    rec = resolution.accept_suggestion(db, sug.id, keep_id=a.id)
    db.commit()
    assert rec.how == "suggestion" and rec.keep_name == "Acme" and db.get(Entity, b.id) is None
    with pytest.raises(MergeError, match="not found"):
        resolution.accept_suggestion(db, "nope")


def test_accept_with_a_foreign_keep_id_is_refused(world):
    db = world.db
    a, b, other = world.ent("Acme"), world.ent("Acme Labs"), world.ent("Beta")
    db.commit()
    resolution.run_resolution(db)
    sug = db.execute(select(MergeSuggestion)).scalar_one()
    with pytest.raises(MergeError, match="one of the two"):
        resolution.accept_suggestion(db, sug.id, keep_id=other.id)


def test_suggestions_that_stop_being_candidates_are_dropped(world):
    db = world.db
    a, b = world.ent("Acme"), world.ent("Acme Labs")
    db.commit()
    resolution.run_resolution(db)
    world.fact(a, "owns", b)   # now a fact links them
    db.commit()
    s = resolution.run_resolution(db)
    db.commit()
    assert s.suggestions_dropped == 1 and s.blocked == 1 and db.scalar(select(func.count()).select_from(MergeSuggestion)) == 0


def test_choose_keep_prefers_the_fuller_name_then_more_facts():
    full, short = info("Alan Turing", "person", "1", n_facts=1), info("Turing", "person", "2", n_facts=9)
    assert resolution.choose_keep(short, full)[0].id == "1"
    big, small = info("Acme Corp", i="1", n_facts=5), info("Acme Inc.", i="2", n_facts=2)
    assert resolution.choose_keep(small, big)[0].id == "1"
    upper, mixed = info("ACME", i="1", n_facts=3), info("Acme", i="2", n_facts=3)
    assert resolution.choose_keep(upper, mixed)[0].id == "2"


# ---------------------------------------------------------------- the model's second opinion

def judge(answers):
    it = iter(answers)

    def f(prompt):
        a = next(it)
        if isinstance(a, Exception):
            raise a
        return {"same": a}
    return f


class JudgeLLM(FakeLLM):
    def __init__(self, answers):
        super().__init__()
        self.answers = iter(answers)
        self.prompts = []

    def generate_json(self, system, prompt, schema):
        self.prompts.append(prompt)
        a = next(self.answers)
        if isinstance(a, Exception):
            raise a
        return {"same": a}


def test_model_opinion_moves_the_score_and_is_remembered(world):
    db = world.db
    a, b, beta = world.ent("Acme"), world.ent("Acme Labs"), world.ent("Beta")
    world.fact(a, "acquired", beta)
    db.commit()
    llm = JudgeLLM(["yes"])
    s = resolution.run_resolution(db, llm=llm)
    db.commit()
    sug = db.execute(select(MergeSuggestion)).scalar_one()
    assert s.judged == 1 and sug.llm_verdict == "yes" and sug.score == pytest.approx(0.75)
    assert "Acme acquired Beta" in llm.prompts[0] and "Entity 1: " in llm.prompts[0]
    again = resolution.run_resolution(db, llm=JudgeLLM([]))   # would raise StopIteration if it asked again
    db.commit()
    assert again.judged == 0 and db.execute(select(MergeSuggestion)).scalar_one().score == pytest.approx(0.75)


def test_model_saying_no_only_demotes_and_can_drop_a_borderline_suggestion_and_failures_are_ignored(world):
    db = world.db
    world.ent("Acme"), world.ent("Acme Labs")
    db.commit()
    resolution.run_resolution(db, llm=JudgeLLM(["no"]))
    db.commit()
    assert db.scalar(select(func.count()).select_from(MergeSuggestion)) == 0     # 0.55 * 0.85 is just below the bar
    from src.services.llm import LLMError, LLMBadOutput
    for err in (LLMError("down"), LLMBadOutput("junk")):
        resolution.run_resolution(db, llm=JudgeLLM([err]))
        db.commit()
        sug = db.execute(select(MergeSuggestion)).scalar_one()
        assert sug.llm_verdict is None and sug.score == pytest.approx(0.55)
        db.delete(sug)
        db.commit()


def test_apply_verdict():
    assert resolution.apply_verdict(0.7, "yes") == pytest.approx(0.9) and resolution.apply_verdict(0.95, "yes") == 0.99
    assert resolution.apply_verdict(0.8, "no") == pytest.approx(0.68) and resolution.apply_verdict(0.7, None) == 0.7


def test_a_clearly_good_suggestion_survives_the_model_saying_no(world):
    db = world.db
    world.ent("Turing", "person"), world.ent("Alan Turing", "person")
    db.commit()
    resolution.run_resolution(db, llm=JudgeLLM(["no"]))
    db.commit()
    sug = db.execute(select(MergeSuggestion)).scalar_one()
    assert sug.llm_verdict == "no" and sug.score == pytest.approx(0.6375, abs=1e-3)


def test_junk_model_answers_count_as_no_answer(world):
    db = world.db
    world.ent("Acme"), world.ent("Acme Labs")
    db.commit()
    resolution.run_resolution(db, llm=JudgeLLM(["maybe"]))
    db.commit()
    assert db.execute(select(MergeSuggestion)).scalar_one().llm_verdict is None


# ---------------------------------------------------------------- inside the pipeline

TEXT = "ACME bought Beta Systems in 2020. Acme Corp was founded in 2010 by Maria Lopez."


def read(db, text, raws, **kw):
    d = Document(title="t", text=text, char_count=len(text))
    db.add(d)
    db.commit()
    s = Settings(_env_file=None, verify_facts=False, gleaning_passes=0, **kw)
    pipeline.process_document(d.id, FakeLLM(extract=lambda p: {"relations": raws}), s)
    db.expire_all()  # the pipeline used its own session
    return d.id


RAWS = [rel("ACME", "bought", "Beta Systems", "ACME bought Beta Systems in 2020.", "2020", otype="organization", stype="organization"),
        rel("Maria Lopez", "founded", "Acme Corp", "Acme Corp was founded in 2010 by Maria Lopez.", "2010", otype="organization")]


def test_documents_are_resolved_after_reading(factory, db):
    doc_id = read(db, TEXT, RAWS)
    names = sorted(e.name for e in db.execute(select(Entity)).scalars())
    assert names == ["Acme Corp", "Beta Systems", "Maria Lopez"]
    assert db.get(Document, doc_id).stats["resolution"]["auto_merged"] == 1
    assert db.execute(select(EntityAlias.name)).scalars().all() == ["ACME"]
    assert {(f.subject.name, f.predicate) for f in db.execute(select(Fact)).scalars()} == {("Acme Corp", "bought"), ("Maria Lopez", "founded")}


def test_auto_resolve_can_be_switched_off(factory, db):
    read(db, TEXT, RAWS, auto_resolve=False)
    assert db.scalar(select(func.count()).select_from(Entity)) == 4


def test_a_merged_name_in_a_later_document_lands_on_the_same_entity(factory, db):
    read(db, TEXT, RAWS)
    later = [rel("ACME", "hired", "Dana Reyes", "ACME hired Dana Reyes in 2022.", "2022", otype="person", stype="organization")]
    read(db, "ACME hired Dana Reyes in 2022.", later)
    assert db.scalar(select(func.count()).select_from(Entity).where(Entity.name.in_(["ACME", "Acme Corp"]))) == 1
    acme = db.execute(select(Entity).where(Entity.name == "Acme Corp")).scalar_one()
    assert {f.predicate for f in db.execute(select(Fact).where(Fact.subject_id == acme.id)).scalars()} == {"bought", "hired"}


def test_a_crash_in_resolution_does_not_fail_the_document(factory, db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(pipeline, "run_resolution", boom)
    doc_id = read(db, TEXT, RAWS)
    d = db.get(Document, doc_id)
    assert d.status == DocumentStatus.COMPLETED and "resolution" not in d.stats
    assert db.scalar(select(func.count()).select_from(Fact)) == 2


def test_a_word_shared_by_hundreds_of_names_does_not_create_pairs():
    infos = {f"e{i}": info(f"University of Place{chr(97 + i % 26)}{i}", i=f"e{i}") for i in range(201)}
    infos.update({"x1": info("University of Oslo", i="x1"), "x2": info("Oslo University Hospital", i="x2")})
    pairs = resolution.candidate_pairs(infos)
    assert ("e0", "e1") not in pairs and not any("e0" in p for p in pairs if "x1" in p)
    few = {"a": info("University of Oslo", i="a"), "b": info("Oslo University Hospital", i="b"), "c": info("Zeta Foods", i="c")}
    assert ("a", "b") in resolution.candidate_pairs(few) and not any("c" in p for p in resolution.candidate_pairs(few))


def test_undo_after_an_undated_fact_was_folded_into_a_dated_one(world):
    db = world.db
    absorbed, keep, beta, gamma = world.ent("Acme"), world.ent("Acme Corp"), world.ent("Beta"), world.ent("Gamma")
    world.fact(absorbed, "acquired", beta, id="a1")                        # undated, moves to keep, then folds into the dated one
    world.fact(keep, "acquired", beta, frm="2020-03", id="b2")
    world.fact(gamma, "owns", absorbed, id="a3")                           # absorbed as the object
    world.fact(gamma, "owns", keep, frm="2019", id="b4")
    db.commit()
    before = snapshot(db)
    rec = resolution.merge_entities(db, keep.id, absorbed.id)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Fact)) == 2
    resolution.undo_merge(db, rec.id)
    db.commit()
    assert snapshot(db) == before


def test_merging_in_a_chain_still_undoes_in_reverse_order(world):
    db = world.db
    a, b, c, beta = world.ent("Acme"), world.ent("Acme Corp"), world.ent("Acme Group"), world.ent("Beta")
    world.fact(a, "x", beta), world.fact(b, "y", beta), world.fact(c, "z", beta)
    db.commit()
    s0 = snapshot(db)
    r1 = resolution.merge_entities(db, b.id, a.id)
    db.commit()
    s1 = snapshot(db)
    r2 = resolution.merge_entities(db, c.id, b.id)
    db.commit()
    resolution.undo_merge(db, r2.id)
    db.commit()
    assert snapshot(db) == s1
    resolution.undo_merge(db, r1.id)
    db.commit()
    assert snapshot(db) == s0


# ---------------------------------------------------------------- pair decisions inside a whole graph

def test_a_surname_matches_one_full_name_even_when_that_name_is_written_two_ways():
    infos = {"t": info("Turing", "person", "t", docs=frozenset({"d1"})),
             "a": info("Alan Turing", "person", "a", docs=frozenset({"d1"})),
             "b": info("Dr. Alan Turing", "person", "b", docs=frozenset({"d2"}))}
    d = resolution.evaluate(infos)
    assert d[("a", "b")].kind == "auto" and d[("a", "t")].kind == "auto"   # two spellings of one name count as one candidate
    assert d[("b", "t")].kind == "suggest"                                  # not in the same document as the short name


def test_a_surname_with_two_different_full_names_is_only_suggested():
    infos = {"t": info("Turing", "person", "t", docs=frozenset({"d1"})), "a": info("Alan Turing", "person", "a", docs=frozenset({"d1"})),
             "b": info("Bob Turing", "person", "b", docs=frozenset({"d1"}))}
    d = resolution.evaluate(infos)
    assert d[("a", "t")].kind == "suggest" and d[("b", "t")].kind == "suggest" and d[("a", "t")].score == 0.5


def test_same_document_rule_needs_a_one_word_name():
    infos = {"s": info("Alan Turing", "person", "s", docs=frozenset({"d1"})),
             "l": info("Alan Mathison Turing", "person", "l", docs=frozenset({"d1"}))}
    assert resolution.evaluate(infos)[("l", "s")].kind == "suggest"


def test_a_bare_name_with_several_qualified_namesakes_is_only_suggested():
    infos = {"bare": info("Henric III", "person", "bare"), "v": info("King Henric III of Vestland", "person", "v"),
             "k": info("Henric III of Karelia", "person", "k")}
    d = resolution.evaluate(infos)
    assert d[("bare", "v")].kind == "suggest" and d[("bare", "k")].kind == "suggest" and d[("k", "v")].kind == "never"
    assert "could also be" in d[("bare", "v")].reasons[0]


def test_a_bare_name_with_one_qualified_name_or_the_same_qualifier_twice_is_merged():
    one = {"bare": info("Henric III", "person", "bare"), "v": info("King Henric III of Vestland", "person", "v")}
    assert resolution.evaluate(one)[("bare", "v")].kind == "auto"
    twice = {"bare": info("Henric III", "person", "bare"), "v": info("King Henric III of Vestland", "person", "v"),
             "w": info("Henric III of Vestland", "person", "w")}
    d = resolution.evaluate(twice)
    assert d[("bare", "v")].kind == "auto" and d[("bare", "w")].kind == "auto" and d[("v", "w")].kind == "auto"


def test_an_acronym_needs_every_significant_word_to_match():
    assert resolution.acronym_matches(info("IBM"), info("International Business Machines"))
    assert resolution.acronym_matches(info("MIT"), info("Massachusetts Institute of Technology"))
    assert not resolution.acronym_matches(info("IB"), info("International Business Machines"))
    assert not resolution.acronym_matches(info("IBM"), info("International Machines"))
    assert not resolution.acronym_matches(info("Acme"), info("Acme Labs"))


# ---------------------------------------------------------------- passes and aliases

def test_run_keeps_going_until_nothing_more_can_be_merged(world):
    db = world.db
    # 'Turing' and 'Alan Turing' share document 1. 'Dr. Alan Turing' (document 2, more facts) is the same name as 'Alan Turing'
    # and survives that merge, so 'Turing' can only be paired with it in a second pass.
    other_doc = Document(title="D2", text="y" * 50, char_count=50, status=DocumentStatus.COMPLETED)
    db.add(other_doc)
    db.flush()
    chunk2 = Chunk(document_id=other_doc.id, index=0, start=0, end=50, text="y" * 50)
    db.add(chunk2)
    db.flush()
    t, a, b = world.ent("Turing", "person"), world.ent("Alan Turing", "person"), world.ent("Dr. Alan Turing", "person")
    world.fact(t, "worked at", world.ent("Bletchley Park", "place"))
    world.fact(a, "designed", world.ent("Bombe", "product"))
    world.fact(b, "joined", world.ent("NPL"), doc=other_doc.id, chunk=chunk2.id)
    world.fact(b, "died in", world.ent("Wilmslow", "place"), doc=other_doc.id, chunk=chunk2.id)
    db.commit()
    s = resolution.run_resolution(db)
    db.commit()
    persons = db.execute(select(Entity).where(Entity.type == "person")).scalars().all()
    assert [e.name for e in persons] == ["Dr. Alan Turing"] and s.auto_merged == 2


def test_an_alias_alone_sends_a_later_document_to_the_merged_entity(factory, db):
    read(db, TEXT, RAWS, auto_resolve=False)
    acme, acme_corp = (db.execute(select(Entity).where(Entity.name == n)).scalar_one() for n in ("ACME", "Acme Corp"))
    resolution.merge_entities(db, acme_corp.id, acme.id)
    db.commit()
    later = [rel("ACME", "hired", "Dana Reyes", "ACME hired Dana Reyes in 2022.", "2022", otype="person", stype="organization")]
    read(db, "ACME hired Dana Reyes in 2022.", later, auto_resolve=False)
    assert db.scalar(select(func.count()).select_from(Entity).where(Entity.name == "ACME")) == 0
    assert {f.predicate for f in db.execute(select(Fact).where(Fact.subject_id == acme_corp.id)).scalars()} == {"bought", "hired"}
