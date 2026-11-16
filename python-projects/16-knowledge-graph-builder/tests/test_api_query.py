import pytest
from fastapi.testclient import TestClient

from src.core import config
from src.core.database import get_db
from src.models.embedding import Embedding
from src.models.graph import Document, DocumentStatus
from src.services import pipeline
from src.services.embedding import EmbeddingError
from src.services.llm import LLMError
from tests.conftest import FakeEmbedder, FakeLLM, ScriptedLLM, rel


@pytest.fixture
def client(factory, story, monkeypatch):
    import server

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    server.app.dependency_overrides[get_db] = override
    monkeypatch.setattr("src.api.query.get_settings", lambda: config.Settings(_env_file=None))
    monkeypatch.setattr("src.api.query.get_embedder", lambda settings=None: FakeEmbedder())
    llm = ScriptedLLM(
        plan=lambda q: {"start": ["Veltra Dynamics"], "steps": [{"relation": "acquired", "direction": "out"}, {"relation": "founded", "direction": "in"}]},
        answer=lambda p: {"found": True, "answer": "Imani Okafor", "cited": ["F1", "F2"]})
    monkeypatch.setattr("src.api.query.get_llm", lambda settings=None: llm)
    c = TestClient(server.app)
    c.llm, c.story = llm, story
    yield c
    server.app.dependency_overrides.clear()


def test_ask_returns_the_answer_citations_and_reasoning(client):
    r = client.post("/api/ask", json={"question": "Who founded the company that Veltra Dynamics acquired?"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] and body["answer"] == "Imani Okafor" and body["reasoning"]["mode"] == "graph"
    assert [c["label"] for c in body["citations"]] == ["F1", "F2"] and body["citations"][0]["document_title"] == "d01"
    assert body["reasoning"]["steps"][1]["relation"] == "founded"


def test_ask_modes_and_validation(client):
    ok = client.post("/api/ask", json={"question": "Who founded Soro Labs?", "mode": "subgraph"})
    assert ok.status_code == 200 and ok.json()["reasoning"]["mode"] == "subgraph"
    assert client.post("/api/ask", json={"question": "Who founded Soro Labs?", "mode": "magic"}).status_code == 422
    assert client.post("/api/ask", json={"question": "hi"}).status_code == 422
    assert client.post("/api/ask", json={"question": "x" * 1001}).status_code == 422
    assert client.post("/api/ask", json={"question": "Who founded Soro Labs?", "document_id": "nope"}).status_code == 404


def test_ask_scoped_to_a_document(client):
    r = client.post("/api/ask", json={"question": "Who founded Soro Labs?", "mode": "subgraph", "document_id": client.story.docs["d02"][0]})
    assert r.status_code == 200 and r.json()["reasoning"]["evidence_documents"] == ["d02"]


def test_ask_reports_a_model_or_embedding_outage(client, monkeypatch):
    def down(settings=None):
        raise LLMError("Cannot reach Ollama at http://localhost:11434. Is it running? (ollama serve)")
    monkeypatch.setattr("src.api.query.get_llm", down)
    r = client.post("/api/ask", json={"question": "Who founded Soro Labs?"})
    assert r.status_code == 503 and "Cannot reach Ollama" in r.json()["detail"]
    monkeypatch.undo()


def test_ask_vector_mode_reports_a_missing_embedding_model(client, monkeypatch):
    class Broken(FakeEmbedder):
        def embed(self, texts, kind="document"):
            raise EmbeddingError("Ollama does not have the embedding model 'nomic-embed-text'. Run: ollama pull nomic-embed-text")
    monkeypatch.setattr("src.api.query.get_embedder", lambda settings=None: Broken())
    r = client.post("/api/ask", json={"question": "Who founded Soro Labs?", "mode": "vector"})
    assert r.status_code == 503 and "ollama pull" in r.json()["detail"]


def test_vectors_made_while_answering_are_kept(client, factory):
    client.post("/api/ask", json={"question": "Who founded Soro Labs?", "mode": "subgraph"})
    with factory() as db:
        assert db.query(Embedding).filter(Embedding.fact_id.is_not(None)).count() > 0


def test_link_shows_what_a_text_is_matched_to(client):
    r = client.get("/api/query/link", params={"q": "Where is the University of Tamsen?"}).json()
    assert [(e["name"], e["how"], e["confidence"]) for e in r["entities"]] == [("University of Tamsen", "exact", 1.0)]
    assert client.get("/api/query/link", params={"q": "nothing known here"}).json() == {"entities": []}
    assert client.get("/api/query/link").status_code == 422


def test_path_by_name_or_id(client):
    r = client.get("/api/query/path", params={"from": "Imani Okafor", "to": "Veltra Dynamics"}).json()
    assert r["from"] == "Imani Okafor" and [p["text"] for p in r["paths"][0]] == ["Imani Okafor founded Soro Labs (2011..)", "Veltra Dynamics acquired Soro Labs (2018..)"]
    assert r["paths"][0][1]["valid_from"] == "2018" and r["paths"][0][1]["valid_to"] is None
    by_id = client.get("/api/query/path", params={"from": client.story.dravia.id, "to": client.story.imani.id, "max_hops": 3}).json()
    assert len(by_id["paths"][0]) == 3
    assert client.get("/api/query/path", params={"from": client.story.dravia.id, "to": client.story.imani.id, "max_hops": 2}).json()["paths"] == []
    assert client.get("/api/query/path", params={"from": "Zorg", "to": "Imani Okafor"}).status_code == 404
    assert client.get("/api/query/path", params={"from": "Imani Okafor"}).status_code == 422
    assert client.get("/api/query/path", params={"from": "Imani Okafor", "to": "Soro Labs", "max_hops": 9}).status_code == 422


def test_chain_query_without_a_language_model(client):
    body = {"start": "Veltra Dynamics", "steps": [{"relation": "acquired", "direction": "out"}, {"relation": "founded", "direction": "in"}]}
    r = client.post("/api/query/chain", json=body).json()
    assert r["ok"] and r["answers"] == ["Imani Okafor"] and [f["text"] for f in r["facts"]] == ["Veltra Dynamics acquired Soro Labs (2018..)", "Imani Okafor founded Soro Labs (2011..)"]
    broken = client.post("/api/query/chain", json={"start": "Veltra Dynamics", "steps": [{"relation": "married to"}]}).json()
    assert broken["ok"] is False and "nothing matches" in broken["reason"] and broken["answers"] == []
    value = client.post("/api/query/chain", json={"start": "Soro Labs", "steps": [{"relation": "employs"}]}).json()
    assert value["answers"] == ["40 people"]
    assert client.post("/api/query/chain", json={"start": "Zorg", "steps": [{"relation": "x"}]}).status_code == 404
    assert client.post("/api/query/chain", json={"start": "Soro Labs", "steps": []}).status_code == 422
    assert client.post("/api/query/chain", json={"start": "Soro Labs", "steps": [{"relation": "x", "direction": "up"}]}).status_code == 422


def test_chain_query_works_without_embeddings(client, monkeypatch):
    class Down(FakeEmbedder):
        def embed(self, texts, kind="document"):
            raise EmbeddingError("down")
    monkeypatch.setattr("src.api.query.get_embedder", lambda settings=None: Down())
    r = client.post("/api/query/chain", json={"start": "Veltra Dynamics", "steps": [{"relation": "acquired"}, {"relation": "founder", "direction": "in"}]}).json()
    assert r["ok"] and r["answers"] == ["Imani Okafor"]


def test_index_status_and_rebuild(client):
    s = client.get("/api/index/status").json()
    assert s["model"] == "fake:embed" and s["passages"] > 0 and s["passages_indexed"] == 0 and s["facts_indexed"] == 0
    r = client.post("/api/index/rebuild").json()
    assert r["passages_added"] == s["passages"] and r["facts_added"] == s["facts"]
    s2 = client.get("/api/index/status").json()
    assert s2["passages_indexed"] == s2["passages"] and s2["facts_indexed"] == s2["facts"]
    again = client.post("/api/index/rebuild").json()
    assert again["passages_added"] == 0 and again["facts_added"] == 0


def test_rebuild_waits_while_a_document_is_read_and_reports_an_embedding_outage(client, monkeypatch):
    assert pipeline.owner_lock(None).acquire(blocking=False)
    try:
        assert client.post("/api/index/rebuild").status_code == 409
    finally:
        pipeline.owner_lock(None).release()

    class Down(FakeEmbedder):
        def embed(self, texts, kind="document"):
            raise EmbeddingError("Cannot reach Ollama at x for embeddings. Is it running?")
    monkeypatch.setattr("src.api.query.get_embedder", lambda settings=None: Down())
    r = client.post("/api/index/rebuild")
    assert r.status_code == 503 and "embeddings" in r.json()["detail"]
    assert client.post("/api/index/rebuild").status_code == 503      # and the lock was released after the failure


# ---------------------------------------------------------------- reading a document indexes its passages

TEXT = "Acme Corp acquired Beta Systems in March 2020. Dana Reyes served as CTO of Acme from 2019 to 2022."
RAWS = [rel("Acme Corp", "acquired", "Beta Systems", "Acme Corp acquired Beta Systems in March 2020.", "March 2020", otype="organization", stype="organization")]


def read(db, settings_kw=None):
    d = Document(title="t", text=TEXT, char_count=len(TEXT))
    db.add(d)
    db.commit()
    s = config.Settings(_env_file=None, verify_facts=False, gleaning_passes=0, auto_resolve=False, **(settings_kw or {}))
    pipeline.process_document(d.id, FakeLLM(extract=lambda p: {"relations": RAWS}), s)
    db.expire_all()
    return db.get(Document, d.id)


def test_passages_are_embedded_after_reading(factory, db, monkeypatch):
    monkeypatch.setattr(pipeline, "get_embedder", lambda settings=None: FakeEmbedder())
    doc = read(db)
    assert doc.status == DocumentStatus.COMPLETED and "embedding_error" not in doc.stats
    assert db.query(Embedding).filter(Embedding.chunk_id.is_not(None)).count() == doc.chunk_count


def test_indexing_can_be_switched_off(factory, db, monkeypatch):
    monkeypatch.setattr(pipeline, "get_embedder", lambda settings=None: FakeEmbedder())
    read(db, {"index_chunks": False})
    assert db.query(Embedding).count() == 0


def test_a_missing_embedding_model_does_not_fail_the_document(factory, db, monkeypatch):
    class Down(FakeEmbedder):
        def embed(self, texts, kind="document"):
            raise EmbeddingError("Ollama does not have the embedding model 'nomic-embed-text'. Run: ollama pull nomic-embed-text")
    monkeypatch.setattr(pipeline, "get_embedder", lambda settings=None: Down())
    doc = read(db)
    assert doc.status == DocumentStatus.COMPLETED and "ollama pull" in doc.stats["embedding_error"] and doc.stats["accepted"] == 1
    assert db.query(Embedding).count() == 0


def test_deleting_a_document_removes_its_vectors(factory, db, monkeypatch):
    monkeypatch.setattr(pipeline, "get_embedder", lambda settings=None: FakeEmbedder())
    doc = read(db)
    pipeline.delete_document(db, doc)
    db.commit()
    assert db.query(Embedding).count() == 0
