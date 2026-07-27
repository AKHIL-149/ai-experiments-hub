"""
Contextual search engine for multi-modal video search
Combine visual, audio, and text signals with contextual re-ranking
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class SearchMode(str, Enum):
    """Search modes"""
    VISUAL_ONLY = "visual_only"
    TEXT_ONLY = "text_only"
    AUDIO_ONLY = "audio_only"
    VISUAL_TEXT = "visual_text"
    ALL_MODALITIES = "all_modalities"
    ADAPTIVE = "adaptive"


class ReRankingMethod(str, Enum):
    """Re-ranking methods"""
    NONE = "none"  # No re-ranking
    TEMPORAL_COHERENCE = "temporal_coherence"  # Boost temporally coherent results
    DIVERSITY = "diversity"  # Promote diverse results
    IMPORTANCE = "importance"  # Boost important scenes
    COMBINED = "combined"  # Combine multiple signals


@dataclass
class SearchQuery:
    """Multi-modal search query"""
    query_text: Optional[str] = None
    query_visual_embedding: Optional[np.ndarray] = None
    query_audio_embedding: Optional[np.ndarray] = None

    # Search parameters
    search_mode: SearchMode = SearchMode.ADAPTIVE
    top_k: int = 20

    # Filters
    video_ids: Optional[List[str]] = None
    time_range: Optional[Tuple[float, float]] = None
    min_importance: Optional[float] = None

    # Re-ranking
    rerank_method: ReRankingMethod = ReRankingMethod.COMBINED
    rerank_top_k: int = 100  # Re-rank top N results

    # Context
    include_context: bool = True
    context_window: float = 5.0  # seconds before/after


@dataclass
class SearchResult:
    """Single search result"""
    video_id: str
    scene_id: int
    timestamp: float
    score: float

    # Content
    visual_description: Optional[str] = None
    transcript_text: Optional[str] = None

    # Metadata
    importance_score: float = 0.0
    matched_modalities: List[str] = field(default_factory=list)
    context_before: Optional[str] = None
    context_after: Optional[str] = None

    # Re-ranking
    original_score: float = 0.0
    rerank_boost: float = 0.0

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResults:
    """Collection of search results"""
    results: List[SearchResult]
    query: SearchQuery
    total_results: int
    search_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContextualSearchEngine:
    """
    Multi-modal contextual search engine
    Combines visual, audio, and text signals with intelligent re-ranking
    """

    def __init__(
        self,
        vector_retriever=None,
        multimodal_embedder=None,
        scene_enricher=None,
        enable_reranking: bool = True,
        enable_context: bool = True,
    ):
        """
        Initialize contextual search engine

        Args:
            vector_retriever: MultiModalVectorRetriever instance
            multimodal_embedder: MultiModalEmbedder instance
            scene_enricher: SceneEnricher instance
            enable_reranking: Enable result re-ranking
            enable_context: Include contextual information
        """
        self.vector_retriever = vector_retriever
        self.multimodal_embedder = multimodal_embedder
        self.scene_enricher = scene_enricher
        self.enable_reranking = enable_reranking
        self.enable_context = enable_context

        logger.info(
            f"Initialized ContextualSearchEngine "
            f"(reranking={enable_reranking}, context={enable_context})"
        )

    def search(
        self,
        query: SearchQuery,
        enriched_scenes: Optional[List[Any]] = None,
    ) -> SearchResults:
        """
        Perform contextual multi-modal search

        Args:
            query: Search query
            enriched_scenes: Optional pre-enriched scenes for context

        Returns:
            SearchResults
        """
        import time
        start_time = time.time()

        logger.info(
            f"Searching with mode={query.search_mode.value}, "
            f"top_k={query.top_k}"
        )

        # Determine which modalities to search
        search_params = self._prepare_search_parameters(query)

        # Retrieve initial results from vector store
        initial_results = self._retrieve_from_vector_store(
            query, search_params
        )

        # Convert to SearchResult objects
        search_results = self._convert_to_search_results(
            initial_results, query
        )

        # Re-rank results if enabled
        if self.enable_reranking and query.rerank_method != ReRankingMethod.NONE:
            search_results = self._rerank_results(
                search_results, query, enriched_scenes
            )

        # Add context if enabled
        if self.enable_context and query.include_context:
            search_results = self._add_context_to_results(
                search_results, query, enriched_scenes
            )

        # Limit to top_k
        search_results = search_results[:query.top_k]

        search_time = time.time() - start_time

        return SearchResults(
            results=search_results,
            query=query,
            total_results=len(search_results),
            search_time=search_time,
            metadata={
                "search_mode": query.search_mode.value,
                "reranking_method": query.rerank_method.value if self.enable_reranking else "none",
            },
        )

    def _prepare_search_parameters(
        self,
        query: SearchQuery,
    ) -> Dict[str, Any]:
        """
        Prepare search parameters based on query

        Args:
            query: Search query

        Returns:
            Search parameters dict
        """
        params = {
            "n_results": query.rerank_top_k if self.enable_reranking else query.top_k,
        }

        # Add filters
        if query.video_ids:
            params["video_ids"] = query.video_ids

        if query.time_range:
            params["time_range"] = query.time_range

        if query.min_importance is not None:
            params["min_importance"] = query.min_importance

        return params

    def _retrieve_from_vector_store(
        self,
        query: SearchQuery,
        params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Retrieve results from vector store

        Args:
            query: Search query
            params: Search parameters

        Returns:
            List of raw results
        """
        if not self.vector_retriever:
            logger.warning("No vector retriever configured")
            return []

        # Determine search mode
        if query.search_mode == SearchMode.ADAPTIVE:
            # Adaptively choose based on available query data
            has_visual = query.query_visual_embedding is not None
            has_text = query.query_text is not None
            has_audio = query.query_audio_embedding is not None

            if has_visual and has_text:
                mode = SearchMode.VISUAL_TEXT
            elif has_text:
                mode = SearchMode.TEXT_ONLY
            elif has_visual:
                mode = SearchMode.VISUAL_ONLY
            elif has_audio:
                mode = SearchMode.AUDIO_ONLY
            else:
                logger.warning("No query data provided")
                return []
        else:
            mode = query.search_mode

        # Execute search based on mode
        if mode == SearchMode.VISUAL_ONLY:
            results = self.vector_retriever.search_frames(
                query_embedding=query.query_visual_embedding,
                **params
            )

        elif mode == SearchMode.TEXT_ONLY:
            results = self.vector_retriever.search_transcripts(
                query_text=query.query_text,
                **params
            )

        elif mode == SearchMode.VISUAL_TEXT:
            results = self.vector_retriever.hybrid_search(
                visual_embedding=query.query_visual_embedding,
                text_query=query.query_text,
                **params
            )

        elif mode == SearchMode.ALL_MODALITIES:
            # Use multimodal embedder to create combined query
            if self.multimodal_embedder:
                fused = self.multimodal_embedder.fuse_embeddings(
                    visual_embedding=query.query_visual_embedding,
                    text_embedding=None,  # Would need text embedding
                    audio_embedding=query.query_audio_embedding,
                )
                results = self.vector_retriever.search_scenes(
                    query_embedding=fused.fused_embedding,
                    **params
                )
            else:
                # Fallback to visual-text
                results = self.vector_retriever.hybrid_search(
                    visual_embedding=query.query_visual_embedding,
                    text_query=query.query_text,
                    **params
                )

        else:
            logger.warning(f"Unsupported search mode: {mode}")
            return []

        return results if results else []

    def _convert_to_search_results(
        self,
        raw_results: List[Dict[str, Any]],
        query: SearchQuery,
    ) -> List[SearchResult]:
        """
        Convert raw results to SearchResult objects

        Args:
            raw_results: Raw vector store results
            query: Search query

        Returns:
            List of SearchResult objects
        """
        search_results = []

        for result in raw_results:
            # Extract matched modalities
            matched_modalities = []
            if result.get("matched_visual"):
                matched_modalities.append("visual")
            if result.get("matched_text"):
                matched_modalities.append("text")
            if result.get("matched_audio"):
                matched_modalities.append("audio")

            search_result = SearchResult(
                video_id=result.get("video_id", ""),
                scene_id=result.get("scene_id", 0),
                timestamp=result.get("timestamp", 0.0),
                score=result.get("score", 0.0),
                visual_description=result.get("visual_description"),
                transcript_text=result.get("transcript_text"),
                importance_score=result.get("importance", 0.0),
                matched_modalities=matched_modalities,
                original_score=result.get("score", 0.0),
                metadata=result.get("metadata", {}),
            )

            search_results.append(search_result)

        return search_results

    def _rerank_results(
        self,
        results: List[SearchResult],
        query: SearchQuery,
        enriched_scenes: Optional[List[Any]] = None,
    ) -> List[SearchResult]:
        """
        Re-rank search results using contextual signals

        Args:
            results: Initial search results
            query: Search query
            enriched_scenes: Enriched scenes for context

        Returns:
            Re-ranked results
        """
        if not results:
            return results

        logger.debug(f"Re-ranking {len(results)} results using {query.rerank_method.value}")

        # Apply re-ranking method
        if query.rerank_method == ReRankingMethod.TEMPORAL_COHERENCE:
            results = self._rerank_by_temporal_coherence(results)

        elif query.rerank_method == ReRankingMethod.DIVERSITY:
            results = self._rerank_by_diversity(results, query.top_k)

        elif query.rerank_method == ReRankingMethod.IMPORTANCE:
            results = self._rerank_by_importance(results)

        elif query.rerank_method == ReRankingMethod.COMBINED:
            # Combine multiple signals
            results = self._rerank_combined(results)

        # Sort by final score
        results.sort(key=lambda x: x.score, reverse=True)

        return results

    def _rerank_by_temporal_coherence(
        self,
        results: List[SearchResult],
    ) -> List[SearchResult]:
        """
        Re-rank by temporal coherence (boost clustered results)

        Args:
            results: Search results

        Returns:
            Re-ranked results
        """
        # Group by video
        by_video = {}
        for result in results:
            video_id = result.video_id
            if video_id not in by_video:
                by_video[video_id] = []
            by_video[video_id].append(result)

        # For each video, find temporal clusters
        for video_id, video_results in by_video.items():
            video_results.sort(key=lambda x: x.timestamp)

            # Detect clusters (results within 30 seconds)
            cluster_bonus = 0.1
            cluster_threshold = 30.0

            for i, result in enumerate(video_results):
                # Check neighbors
                neighbors = 0
                if i > 0 and abs(result.timestamp - video_results[i-1].timestamp) < cluster_threshold:
                    neighbors += 1
                if i < len(video_results) - 1 and abs(result.timestamp - video_results[i+1].timestamp) < cluster_threshold:
                    neighbors += 1

                # Boost score based on neighbors
                if neighbors > 0:
                    boost = cluster_bonus * neighbors
                    result.rerank_boost += boost
                    result.score = result.original_score + result.rerank_boost

        return results

    def _rerank_by_diversity(
        self,
        results: List[SearchResult],
        target_count: int,
    ) -> List[SearchResult]:
        """
        Re-rank to promote diversity (MMR-style)

        Args:
            results: Search results
            target_count: Target number of diverse results

        Returns:
            Re-ranked results
        """
        if len(results) <= target_count:
            return results

        # Maximal Marginal Relevance approach
        selected = []
        remaining = results.copy()

        # Select first (highest scoring)
        selected.append(remaining.pop(0))

        lambda_param = 0.7  # Balance relevance vs diversity

        while len(selected) < target_count and remaining:
            best_idx = 0
            best_mmr = -float('inf')

            for i, candidate in enumerate(remaining):
                # Relevance score
                relevance = candidate.original_score

                # Diversity penalty (max similarity to selected)
                max_similarity = 0.0
                for sel in selected:
                    # Simple diversity: penalize same video/nearby timestamps
                    if sel.video_id == candidate.video_id:
                        time_diff = abs(sel.timestamp - candidate.timestamp)
                        if time_diff < 30.0:  # Within 30 seconds
                            similarity = 1.0 - (time_diff / 30.0)
                            max_similarity = max(max_similarity, similarity)

                # MMR score
                mmr = lambda_param * relevance - (1 - lambda_param) * max_similarity

                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        # Add remaining results after diverse set
        selected.extend(remaining)

        return selected

    def _rerank_by_importance(
        self,
        results: List[SearchResult],
    ) -> List[SearchResult]:
        """
        Re-rank by importance score

        Args:
            results: Search results

        Returns:
            Re-ranked results
        """
        importance_weight = 0.3

        for result in results:
            boost = importance_weight * result.importance_score
            result.rerank_boost += boost
            result.score = result.original_score + result.rerank_boost

        return results

    def _rerank_combined(
        self,
        results: List[SearchResult],
    ) -> List[SearchResult]:
        """
        Re-rank using combined signals

        Args:
            results: Search results

        Returns:
            Re-ranked results
        """
        # First apply importance boost
        results = self._rerank_by_importance(results)

        # Then apply temporal coherence
        results = self._rerank_by_temporal_coherence(results)

        # Finally apply diversity
        results = self._rerank_by_diversity(results, len(results) // 2)

        return results

    def _add_context_to_results(
        self,
        results: List[SearchResult],
        query: SearchQuery,
        enriched_scenes: Optional[List[Any]] = None,
    ) -> List[SearchResult]:
        """
        Add contextual information to results

        Args:
            results: Search results
            query: Search query
            enriched_scenes: Enriched scenes

        Returns:
            Results with context
        """
        if not enriched_scenes:
            return results

        # Create scene lookup
        scene_lookup = {}
        for scene in enriched_scenes:
            key = (scene.video_id if hasattr(scene, 'video_id') else '', scene.scene_id)
            scene_lookup[key] = scene

        # Add context to each result
        for result in results:
            key = (result.video_id, result.scene_id)
            scene = scene_lookup.get(key)

            if scene:
                # Get previous scene (context before)
                prev_key = (result.video_id, result.scene_id - 1)
                prev_scene = scene_lookup.get(prev_key)
                if prev_scene and hasattr(prev_scene, 'description'):
                    result.context_before = prev_scene.description

                # Get next scene (context after)
                next_key = (result.video_id, result.scene_id + 1)
                next_scene = scene_lookup.get(next_key)
                if next_scene and hasattr(next_scene, 'description'):
                    result.context_after = next_scene.description

        return results

    def aggregate_results_by_video(
        self,
        results: SearchResults,
    ) -> Dict[str, List[SearchResult]]:
        """
        Aggregate results by video

        Args:
            results: Search results

        Returns:
            Dict of video_id -> results
        """
        by_video = {}

        for result in results.results:
            video_id = result.video_id
            if video_id not in by_video:
                by_video[video_id] = []
            by_video[video_id].append(result)

        # Sort each video's results by timestamp
        for video_id in by_video:
            by_video[video_id].sort(key=lambda x: x.timestamp)

        return by_video

    def get_result_summary(
        self,
        results: SearchResults,
    ) -> Dict[str, Any]:
        """
        Get summary statistics for search results

        Args:
            results: Search results

        Returns:
            Summary dict
        """
        if not results.results:
            return {
                "total_results": 0,
                "unique_videos": 0,
                "unique_scenes": 0,
            }

        unique_videos = set(r.video_id for r in results.results)
        unique_scenes = set((r.video_id, r.scene_id) for r in results.results)

        modality_counts = {"visual": 0, "text": 0, "audio": 0}
        for result in results.results:
            for modality in result.matched_modalities:
                modality_counts[modality] += 1

        avg_score = sum(r.score for r in results.results) / len(results.results)
        avg_importance = sum(r.importance_score for r in results.results) / len(results.results)

        return {
            "total_results": len(results.results),
            "unique_videos": len(unique_videos),
            "unique_scenes": len(unique_scenes),
            "avg_score": avg_score,
            "avg_importance": avg_importance,
            "modality_matches": modality_counts,
            "search_time": results.search_time,
        }


def search_contextual(
    query_text: Optional[str] = None,
    query_visual_embedding: Optional[np.ndarray] = None,
    top_k: int = 20,
    vector_retriever=None,
) -> SearchResults:
    """
    Convenience function for contextual search

    Args:
        query_text: Text query
        query_visual_embedding: Visual embedding
        top_k: Number of results
        vector_retriever: Vector retriever instance

    Returns:
        SearchResults
    """
    query = SearchQuery(
        query_text=query_text,
        query_visual_embedding=query_visual_embedding,
        top_k=top_k,
    )

    engine = ContextualSearchEngine(vector_retriever=vector_retriever)
    return engine.search(query)
