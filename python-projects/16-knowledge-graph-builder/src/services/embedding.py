"""Embeddings: turn text into vectors (Ollama), keep them in the database, find the nearest ones"""
import hashlib
from abc import ABC, abstractmethod

import httpx
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import Settings, get_settings
from src.models.embedding import Embedding
from src.models.graph import Chunk, Document, Entity, Fact


_ANY = object()   # 'every owner' (used when reading a document's own passages, which are already its owner's)


class EmbeddingError(RuntimeError):
    """The embedding model could not be reached or answered badly (message is safe to show)"""


class Embedder(ABC):
    name: str = "embedder"

    @abstractmethod
    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        """kind is 'document' (things to search in) or 'query' (the question)"""


class OllamaEmbedder(Embedder):
    BATCH = 32

    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout
        self.name = f"ollama:{model}"

    def _prefix(self, kind: str) -> str:
        if self.model.startswith("nomic"):  # nomic-embed-text was trained with these task prefixes
            return "search_query: " if kind == "query" else "search_document: "
        return ""

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH):
            batch = [self._prefix(kind) + t for t in texts[i:i + self.BATCH]]
            try:
                r = httpx.post(f"{self.base_url}/api/embed", json={"model": self.model, "input": batch}, timeout=self.timeout)
            except httpx.ConnectError as exc:
                raise EmbeddingError(f"Cannot reach Ollama at {self.base_url} for embeddings. Is it running?") from exc
            except httpx.HTTPError as exc:
                raise EmbeddingError(f"Embedding request failed ({type(exc).__name__})") from exc
            if r.status_code == 404:
                raise EmbeddingError(f"Ollama does not have the embedding model '{self.model}'. Run: ollama pull {self.model}")
            if r.status_code != 200:
                raise EmbeddingError(f"Ollama returned HTTP {r.status_code} for embeddings")
            try:
                vectors = r.json()["embeddings"]
            except (KeyError, ValueError) as exc:
                raise EmbeddingError("Ollama returned an unexpected embedding response") from exc
            if len(vectors) != len(batch):
                raise EmbeddingError("Ollama returned the wrong number of embeddings")
            out.extend(vectors)
        return out


def get_embedder(settings: Settings | None = None) -> Embedder:
    s = settings or get_settings()
    return OllamaEmbedder(s.ollama_base_url, s.embedding_model)


def to_bytes(vec) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_bytes(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


def normalize(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.where(n == 0, 1, n)


def cosine_top(query: np.ndarray, matrix: np.ndarray, k: int) -> list[tuple[int, float]]:
    """Indices and cosine similarity of the k rows of `matrix` closest to `query`, best first"""
    if matrix.shape[0] == 0:
        return []
    sims = normalize(matrix) @ normalize(query.reshape(1, -1)).T
    sims = sims.ravel()
    order = np.argsort(-sims)[:k]
    return [(int(i), float(sims[i])) for i in order]


def fact_text(f: Fact) -> str:
    obj = f.object.name if f.object is not None else f.object_value
    when = f" ({f.valid_from or ''}..{f.valid_to or ''})" if (f.valid_from or f.valid_to) else ""
    return f"{f.subject.name} {f.predicate} {obj}{when}"


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def ensure_chunk_embeddings(db: Session, embedder: Embedder, document_id: str | None = None, *, owner_id=_ANY) -> int:
    """Embed every passage that has no vector from this model yet. Returns how many were added."""
    have = select(Embedding.chunk_id).where(Embedding.model == embedder.name, Embedding.chunk_id.is_not(None))
    q = select(Chunk).where(~Chunk.id.in_(have))
    if document_id:
        q = q.where(Chunk.document_id == document_id)
    if owner_id is not _ANY:
        q = q.join(Document, Document.id == Chunk.document_id).where(Document.owner_id == owner_id)
    chunks = db.execute(q).scalars().all()
    if not chunks:
        return 0
    vectors = embedder.embed([c.text for c in chunks], "document")
    for c, v in zip(chunks, vectors):
        db.add(Embedding(chunk_id=c.id, model=embedder.name, dim=len(v), vector=to_bytes(v), text_hash=_hash(c.text)))
    db.flush()
    return len(chunks)


def ensure_fact_embeddings(db: Session, embedder: Embedder, facts: list[Fact]) -> dict[str, np.ndarray]:
    """Vectors for the given facts (made now if missing or if the fact's wording changed since)"""
    if not facts:
        return {}
    ids = [f.id for f in facts]
    rows = {}
    for i in range(0, len(ids), 500):
        for e in db.execute(select(Embedding).where(Embedding.model == embedder.name, Embedding.fact_id.in_(ids[i:i + 500]))).scalars():
            rows[e.fact_id] = e
    out, todo = {}, []
    for f in facts:
        text = fact_text(f)
        e = rows.get(f.id)
        if e is not None and e.text_hash == _hash(text):
            out[f.id] = from_bytes(e.vector)
        else:
            todo.append((f, text, e))
    if todo:
        vectors = embedder.embed([t for _, t, _ in todo], "document")
        for (f, text, e), v in zip(todo, vectors):
            if e is None:
                db.add(Embedding(fact_id=f.id, model=embedder.name, dim=len(v), vector=to_bytes(v), text_hash=_hash(text)))
            else:
                e.vector, e.dim, e.text_hash = to_bytes(v), len(v), _hash(text)
            out[f.id] = np.asarray(v, dtype=np.float32)
        db.flush()
    return out


def top_chunks(db: Session, embedder: Embedder, question: str, k: int, document_id: str | None = None, *, owner_id: int | None = None) -> list[tuple[Chunk, float]]:
    """The k passages closest to the question (passage search, as in a plain RAG assistant)"""
    ensure_chunk_embeddings(db, embedder, document_id, owner_id=owner_id)
    q = (select(Chunk, Embedding.vector).join(Embedding, Embedding.chunk_id == Chunk.id)
         .join(Document, Document.id == Chunk.document_id).where(Embedding.model == embedder.name, Document.owner_id == owner_id))
    if document_id:
        q = q.where(Chunk.document_id == document_id)
    rows = db.execute(q).all()
    if not rows:
        return []
    matrix = np.vstack([from_bytes(v) for _, v in rows])
    qv = np.asarray(embedder.embed([question], "query")[0], dtype=np.float32)
    return [(rows[i][0], s) for i, s in cosine_top(qv, matrix, k)]
