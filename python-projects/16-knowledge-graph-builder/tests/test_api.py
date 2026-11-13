import io

import docx
import pytest
from fastapi.testclient import TestClient

from src.core import config
from src.core.database import get_db
from src.models.graph import Document, DocumentStatus
from src.services import pipeline
from tests.conftest import FakeLLM, rel

TEXT = ("Acme Corp, founded in 2010 by Maria Lopez, acquired Beta Systems in March 2020. "
        "Dana Reyes served as CTO of Acme from 2019 to 2022.")
S1 = "Acme Corp, founded in 2010 by Maria Lopez, acquired Beta Systems in March 2020."
S2 = "Dana Reyes served as CTO of Acme from 2019 to 2022."
RAWS = [rel("Acme Corp", "acquired", "Beta Systems", S1, "March 2020", otype="organization", stype="organization"),
        rel("Dana Reyes", "served as cto of", "Acme", S2, "2019", "2022", otype="organization")]


@pytest.fixture
def client(factory, monkeypatch):
    import server

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    llm = FakeLLM(extract=lambda p: {"relations": RAWS})
    monkeypatch.setattr(pipeline, "get_llm", lambda settings=None: llm)
    monkeypatch.setattr(pipeline, "get_settings", lambda: config.Settings(_env_file=None, verify_facts=False, gleaning_passes=0, auto_resolve=False))
    server.app.dependency_overrides[get_db] = override
    c = TestClient(server.app)  # no 'with': the real database is not initialised
    c.llm = llm
    yield c
    server.app.dependency_overrides.clear()


def upload_text(client, text=TEXT, title="Report"):
    r = client.post("/api/documents/text", json={"title": title, "text": text})
    assert r.status_code == 202, r.text
    return r.json()


def test_pasted_text_is_read_in_the_background_and_the_graph_appears(client):
    doc = upload_text(client)
    assert doc["status"] == "pending" and doc["title"] == "Report"
    done = client.get(f"/api/documents/{doc['id']}").json()  # the test client runs background tasks before returning
    assert done["status"] == "completed" and done["progress"] == 1.0 and done["stats"]["accepted"] == 2
    g = client.get("/api/graph").json()
    assert {n["name"] for n in g["nodes"]} == {"Acme Corp", "Beta Systems", "Dana Reyes", "Acme"}
    assert {e["predicate"] for e in g["edges"]} == {"acquired", "served as cto of"}
    assert client.get("/api/graph/stats").json()["facts"] == 2


def test_text_file_upload(client):
    r = client.post("/api/documents", files={"file": ("news.txt", TEXT.encode(), "text/plain")})
    assert r.status_code == 202 and r.json()["title"] == "news" and r.json()["filename"] == "news.txt"


def test_word_file_upload(client):
    d = docx.Document()
    d.add_paragraph(S1)
    d.add_paragraph(S2)
    buf = io.BytesIO()
    d.save(buf)
    r = client.post("/api/documents", files={"file": ("memo.docx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 202
    assert client.get(f"/api/documents/{r.json()['id']}").json()["status"] == "completed"


@pytest.mark.parametrize("name,data,status,fragment", [
    ("a.exe", b"abc" * 20, 422, "Unsupported file type"),
    ("a.txt", b"", 422, "empty"),
    ("a.txt", b"short", 422, "too short"),
    ("a.pdf", b"not really a pdf", 422, "PDF"),
    ("a.docx", b"not a zip", 422, "Word"),
])
def test_bad_uploads_are_refused_with_a_reason(client, name, data, status, fragment):
    r = client.post("/api/documents", files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == status and fragment in r.json()["detail"]


def test_size_limits(client, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "max_upload_mb", 1)
    r = client.post("/api/documents", files={"file": ("big.txt", b"a " * 600_000, "text/plain")})
    assert r.status_code == 413 and "1 MB" in r.json()["detail"]
    monkeypatch.setattr(config.get_settings(), "max_document_chars", 100)
    r = client.post("/api/documents/text", json={"title": "x", "text": "word " * 100})
    assert r.status_code == 413


def test_text_endpoint_validation(client):
    assert client.post("/api/documents/text", json={"title": "", "text": "x" * 50}).status_code == 422
    assert client.post("/api/documents/text", json={"title": "t"}).status_code == 422


def test_model_down_gives_a_failed_document_with_the_reason_and_it_can_be_read_again(client):
    from src.services.llm import LLMError
    down = {"on": True}
    client.llm.extract = lambda p: LLMError("Cannot reach Ollama at http://localhost:11434. Is it running? (ollama serve)") if down["on"] else {"relations": RAWS}
    doc = upload_text(client)
    failed = client.get(f"/api/documents/{doc['id']}").json()
    assert failed["status"] == "failed" and "Cannot reach Ollama" in failed["error"]
    down["on"] = False
    assert client.post(f"/api/documents/{doc['id']}/reprocess").status_code == 202
    assert client.get(f"/api/documents/{doc['id']}").json()["status"] == "completed"
    assert client.get("/api/graph/stats").json()["facts"] == 2


def test_listing_newest_first_and_404s(client):
    a = upload_text(client, title="first")
    b = upload_text(client, title="second")
    titles = [d["title"] for d in client.get("/api/documents").json()["documents"]]
    assert titles == ["second", "first"]
    for url in ("/api/documents/nope", "/api/entities/nope", "/api/entities/nope/neighborhood", "/api/facts/nope"):
        assert client.get(url).status_code == 404
    assert client.delete("/api/documents/nope").status_code == 404
    assert client.post("/api/documents/nope/reprocess").status_code == 404
    assert client.get("/api/graph?document_id=nope").status_code == 404


def test_delete_removes_the_document_and_what_only_it_supported(client):
    doc = upload_text(client)
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get("/api/documents").json()["documents"] == []
    s = client.get("/api/graph/stats").json()
    assert s["facts"] == 0 and s["entities"] == 0


def test_documents_being_read_cannot_be_deleted_or_started_twice(client, factory):
    doc = upload_text(client)
    with factory() as db:
        db.get(Document, doc["id"]).status = DocumentStatus.PROCESSING
        db.commit()
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 409
    assert client.post(f"/api/documents/{doc['id']}/reprocess").status_code == 409


def test_entity_detail_lists_outgoing_and_incoming_facts(client):
    upload_text(client)
    acme = client.get("/api/entities?q=acme corp").json()["entities"][0]
    beta = client.get("/api/entities?q=beta").json()["entities"][0]
    d = client.get(f"/api/entities/{acme['id']}").json()
    assert d["name"] == "Acme Corp" and d["type"] == "organization"
    assert [(f["predicate"], f["object"]) for f in d["outgoing"]] == [("acquired", "Beta Systems")]
    assert d["outgoing"][0]["valid_from"] == "2020-03" and d["incoming"] == []
    b = client.get(f"/api/entities/{beta['id']}").json()
    assert [(f["subject"], f["predicate"]) for f in b["incoming"]] == [("Acme Corp", "acquired")]


def test_entity_search_filters(client):
    upload_text(client)
    assert {e["name"] for e in client.get("/api/entities").json()["entities"]} == {"Acme Corp", "Beta Systems", "Dana Reyes", "Acme"}
    assert [e["name"] for e in client.get("/api/entities?type=person").json()["entities"]] == ["Dana Reyes"]
    assert client.get("/api/entities?type=banana").status_code == 422
    assert client.get("/api/graph?type=banana").status_code == 422
    assert len(client.get("/api/entities?limit=2").json()["entities"]) == 2
    assert client.get("/api/entities?limit=0").status_code == 422


def test_neighborhood_endpoint(client):
    upload_text(client)
    acme = client.get("/api/entities?q=acme corp").json()["entities"][0]
    n = client.get(f"/api/entities/{acme['id']}/neighborhood?depth=1").json()
    assert {x["name"] for x in n["nodes"]} == {"Acme Corp", "Beta Systems"} and len(n["edges"]) == 1
    assert client.get(f"/api/entities/{acme['id']}/neighborhood?depth=9").status_code == 422


def test_fact_detail_shows_the_exact_quote_and_where_it_came_from(client):
    upload_text(client, title="Annual report")
    edge = next(e for e in client.get("/api/graph").json()["edges"] if e["predicate"] == "served as cto of")
    f = client.get(f"/api/facts/{edge['id']}").json()
    assert (f["subject"], f["object"], f["valid_from"], f["valid_to"]) == ("Dana Reyes", "Acme", "2019", "2022")
    [src] = f["sources"]
    assert src["quote"] == S2 and src["document_title"] == "Annual report" and S2 in src["passage"] and src["verified"] is False


def test_graph_can_be_limited_to_one_document(client):
    a = upload_text(client, title="A")
    other = [rel("Zed", "founded", "Omega", "Zed founded Omega in 1999.", otype="organization")]
    client.llm.extract = lambda p: {"relations": other}
    b = upload_text(client, "Zed founded Omega in 1999. Nothing else happens in this short note.", title="B")
    ga = client.get(f"/api/graph?document_id={a['id']}").json()
    gb = client.get(f"/api/graph?document_id={b['id']}").json()
    assert {n["name"] for n in gb["nodes"]} == {"Zed", "Omega"} and "Zed" not in {n["name"] for n in ga["nodes"]}
    assert client.get("/api/graph?limit=2").json()["truncated"] is True


def test_health_reports_the_model_state(client, monkeypatch):
    from src.services import llm as llm_mod
    monkeypatch.setattr(llm_mod.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(llm_mod.httpx.ConnectError("no")))
    import server
    monkeypatch.setattr(server, "llm_status", llm_mod.llm_status)
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["llm"]["ready"] is False and "Cannot reach Ollama" in h["llm"]["detail"]
