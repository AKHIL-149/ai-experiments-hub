import pytest
from sqlalchemy import func, select

from src.core.config import Settings
from src.models.graph import Chunk, Document, DocumentStatus, Entity, Fact, FactSource
from src.services import pipeline
from src.services.llm import LLMBadOutput, LLMError
from tests.conftest import FakeLLM, rel

TEXT = ("Acme Corp, founded in 2010 by Maria Lopez, acquired Beta Systems in March 2020. "
        "Dana Reyes served as CTO of Acme from 2019 to 2022.")
S1 = "Acme Corp, founded in 2010 by Maria Lopez, acquired Beta Systems in March 2020."
S2 = "Dana Reyes served as CTO of Acme from 2019 to 2022."


def settings(**kw):
    return Settings(_env_file=None, verify_facts=False, gleaning_passes=0, **kw)


def script(*raws):
    return FakeLLM(extract=lambda p: {"relations": list(raws)})


ACQ = rel("Acme Corp", "acquired", "Beta Systems", S1, "March 2020", otype="organization", stype="organization")
CTO = rel("Dana Reyes", "served as cto of", "Acme", S2, "2019", "2022", otype="organization")
REV = rel("Acme Corp", "reported revenue", "12M", "Acme Corp reported revenue of 12M in 2021.", "2021", otype="value", stype="organization")


def add_doc(db, text=TEXT, title="Doc"):
    d = Document(title=title, text=text, char_count=len(text))
    db.add(d)
    db.commit()
    return d.id


def counts(db):
    return {m.__name__: db.scalar(select(func.count()).select_from(m)) for m in (Document, Chunk, Entity, Fact, FactSource)}


def test_document_becomes_chunks_facts_entities_and_sources(factory, db):
    doc_id = add_doc(db)
    pipeline.process_document(doc_id, script(ACQ, CTO), settings())
    doc = db.get(Document, doc_id)
    assert doc.status == DocumentStatus.COMPLETED and doc.error is None and doc.finished_at
    assert doc.model == "fake:model" and doc.chunk_count == doc.chunks_done == 1
    assert doc.stats["accepted"] == 2 and doc.stats["new_facts"] == 2
    names = {e.name: e.type for e in db.execute(select(Entity)).scalars()}
    assert names == {"Acme Corp": "organization", "Beta Systems": "organization", "Dana Reyes": "person", "Acme": "organization"}
    fact = db.execute(select(Fact).where(Fact.predicate == "served as cto of")).scalar_one()
    assert (fact.valid_from, fact.valid_to) == ("2019", "2022")
    src = fact.sources[0]
    assert src.evidence == S2 and src.document_id == doc_id and not src.verified
    chunk = db.get(Chunk, src.chunk_id)
    assert chunk.text[chunk.text.index(S2):].startswith(S2)


def test_value_facts_have_no_object_entity(factory, db):
    doc_id = add_doc(db, "Acme Corp reported revenue of 12M in 2021.")
    pipeline.process_document(doc_id, script(REV), settings())
    f = db.execute(select(Fact)).scalar_one()
    assert f.object_id is None and f.object_value == "12M" and f.valid_from == "2021"
    assert db.scalar(select(func.count()).select_from(Entity)) == 1


def test_same_fact_in_two_documents_is_one_fact_with_two_sources(factory, db):
    a, b = add_doc(db, title="A"), add_doc(db, title="B")
    pipeline.process_document(a, script(ACQ), settings())
    pipeline.process_document(b, script(ACQ), settings())
    assert counts(db) == {"Document": 2, "Chunk": 2, "Entity": 2, "Fact": 1, "FactSource": 2}


def test_same_name_different_case_becomes_one_entity(factory, db):
    doc_id = add_doc(db, "Acme Corp bought Beta Systems. ACME CORP bought Gamma Ltd.")
    r1 = rel("Acme Corp", "bought", "Beta Systems", "Acme Corp bought Beta Systems.", otype="organization", stype="organization")
    r2 = rel("ACME CORP", "bought", "Gamma Ltd", "ACME CORP bought Gamma Ltd.", otype="organization", stype="organization")
    pipeline.process_document(doc_id, script(r1, r2), settings())
    assert db.scalar(select(func.count()).select_from(Entity).where(Entity.key == "acme corp")) == 1
    assert db.scalar(select(func.count()).select_from(Fact)) == 2


def test_vague_type_is_upgraded_but_specific_type_is_kept(factory, db):
    doc_id = add_doc(db, "Acme Corp bought Beta Systems. Beta Systems is in Oslo.")
    r1 = rel("Acme Corp", "bought", "Beta Systems", "Acme Corp bought Beta Systems.", otype="concept", stype="organization")
    r2 = rel("Beta Systems", "located in", "Oslo", "Beta Systems is in Oslo.", otype="place", stype="product")
    pipeline.process_document(doc_id, script(r1, r2), settings())
    types = {e.name: e.type for e in db.execute(select(Entity)).scalars()}
    assert types["Beta Systems"] == "product" and types["Acme Corp"] == "organization"


def test_reprocessing_replaces_instead_of_duplicating(factory, db):
    doc_id = add_doc(db)
    pipeline.process_document(doc_id, script(ACQ, CTO), settings())
    before = counts(db)
    pipeline.process_document(doc_id, script(ACQ), settings())
    after = counts(db)
    assert before == {"Document": 1, "Chunk": 1, "Entity": 4, "Fact": 2, "FactSource": 2}
    assert after == {"Document": 1, "Chunk": 1, "Entity": 2, "Fact": 1, "FactSource": 1}  # the CTO fact is gone with its entities


def test_deleting_a_document_keeps_facts_other_documents_still_support(factory, db):
    a, b = add_doc(db, title="A"), add_doc(db, title="B")
    pipeline.process_document(a, script(ACQ, CTO), settings())
    pipeline.process_document(b, script(ACQ), settings())
    pipeline.delete_document(db, db.get(Document, a))
    db.commit()
    assert counts(db) == {"Document": 1, "Chunk": 1, "Entity": 2, "Fact": 1, "FactSource": 1}
    pipeline.delete_document(db, db.get(Document, b))
    db.commit()
    assert counts(db) == {k: 0 for k in counts(db)}


def test_unreachable_model_fails_the_document_with_a_clear_message(factory, db):
    doc_id = add_doc(db)
    pipeline.process_document(doc_id, FakeLLM(extract=lambda p: LLMError("Cannot reach Ollama at http://x")), settings())
    doc = db.get(Document, doc_id)
    assert doc.status == DocumentStatus.FAILED and "Cannot reach Ollama" in doc.error and doc.finished_at
    assert counts(db)["Fact"] == 0


def test_failure_halfway_keeps_earlier_chunks_out_of_a_completed_state(factory, db):
    text = " ".join(f"Sentence {i} mentions Acme Corp and Beta Systems here today." for i in range(80))
    doc_id = add_doc(db, text)
    calls = {"n": 0}

    def flaky(prompt):
        calls["n"] += 1
        if calls["n"] == 3:
            return LLMError("Ollama took longer than 300s to answer")
        return {"relations": []}

    pipeline.process_document(doc_id, FakeLLM(extract=flaky), settings(chunk_chars=400, chunk_overlap_chars=0))
    doc = db.get(Document, doc_id)
    assert doc.status == DocumentStatus.FAILED and doc.chunks_done == 2 and doc.chunk_count > 3


def test_bad_output_on_one_chunk_does_not_fail_the_document(factory, db):
    text = " ".join(f"Sentence {i} mentions Acme Corp and Beta Systems here today." for i in range(40))
    doc_id = add_doc(db, text)
    calls = {"n": 0}

    def sometimes_broken(prompt):
        calls["n"] += 1
        return LLMBadOutput("broken") if calls["n"] in (1, 2) else {"relations": []}

    pipeline.process_document(doc_id, FakeLLM(extract=sometimes_broken), settings(chunk_chars=400, chunk_overlap_chars=0))
    doc = db.get(Document, doc_id)
    assert doc.status == DocumentStatus.COMPLETED and doc.stats["chunk_errors"] == 1
    assert doc.chunks_done == doc.chunk_count


def test_unexpected_crash_never_leaves_the_document_processing(factory, db):
    doc_id = add_doc(db)

    def boom(prompt):
        raise KeyError("bug")

    pipeline.process_document(doc_id, FakeLLM(extract=boom), settings())
    doc = db.get(Document, doc_id)
    assert doc.status == DocumentStatus.FAILED and "Unexpected error" in doc.error and "bug" not in doc.error


def test_missing_document_and_missing_api_key_are_handled(factory, db):
    pipeline.process_document("nope", script(), settings())  # no crash
    doc_id = add_doc(db)
    pipeline.process_document(doc_id, None, settings(llm_provider="anthropic", anthropic_api_key=None))
    assert db.get(Document, doc_id).status == DocumentStatus.FAILED
    assert "ANTHROPIC_API_KEY" in db.get(Document, doc_id).error


def test_verification_runs_per_fact_and_marks_sources_verified(factory, db):
    doc_id = add_doc(db)
    llm = script(ACQ, CTO)
    pipeline.process_document(doc_id, llm, Settings(_env_file=None, verify_facts=True, gleaning_passes=0))
    assert llm.count("verify") == 2
    assert all(s.verified for s in db.execute(select(FactSource)).scalars())


def test_progress_is_committed_after_every_chunk(factory, db):
    text = " ".join(f"Sentence {i} mentions Acme Corp and Beta Systems here today." for i in range(40))
    doc_id = add_doc(db, text)
    seen = []

    def watch(prompt):
        with factory() as other:
            seen.append((other.get(Document, doc_id).status, other.get(Document, doc_id).chunks_done))
        return {"relations": []}

    pipeline.process_document(doc_id, FakeLLM(extract=watch), settings(chunk_chars=400, chunk_overlap_chars=0))
    assert seen[0] == (DocumentStatus.PROCESSING, 0) and seen[1] == (DocumentStatus.PROCESSING, 1)
    assert [n for _, n in seen] == list(range(len(seen)))


def test_recover_interrupted_marks_stuck_documents_failed(factory, db):
    a, b, c = add_doc(db, title="a"), add_doc(db, title="b"), add_doc(db, title="c")
    db.get(Document, a).status = DocumentStatus.PROCESSING
    db.get(Document, c).status = DocumentStatus.COMPLETED
    db.commit()
    assert pipeline.recover_interrupted() == 2  # a (processing) and b (pending)
    db.expire_all()
    assert db.get(Document, a).status == DocumentStatus.FAILED and "restart" in db.get(Document, a).error
    assert db.get(Document, b).status == DocumentStatus.FAILED
    assert db.get(Document, c).status == DocumentStatus.COMPLETED


def test_prune_orphans_leaves_used_entities(factory, db):
    doc_id = add_doc(db)
    pipeline.process_document(doc_id, script(ACQ), settings())
    db.add(Entity(name="Lonely", key="lonely", type="concept"))
    db.commit()
    pipeline.prune_orphans(db)
    db.commit()
    assert {e.name for e in db.execute(select(Entity)).scalars()} == {"Acme Corp", "Beta Systems"}


def test_storing_the_same_fact_from_the_same_quote_twice_adds_one_source(factory, db):
    from src.services.extraction import ExtractedFact
    doc_id = add_doc(db)
    pipeline.process_document(doc_id, script(), settings())  # makes a chunk
    chunk = db.execute(select(Chunk)).scalars().first()
    fact = ExtractedFact("Acme Corp", "organization", "acquired", "Beta Systems", "organization", "", "", S1)
    a, new_a = pipeline.store_fact(db, fact, doc_id, chunk.id)
    b, new_b = pipeline.store_fact(db, fact, doc_id, chunk.id)
    db.commit()
    assert a.id == b.id and new_a and not new_b
    assert db.scalar(select(func.count()).select_from(FactSource)) == 1


def test_entity_names_that_differ_only_in_punctuation_or_spacing_are_one_entity(factory, db):
    doc_id = add_doc(db, "Acme, Inc. bought Beta Systems. ACME  Inc bought Gamma Ltd.")
    r1 = rel("Acme, Inc.", "bought", "Beta Systems", "Acme, Inc. bought Beta Systems.", otype="organization", stype="organization")
    r2 = rel("ACME  Inc", "bought", "Gamma Ltd", "ACME  Inc bought Gamma Ltd.", otype="organization", stype="organization")
    pipeline.process_document(doc_id, script(r1, r2), settings())
    assert db.scalar(select(func.count()).select_from(Entity).where(Entity.key == "acme inc")) == 1
    assert db.scalar(select(func.count()).select_from(Entity)) == 3


def _fact(from_="", to="", subject="Acme Corp", obj="Beta Systems"):
    from src.services.extraction import ExtractedFact
    return ExtractedFact(subject, "organization", "acquired", obj, "organization", from_, to, S1)


def test_undated_and_dated_sightings_of_one_statement_become_one_fact(factory, db):
    doc_id = add_doc(db)
    pipeline.process_document(doc_id, script(), settings())
    chunk = db.execute(select(Chunk)).scalars().first()
    first, _ = pipeline.store_fact(db, _fact(), doc_id, chunk.id)           # undated first
    second, new = pipeline.store_fact(db, _fact("2020-03"), doc_id, chunk.id)  # same statement, now with a date
    db.commit()
    assert first.id == second.id and not new and (second.valid_from, second.valid_to) == ("2020-03", "")
    third, new = pipeline.store_fact(db, _fact(), doc_id, chunk.id)          # undated again: joins the dated fact
    assert third.id == first.id and not new
    other, new = pipeline.store_fact(db, _fact("2010"), doc_id, chunk.id)   # a different period is a new fact
    db.commit()
    assert new and other.id != first.id and db.scalar(select(func.count()).select_from(Fact)) == 2


def test_undated_sighting_joins_a_stored_value_fact_with_dates(factory, db):
    from src.services.extraction import ExtractedFact
    doc_id = add_doc(db)
    pipeline.process_document(doc_id, script(), settings())
    chunk = db.execute(select(Chunk)).scalars().first()
    dated = ExtractedFact("Acme Corp", "organization", "reported revenue", "12M", "value", "2021", "", S1)
    plain = ExtractedFact("Acme Corp", "organization", "reported revenue", "12M", "value", "", "", S1)
    a, _ = pipeline.store_fact(db, dated, doc_id, chunk.id)
    b, new = pipeline.store_fact(db, plain, doc_id, chunk.id)
    assert a.id == b.id and not new


def test_leading_articles_do_not_make_separate_entities(factory, db):
    doc_id = add_doc(db, "Acme Corp bought the Bombe. Beta Systems bought Bombe too.")
    r1 = rel("Acme Corp", "bought", "the Bombe", "Acme Corp bought the Bombe.", otype="product", stype="organization")
    r2 = rel("Beta Systems", "bought", "Bombe", "Beta Systems bought Bombe too.", otype="product", stype="organization")
    pipeline.process_document(doc_id, script(r1, r2), settings())
    bombes = db.execute(select(Entity).where(Entity.key == "bombe")).scalars().all()
    assert [e.name for e in bombes] == ["Bombe"] and db.scalar(select(func.count()).select_from(Entity)) == 3
