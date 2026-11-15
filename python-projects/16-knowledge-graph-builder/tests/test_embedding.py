import httpx
import numpy as np
import pytest
from sqlalchemy import func, select

from src.models.embedding import Embedding
from src.models.graph import Chunk, Entity, Fact
from src.services import embedding as emb
from src.services.embedding import (EmbeddingError, OllamaEmbedder, cosine_top, ensure_chunk_embeddings, ensure_fact_embeddings,
                                    fact_text, from_bytes, to_bytes, top_chunks)
from tests.conftest import FakeEmbedder


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def test_vectors_roundtrip_and_cosine_ranking():
    v = [0.5, -1.25, 3.0]
    assert list(from_bytes(to_bytes(v))) == v
    matrix = np.array([[1, 0], [0, 1], [1, 1], [-1, 0]], dtype=np.float32)
    top = cosine_top(np.array([1, 0.1], dtype=np.float32), matrix, 3)
    assert [i for i, _ in top] == [0, 2, 1] and top[0][1] > top[1][1] > top[2][1]
    assert cosine_top(np.array([1, 0], dtype=np.float32), np.zeros((0, 2), dtype=np.float32), 3) == []
    assert cosine_top(np.array([1, 0], dtype=np.float32), np.array([[0, 0], [1, 0]], dtype=np.float32), 2)[0][0] == 1  # zero rows do not crash


def test_ollama_embedder_request_shape_batches_and_prefixes(monkeypatch):
    sent = []

    def post(url, json=None, timeout=None):
        sent.append((url, json))
        return Resp(200, {"embeddings": [[1.0, 2.0] for _ in json["input"]]})
    monkeypatch.setattr(emb.httpx, "post", post)
    e = OllamaEmbedder("http://x:11434/", "nomic-embed-text")
    out = e.embed([f"t{i}" for i in range(70)], "query")
    assert len(out) == 70 and [len(s[1]["input"]) for s in sent] == [32, 32, 6]
    assert sent[0][0] == "http://x:11434/api/embed" and sent[0][1]["input"][0] == "search_query: t0" and sent[0][1]["model"] == "nomic-embed-text"
    assert e.embed(["a"], "document") and sent[-1][1]["input"] == ["search_document: a"]
    other = OllamaEmbedder("http://x", "mxbai-embed-large")
    other.embed(["a"])
    assert sent[-1][1]["input"] == ["a"]  # no prefix for models that were not trained with one
    assert e.name == "ollama:nomic-embed-text" and e.embed([]) == []


@pytest.mark.parametrize("result,fragment", [
    (httpx.ConnectError("x"), "Cannot reach Ollama"),
    (httpx.ReadTimeout("x"), "failed"),
    (Resp(404, {}), "ollama pull"),
    (Resp(500, {}), "HTTP 500"),
    (Resp(200, {"nope": 1}), "unexpected"),
    (Resp(200, {"embeddings": [[1.0]]}), "wrong number"),
])
def test_ollama_embedder_errors_are_readable(monkeypatch, result, fragment):
    def post(url, json=None, timeout=None):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(emb.httpx, "post", post)
    with pytest.raises(EmbeddingError, match=fragment):
        OllamaEmbedder("http://x", "m").embed(["a", "b"])


def test_chunk_embeddings_are_made_once_and_per_document(world):
    db, e = world.db, FakeEmbedder()
    other = world.new_doc("Other")
    db.commit()
    assert ensure_chunk_embeddings(db, e) == 2
    assert ensure_chunk_embeddings(db, e) == 0 and len(e.calls) == 1
    extra = Chunk(document_id=world.doc, index=1, start=0, end=5, text="More text")
    db.add(extra)
    db.commit()
    assert ensure_chunk_embeddings(db, e, other[0]) == 0           # asked for another document: nothing to do
    assert ensure_chunk_embeddings(db, e, world.doc) == 1
    assert db.scalar(select(func.count()).select_from(Embedding)) == 3


def test_a_new_embedding_model_gets_its_own_vectors(world):
    db = world.db
    ensure_chunk_embeddings(db, FakeEmbedder())
    other = FakeEmbedder()
    other.name = "fake:other"
    assert ensure_chunk_embeddings(db, other) == 1 and db.scalar(select(func.count()).select_from(Embedding)) == 2


def test_fact_embeddings_are_cached_and_refreshed_when_the_wording_changes(world):
    db, e = world.db, FakeEmbedder()
    acme, beta = world.ent("Acme"), world.ent("Beta")
    f = world.fact(acme, "acquired", beta)
    db.commit()
    v1 = ensure_fact_embeddings(db, e, [f])
    assert len(e.calls) == 1 and list(v1) == [f.id]
    ensure_fact_embeddings(db, e, [f])
    assert len(e.calls) == 1                                        # served from the database
    acme.name = "Acme Corporation"                                    # a rename or merge changes the fact's text
    db.commit()
    db.refresh(f)
    v2 = ensure_fact_embeddings(db, e, [f])
    assert len(e.calls) == 2 and not np.array_equal(v1[f.id], v2[f.id])
    assert db.scalar(select(func.count()).select_from(Embedding)) == 1
    assert ensure_fact_embeddings(db, e, []) == {}


def test_fact_text_includes_dates_and_values(world):
    db = world.db
    a, b = world.ent("Acme"), world.ent("Beta")
    assert fact_text(world.fact(a, "acquired", b, frm="2020")) == "Acme acquired Beta (2020..)"
    assert fact_text(world.fact(a, "employs", value="340 people")) == "Acme employs 340 people"
    assert fact_text(world.fact(a, "led", b, frm="2015", to="2018")) == "Acme led Beta (2015..2018)"


def test_top_chunks_rank_filter_and_index_on_demand(world):
    db, e = world.db, FakeEmbedder()
    ch1 = db.get(Chunk, world.chunk)
    ch1.text = "Acme acquired Beta Systems in 2020."
    d2, c2 = world.new_doc("Two")
    db.get(Chunk, c2).text = "Gamma grows roses in the garden."
    db.commit()
    res = top_chunks(db, e, "Who bought Beta Systems?", 2)                # nothing was embedded yet: done on demand
    assert [c.id for c, _ in res] == [world.chunk, c2] and res[0][1] > res[1][1]
    assert [c.id for c, _ in top_chunks(db, e, "Who bought Beta Systems?", 2, d2)] == [c2]
    assert len(top_chunks(db, e, "roses", 1)) == 1


def test_top_chunks_with_nothing_indexed_is_empty(db):
    assert top_chunks(db, FakeEmbedder(), "anything", 3) == []


def test_embeddings_disappear_with_their_chunk_or_fact(world):
    db, e = world.db, FakeEmbedder()
    a, b = world.ent("Acme"), world.ent("Beta")
    f = world.fact(a, "acquired", b)
    ensure_chunk_embeddings(db, e)
    ensure_fact_embeddings(db, e, [f])
    db.commit()
    assert db.scalar(select(func.count()).select_from(Embedding)) == 2
    db.delete(db.get(Fact, f.id))
    db.commit()
    assert db.scalar(select(func.count()).select_from(Embedding)) == 1
    db.delete(db.get(Chunk, world.chunk))
    db.commit()
    assert db.scalar(select(func.count()).select_from(Embedding)) == 0


def test_normalize_leaves_zero_rows_alone():
    out = emb.normalize(np.array([[3.0, 4.0], [0.0, 0.0]], dtype=np.float32))
    assert np.allclose(out[0], [0.6, 0.8]) and np.all(out[1] == 0) and np.all(np.isfinite(out))
