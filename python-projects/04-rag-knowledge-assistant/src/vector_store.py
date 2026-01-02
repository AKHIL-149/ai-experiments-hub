"""Vector store using ChromaDB for document retrieval."""

from typing import List, Dict, Tuple
import chromadb
from chromadb.config import Settings
import os
from pathlib import Path


class VectorStore:
    """Manages document storage and retrieval using ChromaDB."""

    def __init__(self, collection_name: str = "documents", persist_directory: str = None):
        self.collection_name = collection_name

        if persist_directory is None:
            persist_directory = os.getenv("CHROMA_DB_PATH", "./data/chroma")

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory)
        )

        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, str]],
        ids: List[str]
    ):
        """Add documents with their embeddings to the store."""
        self.collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5
    ) -> Tuple[List[str], List[Dict[str, str]], List[float]]:
        """Query similar documents."""
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )

        if not results['documents'] or not results['documents'][0]:
            return [], [], []

        documents = results['documents'][0]
        metadatas = results['metadatas'][0]
        distances = results['distances'][0]

        return documents, metadatas, distances

    def get_collection_stats(self) -> Dict:
        """Get statistics about the collection."""
        count = self.collection.count()
        return {
            "name": self.collection_name,
            "document_count": count,
            "persist_directory": str(self.persist_directory)
        }

    def delete_collection(self):
        """Delete the entire collection."""
        self.client.delete_collection(self.collection_name)

    def clear_collection(self):
        """Clear all documents from the collection."""
        try:
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            print(f"Error clearing collection: {e}")
