"""RAG engine combining retrieval and generation."""

from typing import List, Dict, Tuple
import hashlib
from pathlib import Path

from document_processor import DocumentProcessor, Document
from embedding_service import EmbeddingService
from vector_store import VectorStore
from llm_client import LLMClient


class RAGEngine:
    """Main RAG system orchestrating all components."""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        embedding_model: str = None,
        llm_model: str = None,
        collection_name: str = "documents"
    ):
        self.doc_processor = DocumentProcessor(chunk_size, chunk_overlap)
        self.embedding_service = EmbeddingService(embedding_model)
        self.vector_store = VectorStore(collection_name)
        self.llm_client = LLMClient(llm_model)

    def add_document(self, file_path: str) -> int:
        """Add a document to the knowledge base."""
        print(f"Processing: {file_path}")

        # Load and chunk document
        documents = self.doc_processor.load_file(file_path)
        print(f"Created {len(documents)} chunks")

        # Generate embeddings
        print("Generating embeddings...")
        texts = [doc.content for doc in documents]
        embeddings = self.embedding_service.embed_documents(texts)

        # Create unique IDs
        file_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]
        ids = [f"{file_hash}_{i}" for i in range(len(documents))]

        # Store in vector database
        metadatas = [doc.metadata for doc in documents]
        self.vector_store.add_documents(texts, embeddings, metadatas, ids)

        print(f"Successfully added {len(documents)} chunks to knowledge base")
        return len(documents)

    def query(
        self,
        question: str,
        top_k: int = 5,
        temperature: float = 0.7
    ) -> Tuple[str, List[Dict]]:
        """Query the knowledge base and generate an answer."""

        # Generate query embedding
        query_embedding = self.embedding_service.embed_query(question)

        # Retrieve relevant documents
        documents, metadatas, distances = self.vector_store.query(
            query_embedding,
            n_results=top_k
        )

        if not documents:
            return "No relevant documents found in the knowledge base.", []

        # Build context from retrieved documents
        context = self._build_context(documents, metadatas, distances)

        # Generate answer using LLM
        prompt = self._build_prompt(question, context["text"])
        answer = self.llm_client.generate(prompt, temperature=temperature)

        return answer, context["sources"]

    def _build_context(
        self,
        documents: List[str],
        metadatas: List[Dict],
        distances: List[float]
    ) -> Dict:
        """Build context from retrieved documents."""
        context_parts = []
        sources = []

        for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
            context_parts.append(f"[Document {i+1}]\n{doc}\n")

            source_info = {
                "index": i + 1,
                "source": meta.get("source", "unknown"),
                "relevance": 1 - dist,  # Convert distance to similarity
                "preview": doc[:100] + "..." if len(doc) > 100 else doc
            }

            if "page" in meta:
                source_info["page"] = meta["page"]

            sources.append(source_info)

        return {
            "text": "\n".join(context_parts),
            "sources": sources
        }

    def _build_prompt(self, question: str, context: str) -> str:
        """Build the prompt for the LLM."""
        return f"""You are a helpful assistant that answers questions based on the provided context.

Context:
{context}

Question: {question}

Instructions:
- Answer the question using only information from the context above
- If the context doesn't contain enough information, say so
- Be concise and accurate
- Cite which document number you're using if relevant

Answer:"""

    def get_stats(self) -> Dict:
        """Get knowledge base statistics."""
        return self.vector_store.get_collection_stats()

    def clear_knowledge_base(self):
        """Clear all documents from the knowledge base."""
        self.vector_store.clear_collection()
        print("Knowledge base cleared")
