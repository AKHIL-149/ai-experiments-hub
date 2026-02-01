"""
Deduplicator for Research Assistant.

Removes duplicate content across multiple sources using:
- SHA256 hash for exact duplicates
- Embedding similarity for semantic duplicates
"""

import hashlib
import logging
from typing import List, Set, Optional
from dataclasses import dataclass


@dataclass
class SourceInfo:
    """Minimal source information for deduplication."""
    id: str
    content: str
    content_hash: str
    source_type: str
    title: str
    url: Optional[str] = None


class Deduplicator:
    """Removes duplicate information across sources."""

    def __init__(
        self,
        exact_match: bool = True,
        semantic_threshold: float = 0.95,
        embedding_model=None
    ):
        """
        Initialize deduplicator.

        Args:
            exact_match: Enable exact duplicate detection via SHA256
            semantic_threshold: Cosine similarity threshold for semantic duplicates (0-1)
            embedding_model: Optional embedding model for semantic similarity
        """
        self.exact_match = exact_match
        self.semantic_threshold = semantic_threshold
        self.embedding_model = embedding_model

        self.stats = {
            'total_sources': 0,
            'exact_duplicates': 0,
            'semantic_duplicates': 0,
            'unique_sources': 0
        }

        logging.info(f"Deduplicator initialized (exact: {exact_match}, semantic threshold: {semantic_threshold})")

    def deduplicate(self, sources: List[SourceInfo]) -> List[SourceInfo]:
        """
        Remove duplicate sources.

        Args:
            sources: List of SourceInfo objects

        Returns:
            List of unique SourceInfo objects
        """
        self.stats['total_sources'] = len(sources)

        if not sources:
            return []

        unique_sources = []
        seen_hashes: Set[str] = set()
        seen_embeddings = []

        for source in sources:
            # Step 1: Check exact duplicates (SHA256 hash)
            if self.exact_match:
                if source.content_hash in seen_hashes:
                    self.stats['exact_duplicates'] += 1
                    logging.debug(f"Exact duplicate found: {source.title[:50]}...")
                    continue

            # Step 2: Check semantic duplicates (embedding similarity)
            if self.embedding_model and seen_embeddings:
                is_duplicate = self._is_semantic_duplicate(source, seen_embeddings)
                if is_duplicate:
                    self.stats['semantic_duplicates'] += 1
                    logging.debug(f"Semantic duplicate found: {source.title[:50]}...")
                    continue

            # Not a duplicate - add to unique sources
            unique_sources.append(source)
            seen_hashes.add(source.content_hash)

            if self.embedding_model:
                # Generate and store embedding for future comparisons
                embedding = self._generate_embedding(source.content)
                seen_embeddings.append({
                    'source_id': source.id,
                    'embedding': embedding
                })

        self.stats['unique_sources'] = len(unique_sources)

        logging.info(
            f"Deduplication: {len(sources)} sources → {len(unique_sources)} unique "
            f"(exact dups: {self.stats['exact_duplicates']}, "
            f"semantic dups: {self.stats['semantic_duplicates']})"
        )

        return unique_sources

    def _is_semantic_duplicate(
        self,
        source: SourceInfo,
        seen_embeddings: List[dict]
    ) -> bool:
        """
        Check if source is semantically duplicate.

        Args:
            source: Source to check
            seen_embeddings: List of previously seen embeddings

        Returns:
            True if semantic duplicate, False otherwise
        """
        if not self.embedding_model:
            return False

        # Generate embedding for current source
        current_embedding = self._generate_embedding(source.content)

        # Compare with all seen embeddings
        for seen in seen_embeddings:
            similarity = self._cosine_similarity(current_embedding, seen['embedding'])

            if similarity >= self.semantic_threshold:
                logging.debug(
                    f"Semantic similarity {similarity:.3f} >= {self.semantic_threshold} "
                    f"between {source.id} and {seen['source_id']}"
                )
                return True

        return False

    def _generate_embedding(self, text: str):
        """
        Generate embedding for text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        if not self.embedding_model:
            return None

        # Truncate very long text (embeddings models have token limits)
        max_length = 8000  # characters
        if len(text) > max_length:
            text = text[:max_length]

        try:
            # Use embedding model to generate embedding
            embedding = self.embedding_model.encode(text, convert_to_tensor=False)
            return embedding
        except Exception as e:
            logging.error(f"Failed to generate embedding: {e}")
            return None

    def _cosine_similarity(self, embedding1, embedding2) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity (0-1)
        """
        try:
            import numpy as np

            # Normalize embeddings
            norm1 = np.linalg.norm(embedding1)
            norm2 = np.linalg.norm(embedding2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            # Calculate cosine similarity
            similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)

            # Clamp to [0, 1] range
            return max(0.0, min(1.0, float(similarity)))

        except Exception as e:
            logging.error(f"Failed to calculate cosine similarity: {e}")
            return 0.0

    @staticmethod
    def calculate_content_hash(content: str) -> str:
        """
        Calculate SHA256 hash of content.

        Args:
            content: Content string

        Returns:
            SHA256 hash (hexadecimal)
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def get_stats(self) -> dict:
        """Get deduplication statistics."""
        stats = self.stats.copy()

        if stats['total_sources'] > 0:
            stats['deduplication_rate'] = (
                (stats['exact_duplicates'] + stats['semantic_duplicates']) /
                stats['total_sources']
            )
        else:
            stats['deduplication_rate'] = 0.0

        return stats

    def reset_stats(self):
        """Reset deduplication statistics."""
        self.stats = {
            'total_sources': 0,
            'exact_duplicates': 0,
            'semantic_duplicates': 0,
            'unique_sources': 0
        }

    def get_info(self) -> dict:
        """Get information about the deduplicator."""
        return {
            'exact_match_enabled': self.exact_match,
            'semantic_threshold': self.semantic_threshold,
            'embedding_model_available': self.embedding_model is not None,
            'stats': self.get_stats()
        }
