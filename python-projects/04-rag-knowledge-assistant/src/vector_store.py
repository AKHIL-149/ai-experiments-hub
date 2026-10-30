"""Vector store using ChromaDB for document retrieval."""

from typing import List, Dict, Tuple, Optional
import chromadb
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def default_persist_directory() -> Path:
    """CHROMA_DB_PATH, with relative paths anchored to the project (not the current directory).

    Otherwise running the tool from another folder would silently open a different, empty
    knowledge base.
    """
    configured = Path(os.getenv("CHROMA_DB_PATH", "./data/chroma")).expanduser()
    return configured if configured.is_absolute() else (PROJECT_ROOT / configured).resolve()


class VectorStore:
    """Manages document storage and retrieval using ChromaDB."""

    def __init__(self, collection_name: str = "documents", persist_directory: Optional[str] = None):
        self.collection_name = collection_name

        self.persist_directory = (
            Path(persist_directory) if persist_directory else default_persist_directory()
        )
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        self.collection = self._open_collection()

    def _open_collection(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
        ids: List[str]
    ):
        """Add (or overwrite, by id) documents with their embeddings."""
        self.collection.upsert(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )

    def delete_source(self, source: str) -> int:
        """Delete every chunk that came from one file; returns how many were removed."""
        existing = self.collection.get(where={"source": source}, include=[])
        ids = existing["ids"]
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    def source_info(self, source: str) -> Dict:
        """Chunk count and stored content fingerprint for one file."""
        existing = self.collection.get(where={"source": source}, include=["metadatas"])
        hashes = {m.get("fingerprint") for m in existing["metadatas"]}
        return {"chunks": len(existing["ids"]), "fingerprint": hashes.pop() if len(hashes) == 1 else None}

    def list_sources(self) -> List[Dict]:
        """Every indexed file with its chunk count."""
        everything = self.collection.get(include=["metadatas"])
        counts: Dict[str, int] = {}
        for meta in everything["metadatas"]:
            source = meta.get("source", "unknown")
            counts[source] = counts.get(source, 0) + 1
        return [{"source": s, "chunks": n} for s, n in sorted(counts.items())]

    def all_chunks(self) -> Tuple[List[str], List[str], List[Dict]]:
        """(ids, texts, metadatas) of every stored chunk, for keyword search."""
        everything = self.collection.get(include=["documents", "metadatas"])
        return everything["ids"], everything["documents"], everything["metadatas"]

    def get_embeddings(self, ids: List[str]) -> Dict[str, List[float]]:
        """Stored embeddings for the given chunk ids."""
        if not ids:
            return {}
        found = self.collection.get(ids=ids, include=["embeddings"])
        return {i: list(e) for i, e in zip(found["ids"], found["embeddings"])}

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5
    ) -> Tuple[List[str], List[Dict], List[float], List[str]]:
        """Nearest chunks by cosine distance: (texts, metadatas, distances, ids)."""
        count = self.collection.count()
        if count == 0:
            return [], [], [], []

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, count)
        )

        if not results['documents'] or not results['documents'][0]:
            return [], [], [], []

        return (
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0],
            results['ids'][0],
        )

    def get_collection_stats(self) -> Dict:
        """Get statistics about the collection."""
        sources = self.list_sources()
        return {
            "name": self.collection_name,
            "chunk_count": self.collection.count(),
            "document_count": len(sources),
            "documents": sources,
            "persist_directory": str(self.persist_directory)
        }

    def delete_collection(self):
        """Delete the entire collection."""
        self.client.delete_collection(self.collection_name)

    def clear_collection(self):
        """Clear all documents from the collection."""
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass  # nothing to delete
        self.collection = self._open_collection()
