"""
Embedding Service for Research Assistant.

Thin wrapper around sentence-transformers so document chunking/upload
and query-time retrieval always use the exact same model instance,
loaded once - SentenceTransformer's constructor is slow (downloads/
loads model weights), so this is a genuine singleton, not just
convenience.
"""

import logging
import os
from typing import List, Optional

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("sentence-transformers not installed. Document embedding will not work.")


class EmbeddingService:
    """Generates embeddings for document chunks and search queries."""

    def __init__(self, model_name: Optional[str] = None):
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ValueError("EmbeddingService requires 'sentence-transformers' package")

        # .env's EMBEDDING_MODEL includes a "sentence-transformers/" org
        # prefix (matching its HuggingFace Hub ID); SentenceTransformer
        # accepts that form directly, no need to strip it.
        model_name = model_name or os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name

        logging.info(f"EmbeddingService initialized with model: {model_name}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts (e.g. document chunks)."""
        if not texts:
            return []
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string."""
        embedding = self.model.encode([text], convert_to_numpy=True)
        return embedding[0].tolist()


_embedding_service_instance: Optional[EmbeddingService] = None


def get_embedding_service(model_name: Optional[str] = None) -> EmbeddingService:
    """Get or create the global EmbeddingService instance."""
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService(model_name)
    return _embedding_service_instance
