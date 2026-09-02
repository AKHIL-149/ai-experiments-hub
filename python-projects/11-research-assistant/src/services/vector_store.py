"""
Vector Store for Research Assistant.

Thin wrapper around ChromaDB for storing and retrieving document chunk
embeddings. Embeddings are computed elsewhere (embedding_service.py,
via sentence-transformers) and passed in pre-computed - this module
never invokes ChromaDB's own default embedding function, so it stays
consistent with the exact model configured via EMBEDDING_MODEL.
"""

import logging
from typing import List, Dict, Any, Optional

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logging.warning("chromadb not installed. Document search will not work.")


class VectorStore:
    """Stores and searches document chunk embeddings via ChromaDB."""

    def __init__(
        self,
        persist_dir: str = './data/chroma',
        collection_name: str = 'research_documents'
    ):
        """
        Initialize the vector store.

        Args:
            persist_dir: Directory ChromaDB persists its index to
            collection_name: Name of the ChromaDB collection to use
        """
        if not CHROMADB_AVAILABLE:
            raise ValueError("VectorStore requires 'chromadb' package")

        # anonymized_telemetry=False for privacy. Doesn't fully silence
        # it in this chromadb version, though - confirmed live, "Failed
        # to send telemetry event ... capture() takes 1 positional
        # argument but 3 were given" still logs on every add/query
        # (a version mismatch between chromadb's telemetry code and the
        # installed posthog package). Harmless - it's a caught exception
        # around a fire-and-forget network call, not a functional
        # failure - just noisy; left the setting in regardless since
        # it's still correct to declare disabled.
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=chromadb.Settings(anonymized_telemetry=False)
        )
        # Cosine distance matches how embedding similarity is normally
        # compared (sentence-transformers embeddings aren't guaranteed
        # unit-length, but cosine is still the right space for semantic
        # similarity here, not raw L2/dot-product).
        self.collection = self.client.get_or_create_collection(
            collection_name,
            metadata={'hnsw:space': 'cosine'}
        )

        logging.info(f"VectorStore initialized (dir={persist_dir}, collection={collection_name})")

    def add_chunks(
        self,
        document_id: str,
        user_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        filename: str
    ) -> int:
        """
        Store a document's chunks and their embeddings.

        Args:
            document_id: Document this chunk set belongs to
            user_id: Owning user - stored as metadata so search() can
                scope queries to one user's documents only
            chunks: Chunk text, same order as embeddings
            embeddings: Pre-computed embedding vectors, same order as chunks
            filename: Original filename, stored as metadata for display

        Returns:
            Number of chunks stored
        """
        if not chunks:
            return 0

        ids = [f"{document_id}:{i}" for i in range(len(chunks))]
        metadatas = [
            {
                'document_id': document_id,
                'user_id': user_id,
                'filename': filename,
                'chunk_index': i
            }
            for i in range(len(chunks))
        ]

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )

        return len(chunks)

    def search(
        self,
        query_embedding: List[float],
        user_id: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find the most semantically similar chunks for a query, scoped
        to one user's own documents.

        Args:
            query_embedding: Pre-computed embedding of the search query
            user_id: Only chunks belonging to this user's documents are
                searched - critical for not leaking one user's uploaded
                documents into another user's research results
            top_k: Maximum number of chunks to return

        Returns:
            List of {chunk_text, document_id, filename, chunk_index,
            similarity} dicts, best match first
        """
        # Nothing stored yet for anyone - querying an empty collection
        # raises in some Chroma versions rather than returning [].
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={'user_id': user_id}
        )

        chunks = []
        ids = results.get('ids', [[]])[0]
        documents = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]

        for i in range(len(ids)):
            metadata = metadatas[i] or {}
            # Cosine distance -> similarity (0 distance = identical = 1.0
            # similarity). Chroma's cosine distance is in [0, 2]; clamp
            # defensively since floating point can push similarity
            # slightly outside [0, 1].
            similarity = max(0.0, min(1.0, 1.0 - (distances[i] / 2.0)))

            chunks.append({
                'chunk_text': documents[i],
                'document_id': metadata.get('document_id'),
                'filename': metadata.get('filename'),
                'chunk_index': metadata.get('chunk_index'),
                'similarity': similarity
            })

        return chunks

    def delete_document(self, document_id: str):
        """Remove all chunks belonging to a document."""
        try:
            self.collection.delete(where={'document_id': document_id})
        except Exception as e:
            logging.warning(f"Failed to delete chunks for document {document_id}: {e}")


_vector_store_instance: Optional[VectorStore] = None


def get_vector_store(
    persist_dir: str = './data/chroma',
    collection_name: str = 'research_documents'
) -> VectorStore:
    """Get or create the global VectorStore instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore(persist_dir, collection_name)
    return _vector_store_instance
