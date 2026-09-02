"""
Unit + integration tests for the 'My Documents' RAG feature (AKHIL-254):
- src/services/document_processor.py (text extraction + chunking)
- src/services/vector_store.py (ChromaDB wrapper, per-user isolation)
- src/services/embedding_service.py (sentence-transformers wrapper)
- server.py's /api/documents endpoints and their wiring into
  /api/research's search_documents branch

server.py's vector_store/documents_dir are process-wide singletons
pointed at the real ./data/chroma and ./data/documents by default -
tests that go through the live API endpoints redirect both to a
tmp_path via monkeypatch (see `isolated_document_storage` fixture)
rather than writing real chunks/files into production data, the same
class of isolation conftest.py already applies to the SQL database.
"""

import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.document_processor import (
    extract_text,
    chunk_text,
    DocumentProcessingError,
)
from src.services.vector_store import VectorStore
from src.services.embedding_service import EmbeddingService

import server as server_module
from server import app, db_manager

client = TestClient(app)


# --- document_processor.py -------------------------------------------------

class TestExtractText:
    def test_extract_txt(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Hello world.\n\nSecond paragraph.")
        text = extract_text(str(f), "txt")
        assert "Hello world." in text
        assert "Second paragraph." in text

    def test_extract_md(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nSome content.")
        text = extract_text(str(f), "md")
        assert "Some content." in text

    def test_extract_unsupported_type(self, tmp_path):
        f = tmp_path / "doc.exe"
        f.write_bytes(b"binary")
        with pytest.raises(DocumentProcessingError):
            extract_text(str(f), "exe")

    def test_extract_txt_latin1_fallback(self, tmp_path):
        f = tmp_path / "doc.txt"
        # A byte sequence that's invalid UTF-8 but valid latin-1.
        f.write_bytes(b"caf\xe9 au lait")
        text = extract_text(str(f), "txt")
        assert "caf" in text


class TestChunkText:
    def test_empty_text(self):
        assert chunk_text("") == []

    def test_short_text_single_chunk(self):
        chunks = chunk_text("Just one short paragraph.", chunk_size=1000, overlap=150)
        assert len(chunks) == 1
        assert chunks[0] == "Just one short paragraph."

    def test_multiple_paragraphs_merge_into_one_chunk(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        chunks = chunk_text(text, chunk_size=1000, overlap=150)
        assert len(chunks) == 1
        assert "Para one." in chunks[0]
        assert "Para three." in chunks[0]

    def test_long_text_splits_into_multiple_chunks(self):
        paragraphs = [f"Paragraph number {i} with some filler text." for i in range(50)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, chunk_size=200, overlap=30)
        assert len(chunks) > 1
        assert all(len(c) <= 200 + 30 for c in chunks)  # overlap tail can push slightly over

    def test_single_paragraph_longer_than_chunk_size_hard_splits(self):
        text = "x" * 5000
        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        assert len(chunks) > 1
        assert all(chunks)  # no empty chunks

    def test_overlap_carries_context_between_chunks(self):
        paragraphs = [f"Sentence {i}. " * 5 for i in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, chunk_size=150, overlap=50)
        assert len(chunks) > 1
        # Some suffix of chunk N should reappear as a prefix of chunk N+1.
        assert chunks[0][-20:] in chunks[1]


# --- vector_store.py ---------------------------------------------------------

class TestVectorStore:
    def _fake_embedding(self, seed):
        # Deterministic tiny fake embedding - dimensionality doesn't
        # matter to VectorStore itself, only that add/search agree.
        import random
        r = random.Random(seed)
        return [r.random() for _ in range(16)]

    def test_add_and_search_returns_chunk(self, tmp_path):
        vs = VectorStore(persist_dir=str(tmp_path / "chroma"), collection_name="test")
        emb = self._fake_embedding("chunk1")
        vs.add_chunks(
            document_id="doc1",
            user_id="user1",
            chunks=["The sky is blue."],
            embeddings=[emb],
            filename="sky.txt"
        )
        results = vs.search(emb, user_id="user1", top_k=5)
        assert len(results) == 1
        assert results[0]["chunk_text"] == "The sky is blue."
        assert results[0]["filename"] == "sky.txt"
        assert results[0]["document_id"] == "doc1"
        assert results[0]["similarity"] > 0.99  # querying with the exact same vector

    def test_search_scoped_to_user_returns_empty_for_other_user(self, tmp_path):
        vs = VectorStore(persist_dir=str(tmp_path / "chroma"), collection_name="test")
        emb = self._fake_embedding("chunk2")
        vs.add_chunks(
            document_id="doc1",
            user_id="user1",
            chunks=["Private content."],
            embeddings=[emb],
            filename="private.txt"
        )
        # user2 must never see user1's chunks - the core privacy
        # guarantee of My Documents.
        results = vs.search(emb, user_id="user2", top_k=5)
        assert results == []

    def test_search_empty_collection_returns_empty_list(self, tmp_path):
        vs = VectorStore(persist_dir=str(tmp_path / "chroma"), collection_name="test")
        results = vs.search(self._fake_embedding("q"), user_id="nobody", top_k=5)
        assert results == []

    def test_delete_document_removes_its_chunks(self, tmp_path):
        vs = VectorStore(persist_dir=str(tmp_path / "chroma"), collection_name="test")
        emb = self._fake_embedding("chunk3")
        vs.add_chunks(
            document_id="doc-to-delete",
            user_id="user1",
            chunks=["Ephemeral content."],
            embeddings=[emb],
            filename="temp.txt"
        )
        assert len(vs.search(emb, user_id="user1", top_k=5)) == 1

        vs.delete_document("doc-to-delete")

        assert vs.search(emb, user_id="user1", top_k=5) == []

    def test_add_chunks_empty_list_returns_zero(self, tmp_path):
        vs = VectorStore(persist_dir=str(tmp_path / "chroma"), collection_name="test")
        assert vs.add_chunks("doc1", "user1", [], [], "empty.txt") == 0


# --- embedding_service.py -----------------------------------------------------

class TestEmbeddingService:
    @pytest.fixture(scope="class")
    def service(self):
        # Reuses the same model server.py already loaded at import time
        # (HF cache is warm), so this doesn't re-download anything.
        return EmbeddingService()

    def test_embed_texts_returns_one_vector_per_input(self, service):
        vectors = service.embed_texts(["hello", "world"])
        assert len(vectors) == 2
        assert len(vectors[0]) == len(vectors[1])
        assert len(vectors[0]) > 0

    def test_embed_texts_empty_list(self, service):
        assert service.embed_texts([]) == []

    def test_embed_query_returns_single_vector(self, service):
        vector = service.embed_query("hello")
        assert isinstance(vector, list)
        assert all(isinstance(x, float) for x in vector)

    def test_similar_texts_are_closer_than_dissimilar_ones(self, service):
        import math

        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(y * y for y in b))
            return dot / (norm_a * norm_b)

        v_cat = service.embed_query("The cat sat on the mat.")
        v_kitten = service.embed_query("A kitten rested on the rug.")
        v_unrelated = service.embed_query("Quarterly tax filing deadlines.")

        assert cosine(v_cat, v_kitten) > cosine(v_cat, v_unrelated)


# --- server.py: /api/documents + /api/research integration --------------------

@pytest.fixture
def isolated_document_storage(tmp_path, monkeypatch):
    """
    Redirects server.py's module-level documents_dir/vector_store to a
    tmp_path for the duration of a test, so hitting the real
    /api/documents endpoint doesn't write into the real ./data/chroma
    or ./data/documents used by the live app. embedding_service is left
    as-is (real, already-loaded singleton) since computing an embedding
    isn't destructive - only where chunks/files get persisted is.
    """
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    monkeypatch.setattr(server_module, "documents_dir", docs_dir)

    test_vector_store = VectorStore(persist_dir=str(tmp_path / "chroma"), collection_name="test_docs")
    monkeypatch.setattr(server_module, "vector_store", test_vector_store)

    yield docs_dir, test_vector_store


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_users():
    from src.core.database import User
    with db_manager.get_session() as db_session:
        db_session.query(User).filter(
            User.username.in_(["doc_owner", "doc_other_user"])
        ).delete(synchronize_session=False)
        db_session.commit()
    yield


def _register_and_login(username):
    client.post("/api/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "testpass123"
    })
    login_response = client.post("/api/auth/login", json={
        "username": username,
        "password": "testpass123"
    })
    return login_response.cookies


class TestDocumentEndpoints:
    def test_upload_list_delete_roundtrip(self, isolated_document_storage):
        cookies = _register_and_login("doc_owner")

        response = client.post(
            "/api/documents",
            files={"file": ("notes.txt", io.BytesIO(b"Some uploaded content here."), "text/plain")},
            cookies=cookies
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["filename"] == "notes.txt"
        assert data["chunk_count"] >= 1
        document_id = data["id"]

        list_response = client.get("/api/documents", cookies=cookies)
        assert list_response.status_code == 200
        docs = list_response.json()["documents"]
        assert any(d["id"] == document_id for d in docs)

        delete_response = client.delete(f"/api/documents/{document_id}", cookies=cookies)
        assert delete_response.status_code == 200

        list_after = client.get("/api/documents", cookies=cookies).json()["documents"]
        assert not any(d["id"] == document_id for d in list_after)

    def test_upload_unsupported_type_rejected(self, isolated_document_storage):
        cookies = _register_and_login("doc_owner")

        response = client.post(
            "/api/documents",
            files={"file": ("virus.exe", io.BytesIO(b"binary"), "application/octet-stream")},
            cookies=cookies
        )
        assert response.status_code == 400

    def test_upload_empty_file_rejected(self, isolated_document_storage):
        cookies = _register_and_login("doc_owner")

        response = client.post(
            "/api/documents",
            files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
            cookies=cookies
        )
        assert response.status_code == 400

    def test_upload_requires_auth(self, isolated_document_storage):
        # client is a module-level TestClient shared across this whole
        # file - httpx merges any per-request `cookies=` passed by
        # earlier tests into the client's own persistent cookie jar, so
        # a stale session_token from a previous logged-in test can leak
        # into this "no auth" request unless explicitly cleared first.
        client.cookies.clear()
        response = client.post(
            "/api/documents",
            files={"file": ("notes.txt", io.BytesIO(b"content"), "text/plain")}
        )
        assert response.status_code == 401

    def test_cannot_delete_other_users_document(self, isolated_document_storage):
        owner_cookies = _register_and_login("doc_owner")
        other_cookies = _register_and_login("doc_other_user")

        upload = client.post(
            "/api/documents",
            files={"file": ("secret.txt", io.BytesIO(b"Owner's private notes."), "text/plain")},
            cookies=owner_cookies
        )
        document_id = upload.json()["id"]

        response = client.delete(f"/api/documents/{document_id}", cookies=other_cookies)
        assert response.status_code == 404

        # Still there for the actual owner.
        docs = client.get("/api/documents", cookies=owner_cookies).json()["documents"]
        assert any(d["id"] == document_id for d in docs)

        client.delete(f"/api/documents/{document_id}", cookies=owner_cookies)

    def test_other_users_documents_not_listed(self, isolated_document_storage):
        owner_cookies = _register_and_login("doc_owner")
        other_cookies = _register_and_login("doc_other_user")

        upload = client.post(
            "/api/documents",
            files={"file": ("owner_only.txt", io.BytesIO(b"Only the owner should see this.").read(), "text/plain")},
            cookies=owner_cookies
        )
        document_id = upload.json()["id"]

        other_docs = client.get("/api/documents", cookies=other_cookies).json()["documents"]
        assert not any(d["id"] == document_id for d in other_docs)

        client.delete(f"/api/documents/{document_id}", cookies=owner_cookies)


class TestDocumentResearchIntegration:
    """
    The end-to-end case that matters most: content uploaded via
    /api/documents is actually retrievable through /api/research when
    search_documents=True, and stays scoped to the uploading user.
    """

    def test_uploaded_document_is_retrieved_by_research_query(self, isolated_document_storage):
        cookies = _register_and_login("doc_owner")

        unique_content = (
            "The Glimmerwood Cipher is a fictional encoding scheme "
            "invented solely for this test. It maps each letter to the "
            "sum of its position and a rotating key called the "
            "Glimmerwood Offset, which increments by three every four "
            "characters."
        )
        upload = client.post(
            "/api/documents",
            files={"file": ("cipher.txt", io.BytesIO(unique_content.encode()), "text/plain")},
            cookies=cookies
        )
        assert upload.json()["status"] == "ready"

        response = client.post(
            "/api/research",
            json={
                "query": "What is the Glimmerwood Offset in the Glimmerwood Cipher?",
                "search_web": False,
                "search_arxiv": False,
                "search_documents": True,
                "max_sources": 5,
                "citation_style": "APA"
            },
            cookies=cookies
        )
        assert response.status_code == 200
        data = response.json()

        assert len(data["sources"]) >= 1
        assert data["sources"][0]["type"] == "document"
        assert any("cipher.txt" in c for c in data["citations"])

    def test_document_search_scoped_to_uploading_user(self, isolated_document_storage):
        owner_cookies = _register_and_login("doc_owner")
        other_cookies = _register_and_login("doc_other_user")

        unique_content = (
            "The Thistlebrook Index is a fictional metric invented "
            "solely for this isolation test, computed from vertex "
            "degree and the Thistlebrook coefficient."
        )
        client.post(
            "/api/documents",
            files={"file": ("thistlebrook.txt", io.BytesIO(unique_content.encode()), "text/plain")},
            cookies=owner_cookies
        )

        # doc_other_user has uploaded nothing - searching their own
        # documents for this owner-only term must find zero sources.
        response = client.post(
            "/api/research",
            json={
                "query": "What is the Thistlebrook Index?",
                "search_web": False,
                "search_arxiv": False,
                "search_documents": True,
                "max_sources": 5,
                "citation_style": "APA"
            },
            cookies=other_cookies
        )
        assert response.status_code == 200
        assert response.json()["sources"] == []
