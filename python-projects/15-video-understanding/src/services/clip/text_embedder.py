"""
CLIP text embedder
Generates CLIP embeddings for text queries
"""

import logging
from typing import List, Optional, Dict, Union
from dataclasses import dataclass
import numpy as np

from src.services.clip.clip_model import CLIPModel, CLIPConfig

logger = logging.getLogger(__name__)


@dataclass
class TextEmbedding:
    """CLIP embedding for a text query"""
    text: str
    embedding: np.ndarray
    metadata: Optional[Dict[str, any]] = None


@dataclass
class QueryResult:
    """Result of a text-to-image search query"""
    query: str
    query_embedding: np.ndarray
    matches: List[Dict[str, any]]  # List of {frame_idx, similarity, frame_path, timestamp}
    total_matches: int
    search_time: Optional[float] = None
    metadata: Optional[Dict[str, any]] = None


class CLIPTextEmbedder:
    """
    Generate CLIP embeddings for text queries
    Supports query expansion, prompt templates, and caching
    """

    def __init__(
        self,
        clip_model: Optional[CLIPModel] = None,
        config: Optional[CLIPConfig] = None,
        cache_queries: bool = True
    ):
        """
        Initialize CLIP text embedder

        Args:
            clip_model: Existing CLIP model instance
            config: CLIP configuration (if clip_model not provided)
            cache_queries: Cache query embeddings
        """
        self.clip_model = clip_model or CLIPModel(config)
        self.cache_queries = cache_queries

        # Query cache
        self._query_cache: Dict[str, np.ndarray] = {}

    def embed_text(
        self,
        text: str,
        use_cache: bool = True
    ) -> TextEmbedding:
        """
        Generate CLIP embedding for text

        Args:
            text: Text to embed
            use_cache: Use cached embedding if available

        Returns:
            TextEmbedding
        """
        # Check cache
        if use_cache and self.cache_queries and text in self._query_cache:
            logger.debug(f"Using cached embedding for query: '{text}'")
            embedding = self._query_cache[text]
        else:
            # Generate embedding
            embedding = self.clip_model.encode_text(text)

            # Cache if enabled
            if self.cache_queries:
                self._query_cache[text] = embedding

        return TextEmbedding(
            text=text,
            embedding=embedding,
            metadata={'embedding_dim': len(embedding)}
        )

    def embed_texts(
        self,
        texts: List[str],
        use_cache: bool = True
    ) -> List[TextEmbedding]:
        """
        Generate embeddings for multiple texts

        Args:
            texts: List of texts to embed
            use_cache: Use cached embeddings

        Returns:
            List of TextEmbedding
        """
        logger.info(f"Embedding {len(texts)} text queries")

        # Check cache
        uncached_texts = []
        uncached_indices = []
        embeddings_dict = {}

        for idx, text in enumerate(texts):
            if use_cache and self.cache_queries and text in self._query_cache:
                embeddings_dict[idx] = self._query_cache[text]
            else:
                uncached_texts.append(text)
                uncached_indices.append(idx)

        # Generate embeddings for uncached texts
        if uncached_texts:
            logger.info(f"Generating {len(uncached_texts)} new embeddings")
            embedding_matrix = self.clip_model.encode_text(uncached_texts)

            # Cache and store
            for i, idx in enumerate(uncached_indices):
                embedding = embedding_matrix[i]
                embeddings_dict[idx] = embedding

                # Cache
                if self.cache_queries:
                    self._query_cache[uncached_texts[i]] = embedding

        # Create TextEmbedding objects
        text_embeddings = []
        for idx, text in enumerate(texts):
            text_embeddings.append(TextEmbedding(
                text=text,
                embedding=embeddings_dict[idx],
                metadata={'embedding_dim': len(embeddings_dict[idx])}
            ))

        return text_embeddings

    def create_prompt(
        self,
        query: str,
        template: str = "a photo of {}"
    ) -> str:
        """
        Create a prompt from query using template

        Args:
            query: Raw query text
            template: Prompt template with {} placeholder

        Returns:
            Formatted prompt
        """
        return template.format(query)

    def expand_query(
        self,
        query: str,
        templates: Optional[List[str]] = None
    ) -> List[str]:
        """
        Expand query into multiple prompts using templates

        Args:
            query: Original query
            templates: List of prompt templates

        Returns:
            List of expanded prompts
        """
        if templates is None:
            templates = [
                "a photo of {}",
                "a picture of {}",
                "an image showing {}",
                "{}",
                "a scene with {}"
            ]

        expanded = [template.format(query) for template in templates]
        return expanded

    def embed_with_expansion(
        self,
        query: str,
        templates: Optional[List[str]] = None,
        aggregate: str = "mean"
    ) -> TextEmbedding:
        """
        Embed query with template expansion and aggregation

        Args:
            query: Original query
            templates: Prompt templates
            aggregate: Aggregation method (mean, max, concat)

        Returns:
            TextEmbedding with aggregated embedding
        """
        # Expand query
        expanded_queries = self.expand_query(query, templates)

        # Embed all variations
        embeddings = self.embed_texts(expanded_queries)

        # Aggregate embeddings
        embedding_matrix = np.vstack([emb.embedding for emb in embeddings])

        if aggregate == "mean":
            aggregated = np.mean(embedding_matrix, axis=0)
        elif aggregate == "max":
            aggregated = np.max(embedding_matrix, axis=0)
        elif aggregate == "concat":
            aggregated = embedding_matrix.flatten()
        else:
            aggregated = embedding_matrix[0]  # Use first

        # Normalize
        aggregated = aggregated / (np.linalg.norm(aggregated) + 1e-8)

        return TextEmbedding(
            text=query,
            embedding=aggregated,
            metadata={
                'expanded_queries': expanded_queries,
                'aggregation': aggregate,
                'num_variations': len(expanded_queries)
            }
        )

    def search_frames(
        self,
        query: str,
        frame_embeddings: np.ndarray,
        frame_paths: Optional[List] = None,
        timestamps: Optional[List[float]] = None,
        top_k: int = 10,
        min_similarity: float = 0.0,
        use_expansion: bool = False
    ) -> QueryResult:
        """
        Search frames using text query

        Args:
            query: Text query
            frame_embeddings: Frame embedding matrix (n_frames x dim)
            frame_paths: Optional list of frame paths
            timestamps: Optional list of timestamps
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold
            use_expansion: Use query expansion

        Returns:
            QueryResult
        """
        import time
        start_time = time.time()

        # Generate query embedding
        if use_expansion:
            query_emb = self.embed_with_expansion(query)
        else:
            query_emb = self.embed_text(query)

        # Compute similarities
        similarities = frame_embeddings @ query_emb.embedding

        # Filter by minimum similarity
        valid_indices = np.where(similarities >= min_similarity)[0]
        valid_similarities = similarities[valid_indices]

        # Sort by similarity
        sorted_indices = np.argsort(valid_similarities)[::-1][:top_k]
        top_indices = valid_indices[sorted_indices]
        top_similarities = valid_similarities[sorted_indices]

        # Create match results
        matches = []
        for idx, similarity in zip(top_indices, top_similarities):
            match = {
                'frame_idx': int(idx),
                'similarity': float(similarity),
            }

            if frame_paths:
                match['frame_path'] = frame_paths[idx]

            if timestamps:
                match['timestamp'] = timestamps[idx]

            matches.append(match)

        search_time = time.time() - start_time

        result = QueryResult(
            query=query,
            query_embedding=query_emb.embedding,
            matches=matches,
            total_matches=len(matches),
            search_time=search_time,
            metadata={
                'top_k': top_k,
                'min_similarity': min_similarity,
                'use_expansion': use_expansion,
                'total_frames': len(frame_embeddings)
            }
        )

        logger.info(
            f"Query '{query}' returned {len(matches)} results in {search_time:.3f}s"
        )

        return result

    def batch_search(
        self,
        queries: List[str],
        frame_embeddings: np.ndarray,
        frame_paths: Optional[List] = None,
        timestamps: Optional[List[float]] = None,
        top_k: int = 10
    ) -> List[QueryResult]:
        """
        Search frames with multiple queries

        Args:
            queries: List of text queries
            frame_embeddings: Frame embedding matrix
            frame_paths: Optional frame paths
            timestamps: Optional timestamps
            top_k: Results per query

        Returns:
            List of QueryResult
        """
        logger.info(f"Batch searching {len(queries)} queries")

        results = []
        for query in queries:
            result = self.search_frames(
                query, frame_embeddings, frame_paths, timestamps, top_k
            )
            results.append(result)

        return results

    def find_best_query(
        self,
        queries: List[str],
        frame_embeddings: np.ndarray
    ) -> Dict[str, any]:
        """
        Find which query best matches the frame set

        Args:
            queries: List of candidate queries
            frame_embeddings: Frame embedding matrix

        Returns:
            Dictionary with best query and statistics
        """
        # Embed all queries
        query_embeddings = self.embed_texts(queries)

        # Compute average similarity for each query
        query_scores = []
        for query_emb in query_embeddings:
            similarities = frame_embeddings @ query_emb.embedding
            avg_similarity = np.mean(similarities)
            max_similarity = np.max(similarities)

            query_scores.append({
                'query': query_emb.text,
                'avg_similarity': float(avg_similarity),
                'max_similarity': float(max_similarity),
                'median_similarity': float(np.median(similarities))
            })

        # Sort by average similarity
        query_scores.sort(key=lambda x: x['avg_similarity'], reverse=True)

        return {
            'best_query': query_scores[0]['query'],
            'all_scores': query_scores
        }

    def semantic_tagging(
        self,
        candidate_tags: List[str],
        frame_embeddings: np.ndarray,
        threshold: float = 0.3
    ) -> Dict[str, float]:
        """
        Tag video frames semantically

        Args:
            candidate_tags: List of possible tags
            frame_embeddings: Frame embedding matrix
            threshold: Minimum similarity to assign tag

        Returns:
            Dictionary mapping tags to relevance scores
        """
        # Embed tags
        tag_embeddings = self.embed_texts(candidate_tags)

        # Compute tag relevance
        tag_scores = {}

        for tag_emb in tag_embeddings:
            # Compute similarity with all frames
            similarities = frame_embeddings @ tag_emb.embedding

            # Score as average similarity above threshold
            relevant_sims = similarities[similarities >= threshold]

            if len(relevant_sims) > 0:
                score = np.mean(relevant_sims)
                tag_scores[tag_emb.text] = float(score)

        return tag_scores

    def clear_cache(self):
        """Clear query cache"""
        self._query_cache.clear()
        logger.info("Query cache cleared")

    def get_cache_size(self) -> int:
        """Get number of cached queries"""
        return len(self._query_cache)

    def get_cache_memory(self) -> float:
        """
        Get approximate cache memory usage in MB

        Returns:
            Memory usage in megabytes
        """
        total_bytes = sum(
            emb.nbytes for emb in self._query_cache.values()
        )
        return total_bytes / (1024 * 1024)

    def save_query_cache(self, output_path):
        """
        Save query cache to disk

        Args:
            output_path: Output file path
        """
        import pickle

        with open(output_path, 'wb') as f:
            pickle.dump(self._query_cache, f)

        logger.info(f"Saved query cache to {output_path}")

    def load_query_cache(self, cache_path):
        """
        Load query cache from disk

        Args:
            cache_path: Cache file path
        """
        import pickle

        with open(cache_path, 'rb') as f:
            self._query_cache = pickle.load(f)

        logger.info(f"Loaded query cache from {cache_path}")


def search_video_frames(
    query: str,
    frame_embeddings: np.ndarray,
    top_k: int = 10,
    model_name: str = "ViT-B/32"
) -> QueryResult:
    """
    Convenience function to search video frames

    Args:
        query: Text query
        frame_embeddings: Frame embedding matrix
        top_k: Number of results
        model_name: CLIP model name

    Returns:
        QueryResult
    """
    config = CLIPConfig(model_name=model_name)
    embedder = CLIPTextEmbedder(config=config)
    return embedder.search_frames(query, frame_embeddings, top_k=top_k)
