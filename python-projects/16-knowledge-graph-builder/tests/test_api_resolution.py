import pytest
from fastapi.testclient import TestClient

from src.core import config
from src.core.database import get_db
from src.models.graph import Chunk, Document, DocumentStatus, Entity, Fact, FactSource
from src.services import pipeline, resolution
from tests.conftest import FakeLLM


@pytest.fixture
def client(factory, monkeypatch):
    import server

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    server.app.dependency_overrides[get_db] = override
    monkeypatch.setattr("src.api.resolution.get_settings", lambda: config.Settings(_env_file=None))
    c = TestClient(server.app)
    c.factory = factory
    yield c
    server.app.dependency_overrides.clear()


def seed(factory, spec):
    """spec: list of (name, type) -> {name: id}; plus one fact 'partnered with' Beta for each, so they have context"""
    with factory() as db:
        doc = Document(title="D", text="x" * 50, char_count=50, status=DocumentStatus.COMPLETED)
        db.add(doc)
        db.flush()
        chunk = Chunk(document_id=doc.id, index=0, start=0, end=50, text="x" * 50)
        db.add(chunk)
        ids = {}
        for name, etype in spec:
            e = Entity(name=name, key=resolution.entity_key(name), type=etype)
            db.add(e)
            db.flush()
            ids[name] = e.id
        db.commit()
        return ids, doc.id, chunk.id


def link(factory, ids, doc, chunk, subj, pred, obj):
    with factory() as db:
        f = Fact(subject_id=ids[subj], predicate=pred, object_id=ids[obj], object_value="")
        db.add(f)
        db.flush()
        db.add(FactSource(fact_id=f.id, document_id=doc, chunk_id=chunk, evidence=f"{subj} {pred} {obj}"))
        db.commit()


def test_run_merges_safe_pairs_and_lists_the_rest_with_details(client):
    ids, doc, chunk = seed(client.factory, [("ACME", "organization"), ("Acme Corp", "organization"), ("Acme Labs", "organization"), ("Beta", "organization")])
    link(client.factory, ids, doc, chunk, "Acme Corp", "acquired", "Beta")
    r = client.post("/api/resolution/run")
    assert r.status_code == 200 and r.json()["auto_merged"] == 1 and r.json()["suggestions_new"] == 1
    sug = client.get("/api/resolution/suggestions").json()["suggestions"]
    assert len(sug) == 1 and sug[0]["status"] == "pending" and 0.5 <= sug[0]["score"] <= 0.95
    names = {sug[0]["a"]["name"], sug[0]["b"]["name"]}
    assert names == {"Acme Corp", "Acme Labs"} and sug[0]["reasons"]
    corp = next(x for x in (sug[0]["a"], sug[0]["b"]) if x["name"] == "Acme Corp")
    assert corp["fact_count"] == 1 and corp["aliases"] == ["ACME"] and corp["sample_facts"] == ["Acme Corp acquired Beta"]


def test_run_can_skip_merging(client):
    seed(client.factory, [("ACME", "organization"), ("Acme Corp", "organization")])
    assert client.post("/api/resolution/run", json={"auto": False}).json()["auto_merged"] == 0
    assert len(client.get("/api/entities").json()["entities"]) == 2


def test_accept_reject_and_history(client):
    ids, *_ = seed(client.factory, [("Acme", "organization"), ("Acme Labs", "organization"), ("Turing", "person"), ("Alan Turing", "person")])
    client.post("/api/resolution/run")
    sug = {frozenset((s["a"]["name"], s["b"]["name"])): s for s in client.get("/api/resolution/suggestions").json()["suggestions"]}
    acme_pair, turing_pair = sug[frozenset(("Acme", "Acme Labs"))], sug[frozenset(("Turing", "Alan Turing"))]
    r = client.post(f"/api/resolution/suggestions/{turing_pair['id']}/accept")
    assert r.status_code == 200 and r.json()["kept"] == "Alan Turing" and r.json()["absorbed"] == "Turing" and r.json()["how"] == "suggestion"
    assert client.post(f"/api/resolution/suggestions/{acme_pair['id']}/reject").status_code == 204
    assert client.post(f"/api/resolution/suggestions/{acme_pair['id']}/reject").status_code == 409
    assert client.post(f"/api/resolution/suggestions/{acme_pair['id']}/accept").status_code == 409
    assert client.post("/api/resolution/suggestions/nope/accept").status_code == 404
    assert client.post("/api/resolution/suggestions/nope/reject").status_code == 404
    assert client.get("/api/resolution/suggestions").json()["suggestions"] == []
    rejected = client.get("/api/resolution/suggestions?status=rejected").json()["suggestions"]
    assert len(rejected) == 1 and client.get("/api/resolution/suggestions?status=banana").status_code == 422
    merges = client.get("/api/resolution/merges").json()["merges"]
    assert [(m["kept"], m["absorbed"]) for m in merges] == [("Alan Turing", "Turing")]
    detail = client.get(f"/api/entities/{ids['Alan Turing']}").json()
    assert detail["aliases"] == ["Turing"]


def test_accept_can_choose_the_survivor(client):
    ids, *_ = seed(client.factory, [("Acme", "organization"), ("Acme Labs", "organization")])
    client.post("/api/resolution/run")
    s = client.get("/api/resolution/suggestions").json()["suggestions"][0]
    assert client.post(f"/api/resolution/suggestions/{s['id']}/accept", json={"keep_id": "other"}).status_code == 409
    r = client.post(f"/api/resolution/suggestions/{s['id']}/accept", json={"keep_id": ids["Acme"]})
    assert r.json()["kept"] == "Acme"


def test_manual_merge_and_its_refusals(client):
    ids, doc, chunk = seed(client.factory, [("Acme", "organization"), ("Acme Corp", "organization"), ("Ann", "person"), ("Beta", "organization")])
    link(client.factory, ids, doc, chunk, "Acme", "owns", "Beta")
    assert client.post("/api/entities/merge", json={"keep_id": ids["Acme"], "absorb_id": ids["Ann"]}).status_code == 409
    assert client.post("/api/entities/merge", json={"keep_id": ids["Acme"], "absorb_id": ids["Beta"]}).status_code == 409
    assert client.post("/api/entities/merge", json={"keep_id": ids["Acme"], "absorb_id": ids["Acme"]}).status_code == 409
    assert client.post("/api/entities/merge", json={"keep_id": ids["Acme"], "absorb_id": "nope"}).status_code == 404
    assert client.post("/api/entities/merge", json={"keep_id": ids["Acme"]}).status_code == 422
    r = client.post("/api/entities/merge", json={"keep_id": ids["Acme"], "absorb_id": ids["Acme Corp"]})
    assert r.status_code == 200 and r.json()["how"] == "manual"
    assert client.get(f"/api/entities/{ids['Acme Corp']}").status_code == 404


def test_undo_through_the_api(client):
    ids, doc, chunk = seed(client.factory, [("Acme", "organization"), ("Acme Corp", "organization"), ("Beta", "organization")])
    link(client.factory, ids, doc, chunk, "Acme Corp", "owns", "Beta")
    rec = client.post("/api/entities/merge", json={"keep_id": ids["Acme"], "absorb_id": ids["Acme Corp"]}).json()
    assert client.get(f"/api/entities/{ids['Acme']}").json()["outgoing"][0]["predicate"] == "owns"
    assert client.post(f"/api/resolution/merges/{rec['id']}/undo").json()["undone"] is True
    assert client.get(f"/api/entities/{ids['Acme Corp']}").json()["outgoing"][0]["predicate"] == "owns"
    assert client.get(f"/api/entities/{ids['Acme']}").json()["outgoing"] == []
    assert client.get("/api/resolution/merges").json()["merges"] == []
    assert len(client.get("/api/resolution/merges?include_undone=true").json()["merges"]) == 1
    assert client.post(f"/api/resolution/merges/{rec['id']}/undo").status_code == 409
    assert client.post("/api/resolution/merges/nope/undo").status_code == 404


def test_writes_wait_while_a_document_is_being_read(client):
    ids, *_ = seed(client.factory, [("Acme", "organization"), ("Acme Corp", "organization")])
    assert pipeline._PROCESS_LOCK.acquire(blocking=False)
    try:
        assert client.post("/api/resolution/run").status_code == 409
        assert client.post("/api/entities/merge", json={"keep_id": ids["Acme"], "absorb_id": ids["Acme Corp"]}).status_code == 409
        assert client.post("/api/resolution/suggestions/x/accept").status_code == 409
        assert client.post("/api/resolution/suggestions/x/reject").status_code == 409
        assert client.post("/api/resolution/merges/x/undo").status_code == 409
        assert client.get("/api/resolution/suggestions").status_code == 200   # reading is always fine
    finally:
        pipeline._PROCESS_LOCK.release()
    assert client.post("/api/resolution/run").status_code == 200              # and the lock is free again afterwards


def test_run_with_the_model_asks_for_second_opinions_and_reports_an_unavailable_model(client, monkeypatch):
    seed(client.factory, [("Acme", "organization"), ("Acme Labs", "organization")])
    llm = FakeLLM()
    llm.generate_json = lambda system, prompt, schema: {"same": "yes"}
    monkeypatch.setattr("src.api.resolution.get_llm", lambda settings=None: llm)
    r = client.post("/api/resolution/run", json={"use_llm": True}).json()
    assert r["judged"] == 1
    assert client.get("/api/resolution/suggestions").json()["suggestions"][0]["llm_verdict"] == "yes"

    from src.services.llm import LLMError

    def down(settings=None):
        raise LLMError("Cannot reach Ollama")
    monkeypatch.setattr("src.api.resolution.get_llm", down)
    r = client.post("/api/resolution/run", json={"use_llm": True})
    assert r.status_code == 503 and "Cannot reach Ollama" in r.json()["detail"]
