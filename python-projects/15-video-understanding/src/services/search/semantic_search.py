"""
Semantic video search using multi-modal retrieval
Search across videos using natural language queries
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class SearchMode(str, Enum):
    """Search modes"""
    VISUAL_ONLY = "visual_only"  # Search frames only
    TEXT_ONLY = "text_only"  # Search transcripts only
    MULTIMODAL = "multimodal"  # Search both frames and transcripts
    HYBRID = "hybrid"  # Weighted combination


@dataclass
class SearchConfig:
    """Configuration for semantic search"""
    # Search mode
    mode: SearchMode = SearchMode.MULTIMODAL

    # Retrieval settings
    top_k: int = 10
    min_similarity: float = 0.0

    # Weights for hybrid search
    visual_weight: float = 0.5
    text_weight: float = 0.5

    # Filtering
    video_ids: Optional[List[str]] = None  # Filter to specific videos
    time_range: Optional[Tuple[float, float]] = None  # Filter by timestamp

    # Re-ranking
    enable_reranking: bool = False
    rerank_top_k: int = 50  # Retrieve more, then rerank

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Single search result"""
    result_id: str
    video_id: str

    # Type
    result_type: str  # "frame", "transcript", "scene"

    # Content
    timestamp: float
    content: Optional[str] = None  # Transcript text or description
    frame_path: Optional[str] = None

    # Similarity
    similarity_score: float = 0.0
    visual_similarity: float = 0.0
    text_similarity: float = 0.0

    # Context
    scene_id: Optional[int] = None
    context: Dict[str, Any] = field(default_factory=dict)

    # Ranking
    rank: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResults:
    """Collection of search results"""
    query: str
    results: List[SearchResult]
    total_results: int

    # Search info
    search_mode: SearchMode
    config: SearchConfig

    # Performance
    search_time_ms: float = 0.0

    metadata: Dict[str, Any] = field(default_factory=dict)


class SemanticVideoSearch:
    """
    Semantic search across videos using multi-modal retrieval
    Combine visual (CLIP) and text (transcript) search
    """

    def __init__(
        self,
        frame_vector_store=None,
        transcript_vector_store=None,
        scene_vector_store=None,
        clip_embedder=None,
        text_embedder=None,
        default_config: Optional[SearchConfig] = None,
    ):
        """
        Initialize semantic video search

        Args:
            frame_vector_store: FrameVectorStore for visual search
            transcript_vector_store: TranscriptVectorStore for text search
            scene_vector_store: SceneVectorStore for scene-level search
            clip_embedder: CLIP embedder for query encoding
            text_embedder: Text embedder for transcript queries
            default_config: Default search configuration
        """
        self.frame_vector_store = frame_vector_store
        self.transcript_vector_store = transcript_vector_store
        self.scene_vector_store = scene_vector_store

        self.clip_embedder = clip_embedder
        self.text_embedder = text_embedder

        self.default_config = default_config or SearchConfig()

        logger.info("Initialized SemanticVideoSearch")

    def search(
        self,
        query: str,
        config: Optional[SearchConfig] = None,
    ) -> SearchResults:
        """
        Search videos using natural language query

        Args:
            query: Natural language search query
            config: Search configuration

        Returns:
            SearchResults
        """
        import time
        start_time = time.time()

        config = config or self.default_config

        logger.info(f"Searching for: '{query}' (mode={config.mode.value})")

        # Search based on mode
        if config.mode == SearchMode.VISUAL_ONLY:
            results = self._search_visual(query, config)
        elif config.mode == SearchMode.TEXT_ONLY:
            results = self._search_text(query, config)
        elif config.mode == SearchMode.MULTIMODAL:
            results = self._search_multimodal(query, config)
        elif config.mode == SearchMode.HYBRID:
            results = self._search_hybrid(query, config)
        else:
            raise ValueError(f"Unknown search mode: {config.mode}")

        # Apply filters
        results = self._apply_filters(results, config)

        # Sort by similarity
        results = sorted(
            results,
            key=lambda x: x.similarity_score,
            reverse=True,
        )

        # Limit to top_k
        results = results[:config.top_k]

        # Assign ranks
        for i, result in enumerate(results, 1):
            result.rank = i

        # Calculate search time
        search_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Found {len(results)} results in {search_time_ms:.2f}ms "
            f"(mode={config.mode.value})"
        )

        return SearchResults(
            query=query,
            results=results,
            total_results=len(results),
            search_mode=config.mode,
            config=config,
            search_time_ms=search_time_ms,
        )

    def _search_visual(
        self,
        query: str,
        config: SearchConfig,
    ) -> List[SearchResult]:
        """Search frames using visual similarity"""
        if not self.frame_vector_store or not self.clip_embedder:
            logger.warning("Frame search not available (no frame store or embedder)")
            return []

        # Generate query embedding
        query_embedding = self.clip_embedder.encode_text(query)

        # Retrieve from top_k (or rerank_top_k if reranking)
        k = config.rerank_top_k if config.enable_reranking else config.top_k

        # Search frame vectors
        frame_results = self.frame_vector_store.search(
            query_embedding=query_embedding,
            top_k=k,
            min_similarity=config.min_similarity,
            video_ids=config.video_ids,
        )

        # Convert to SearchResult objects
        results = []
        for frame_result in frame_results:
            result = SearchResult(
                result_id=frame_result.get("frame_id", ""),
                video_id=frame_result.get("video_id", ""),
                result_type="frame",
                timestamp=frame_result.get("timestamp", 0.0),
                frame_path=frame_result.get("frame_path"),
                similarity_score=frame_result.get("similarity", 0.0),
                visual_similarity=frame_result.get("similarity", 0.0),
                scene_id=frame_result.get("scene_id"),
                metadata=frame_result.get("metadata", {}),
            )
            results.append(result)

        return results

    def _search_text(
        self,
        query: str,
        config: SearchConfig,
    ) -> List[SearchResult]:
        """Search transcripts using text similarity"""
        if not self.transcript_vector_store or not self.text_embedder:
            logger.warning("Transcript search not available")
            return []

        # Generate query embedding
        query_embedding = self.text_embedder.encode(query)

        # Retrieve
        k = config.rerank_top_k if config.enable_reranking else config.top_k

        # Search transcript vectors
        transcript_results = self.transcript_vector_store.search(
            query_embedding=query_embedding,
            top_k=k,
            min_similarity=config.min_similarity,
            video_ids=config.video_ids,
        )

        # Convert to SearchResult objects
        results = []
        for transcript_result in transcript_results:
            result = SearchResult(
                result_id=transcript_result.get("transcript_id", ""),
                video_id=transcript_result.get("video_id", ""),
                result_type="transcript",
                timestamp=transcript_result.get("timestamp", 0.0),
                content=transcript_result.get("text", ""),
                similarity_score=transcript_result.get("similarity", 0.0),
                text_similarity=transcript_result.get("similarity", 0.0),
                scene_id=transcript_result.get("scene_id"),
                metadata=transcript_result.get("metadata", {}),
            )
            results.append(result)

        return results

    def _search_multimodal(
        self,
        query: str,
        config: SearchConfig,
    ) -> List[SearchResult]:
        """Search both frames and transcripts, return all results"""
        # Search both modalities
        visual_results = self._search_visual(query, config)
        text_results = self._search_text(query, config)

        # Combine results
        all_results = visual_results + text_results

        return all_results

    def _search_hybrid(
        self,
        query: str,
        config: SearchConfig,
    ) -> List[SearchResult]:
        """Search with weighted combination of visual and text"""
        # Search both modalities
        visual_results = self._search_visual(query, config)
        text_results = self._search_text(query, config)

        # Create combined results by video+timestamp
        result_map: Dict[str, SearchResult] = {}

        # Add visual results
        for result in visual_results:
            key = f"{result.video_id}_{result.timestamp:.2f}"
            result_map[key] = result

        # Merge text results
        for result in text_results:
            key = f"{result.video_id}_{result.timestamp:.2f}"

            if key in result_map:
                # Already have visual result, merge
                existing = result_map[key]
                existing.text_similarity = result.text_similarity
                existing.content = result.content

                # Calculate hybrid score
                existing.similarity_score = (
                    existing.visual_similarity * config.visual_weight +
                    existing.text_similarity * config.text_weight
                )
            else:
                # New result from text only
                result_map[key] = result

        # Re-weight visual-only results
        for result in result_map.values():
            if result.text_similarity == 0.0 and result.visual_similarity > 0.0:
                # Visual only - apply weight
                result.similarity_score = result.visual_similarity * config.visual_weight
            elif result.visual_similarity == 0.0 and result.text_similarity > 0.0:
                # Text only - apply weight
                result.similarity_score = result.text_similarity * config.text_weight

        return list(result_map.values())

    def _apply_filters(
        self,
        results: List[SearchResult],
        config: SearchConfig,
    ) -> List[SearchResult]:
        """Apply filters to search results"""
        filtered = results

        # Filter by video IDs
        if config.video_ids:
            filtered = [
                r for r in filtered
                if r.video_id in config.video_ids
            ]

        # Filter by time range
        if config.time_range:
            start_time, end_time = config.time_range
            filtered = [
                r for r in filtered
                if start_time <= r.timestamp <= end_time
            ]

        # Filter by minimum similarity
        if config.min_similarity > 0.0:
            filtered = [
                r for r in filtered
                if r.similarity_score >= config.min_similarity
            ]

        return filtered

    def search_by_video(
        self,
        query: str,
        video_id: str,
        config: Optional[SearchConfig] = None,
    ) -> SearchResults:
        """
        Search within a specific video

        Args:
            query: Search query
            video_id: Video to search in
            config: Search configuration

        Returns:
            SearchResults
        """
        config = config or self.default_config.copy() if hasattr(self.default_config, 'copy') else self.default_config

        # Override video_ids filter
        if not hasattr(config, 'video_ids') or config.video_ids is None:
            # Create new config with video filter
            config = SearchConfig(
                mode=config.mode,
                top_k=config.top_k,
                min_similarity=config.min_similarity,
                visual_weight=config.visual_weight,
                text_weight=config.text_weight,
                video_ids=[video_id],
                time_range=config.time_range,
                enable_reranking=config.enable_reranking,
                rerank_top_k=config.rerank_top_k,
            )
        else:
            config.video_ids = [video_id]

        return self.search(query, config)

    def search_temporal_context(
        self,
        query: str,
        video_id: str,
        timestamp: float,
        context_window: float = 30.0,
        config: Optional[SearchConfig] = None,
    ) -> SearchResults:
        """
        Search within temporal context around a timestamp

        Args:
            query: Search query
            video_id: Video ID
            timestamp: Center timestamp
            context_window: Window size in seconds (±window/2)
            config: Search configuration

        Returns:
            SearchResults
        """
        config = config or self.default_config

        # Set time range filter
        half_window = context_window / 2
        start_time = max(0, timestamp - half_window)
        end_time = timestamp + half_window

        # Create config with filters
        filtered_config = SearchConfig(
            mode=config.mode,
            top_k=config.top_k,
            min_similarity=config.min_similarity,
            visual_weight=config.visual_weight,
            text_weight=config.text_weight,
            video_ids=[video_id],
            time_range=(start_time, end_time),
            enable_reranking=config.enable_reranking,
            rerank_top_k=config.rerank_top_k,
        )

        return self.search(query, filtered_config)

    def get_similar_moments(
        self,
        video_id: str,
        timestamp: float,
        top_k: int = 5,
        same_video_only: bool = False,
    ) -> List[SearchResult]:
        """
        Find similar moments to a given timestamp

        Args:
            video_id: Source video ID
            timestamp: Source timestamp
            top_k: Number of similar moments to return
            same_video_only: Only search within same video

        Returns:
            List of similar moments
        """
        if not self.frame_vector_store:
            logger.warning("Frame vector store not available")
            return []

        # Get frame at timestamp
        frame = self.frame_vector_store.get_frame_at_timestamp(
            video_id=video_id,
            timestamp=timestamp,
        )

        if not frame or "embedding" not in frame:
            logger.warning(f"No frame found at {timestamp}s")
            return []

        # Search using frame embedding
        video_ids_filter = [video_id] if same_video_only else None

        similar_frames = self.frame_vector_store.search(
            query_embedding=frame["embedding"],
            top_k=top_k + 1,  # +1 to exclude source frame
            video_ids=video_ids_filter,
        )

        # Convert to SearchResult and exclude source
        results = []
        for frame_result in similar_frames:
            # Skip source frame
            if (frame_result.get("video_id") == video_id and
                abs(frame_result.get("timestamp", 0) - timestamp) < 1.0):
                continue

            result = SearchResult(
                result_id=frame_result.get("frame_id", ""),
                video_id=frame_result.get("video_id", ""),
                result_type="frame",
                timestamp=frame_result.get("timestamp", 0.0),
                frame_path=frame_result.get("frame_path"),
                similarity_score=frame_result.get("similarity", 0.0),
                visual_similarity=frame_result.get("similarity", 0.0),
                scene_id=frame_result.get("scene_id"),
            )
            results.append(result)

        return results[:top_k]

    def export_results_to_dict(
        self,
        search_results: SearchResults,
    ) -> Dict[str, Any]:
        """Export search results to dictionary"""
        return {
            "query": search_results.query,
            "search_mode": search_results.search_mode.value,
            "total_results": search_results.total_results,
            "search_time_ms": search_results.search_time_ms,
            "results": [
                {
                    "result_id": r.result_id,
                    "video_id": r.video_id,
                    "result_type": r.result_type,
                    "timestamp": r.timestamp,
                    "content": r.content,
                    "frame_path": r.frame_path,
                    "similarity_score": r.similarity_score,
                    "visual_similarity": r.visual_similarity,
                    "text_similarity": r.text_similarity,
                    "scene_id": r.scene_id,
                    "rank": r.rank,
                    "context": r.context,
                    "metadata": r.metadata,
                }
                for r in search_results.results
            ],
            "config": {
                "mode": search_results.config.mode.value,
                "top_k": search_results.config.top_k,
                "min_similarity": search_results.config.min_similarity,
            },
            "metadata": search_results.metadata,
        }


def search_videos(
    query: str,
    frame_vector_store=None,
    transcript_vector_store=None,
    clip_embedder=None,
    text_embedder=None,
    mode: SearchMode = SearchMode.MULTIMODAL,
    top_k: int = 10,
) -> SearchResults:
    """
    Convenience function to search videos

    Args:
        query: Search query
        frame_vector_store: Frame vector store
        transcript_vector_store: Transcript vector store
        clip_embedder: CLIP embedder
        text_embedder: Text embedder
        mode: Search mode
        top_k: Number of results

    Returns:
        SearchResults
    """
    config = SearchConfig(mode=mode, top_k=top_k)

    searcher = SemanticVideoSearch(
        frame_vector_store=frame_vector_store,
        transcript_vector_store=transcript_vector_store,
        clip_embedder=clip_embedder,
        text_embedder=text_embedder,
        default_config=config,
    )

    return searcher.search(query, config)
