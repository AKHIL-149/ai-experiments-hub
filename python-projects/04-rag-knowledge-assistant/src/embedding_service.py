"""Embedding generation service using sentence-transformers."""

from typing import List
from sentence_transformers import SentenceTransformer
import os


class EmbeddingService:
    """Generate embeddings for text using local models."""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.getenv(
            "EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        print(f"Loading embedding model: {self.model_name}...")
        self.model = SentenceTransformer(self.model_name)
        print("Embedding model loaded successfully")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple documents."""
        return self.model.encode(texts, convert_to_numpy=True).tolist()

    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query."""
        return self.model.encode(text, convert_to_numpy=True).tolist()

    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this model."""
        return self.model.get_sentence_embedding_dimension()
