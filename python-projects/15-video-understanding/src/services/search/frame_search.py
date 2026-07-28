"""
Frame search engine for visual content retrieval
CLIP-based frame search with timestamp-based results
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FrameSearchConfig:
    """Configuration for frame search"""
    # Retrieval settings
    top_k: int = 10
    min_similarity: float = 0.0

    # Filtering
    video_ids: Optional[List[str]] = None
    scene_ids: Optional[List[int]] = None
    time_range: Optional[Tuple[float, float]] = None

    # Temporal grouping
    group_nearby_frames: bool = True
    temporal_threshold: float = 2.0  # Group frames within N seconds

    # Diversity
    enforce_diversity: bool = False
    min_temporal_gap: float = 5.0  # Minimum gap between results

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FrameMatch:
    """Single frame match result"""
    frame_id: str
    video_id: str
    frame_path: str

    # Temporal info
    timestamp: float
    frame_number: int

    # Scene info
    scene_id: Optional[int] = None
    scene_type: Optional[str] = None

    # Similarity
    similarity_score: float = 0.0

    # Visual features
    description: Optional[str] = None
    detected_objects: List[str] = field(default_factory=list)
    detected_actions: List[str] = field(default_factory=list)

    # Ranking
    rank: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FrameSearchResults:
    """Collection of frame search results"""
    query: str
    matches: List[FrameMatch]
    total_matches: int

    # Search info
    config: FrameSearchConfig
    search_time_ms: float = 0.0

    # Grouping info
    num_groups: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


class FrameSearchEngine:
    """
    Search engine for visual content in video frames
    Use CLIP embeddings for semantic visual search
    """

    def __init__(
        self,
        frame_vector_store=None,
        clip_embedder=None,
        default_config: Optional[FrameSearchConfig] = None,
    ):
        """
        Initialize frame search engine

        Args:
            frame_vector_store: FrameVectorStore for frame retrieval
            clip_embedder: CLIP embedder for query encoding
            default_config: Default search configuration
        """
        self.frame_vector_store = frame_vector_store
        self.clip_embedder = clip_embedder
        self.default_config = default_config or FrameSearchConfig()

        logger.info("Initialized FrameSearchEngine")

    def search(
        self,
        query: str,
        config: Optional[FrameSearchConfig] = None,
    ) -> FrameSearchResults:
        """
        Search frames by visual content

        Args:
            query: Natural language description of visual content
            config: Search configuration

        Returns:
            FrameSearchResults
        """
        import time
        start_time = time.time()

        config = config or self.default_config

        logger.info(f"Searching frames for: '{query}'")

        if not self.frame_vector_store or not self.clip_embedder:
            logger.error("Frame search not available (missing store or embedder)")
            return FrameSearchResults(
                query=query,
                matches=[],
                total_matches=0,
                config=config,
            )

        # Encode query
        query_embedding = self.clip_embedder.encode_text(query)

        # Search vector store
        raw_results = self.frame_vector_store.search(
            query_embedding=query_embedding,
            top_k=config.top_k * 2 if config.enforce_diversity else config.top_k,
            min_similarity=config.min_similarity,
            video_ids=config.video_ids,
        )

        # Convert to FrameMatch objects
        matches = self._convert_to_matches(raw_results)

        # Apply filters
        matches = self._apply_filters(matches, config)

        # Group nearby frames if requested
        if config.group_nearby_frames:
            matches = self._group_nearby_frames(matches, config.temporal_threshold)

        # Enforce diversity if requested
        if config.enforce_diversity:
            matches = self._enforce_diversity(matches, config.min_temporal_gap)

        # Limit to top_k
        matches = matches[:config.top_k]

        # Assign ranks
        for i, match in enumerate(matches, 1):
            match.rank = i

        # Calculate search time
        search_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Found {len(matches)} frame matches in {search_time_ms:.2f}ms"
        )

        return FrameSearchResults(
            query=query,
            matches=matches,
            total_matches=len(matches),
            config=config,
            search_time_ms=search_time_ms,
        )

    def search_by_example_frame(
        self,
        video_id: str,
        timestamp: float,
        config: Optional[FrameSearchConfig] = None,
        exclude_source: bool = True,
    ) -> FrameSearchResults:
        """
        Search for frames similar to an example frame

        Args:
            video_id: Source video ID
            timestamp: Source timestamp
            config: Search configuration
            exclude_source: Exclude source frame from results

        Returns:
            FrameSearchResults
        """
        import time
        start_time = time.time()

        config = config or self.default_config

        logger.info(
            f"Searching for frames similar to {video_id} at {timestamp}s"
        )

        if not self.frame_vector_store:
            logger.error("Frame vector store not available")
            return FrameSearchResults(
                query=f"Similar to {video_id}@{timestamp}s",
                matches=[],
                total_matches=0,
                config=config,
            )

        # Get source frame
        source_frame = self.frame_vector_store.get_frame_at_timestamp(
            video_id=video_id,
            timestamp=timestamp,
        )

        if not source_frame or "embedding" not in source_frame:
            logger.warning(f"No frame found at {timestamp}s in {video_id}")
            return FrameSearchResults(
                query=f"Similar to {video_id}@{timestamp}s",
                matches=[],
                total_matches=0,
                config=config,
            )

        # Search using frame embedding
        raw_results = self.frame_vector_store.search(
            query_embedding=source_frame["embedding"],
            top_k=config.top_k + (1 if exclude_source else 0),
            min_similarity=config.min_similarity,
            video_ids=config.video_ids,
        )

        # Convert to matches
        matches = self._convert_to_matches(raw_results)

        # Exclude source frame if requested
        if exclude_source:
            matches = [
                m for m in matches
                if not (m.video_id == video_id and abs(m.timestamp - timestamp) < 0.5)
            ]

        # Apply filters and processing
        matches = self._apply_filters(matches, config)

        if config.group_nearby_frames:
            matches = self._group_nearby_frames(matches, config.temporal_threshold)

        if config.enforce_diversity:
            matches = self._enforce_diversity(matches, config.min_temporal_gap)

        matches = matches[:config.top_k]

        for i, match in enumerate(matches, 1):
            match.rank = i

        search_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Found {len(matches)} similar frames in {search_time_ms:.2f}ms"
        )

        return FrameSearchResults(
            query=f"Similar to {video_id}@{timestamp}s",
            matches=matches,
            total_matches=len(matches),
            config=config,
            search_time_ms=search_time_ms,
        )

    def search_by_image(
        self,
        image_path: str,
        config: Optional[FrameSearchConfig] = None,
    ) -> FrameSearchResults:
        """
        Search for frames similar to an input image

        Args:
            image_path: Path to query image
            config: Search configuration

        Returns:
            FrameSearchResults
        """
        import time
        start_time = time.time()

        config = config or self.default_config

        logger.info(f"Searching for frames similar to image: {image_path}")

        if not self.clip_embedder:
            logger.error("CLIP embedder not available")
            return FrameSearchResults(
                query=f"Similar to {image_path}",
                matches=[],
                total_matches=0,
                config=config,
            )

        # Encode image
        query_embedding = self.clip_embedder.encode_image(image_path)

        # Search
        raw_results = self.frame_vector_store.search(
            query_embedding=query_embedding,
            top_k=config.top_k * 2 if config.enforce_diversity else config.top_k,
            min_similarity=config.min_similarity,
            video_ids=config.video_ids,
        )

        # Process results
        matches = self._convert_to_matches(raw_results)
        matches = self._apply_filters(matches, config)

        if config.group_nearby_frames:
            matches = self._group_nearby_frames(matches, config.temporal_threshold)

        if config.enforce_diversity:
            matches = self._enforce_diversity(matches, config.min_temporal_gap)

        matches = matches[:config.top_k]

        for i, match in enumerate(matches, 1):
            match.rank = i

        search_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Found {len(matches)} matches for image in {search_time_ms:.2f}ms"
        )

        return FrameSearchResults(
            query=f"Similar to {image_path}",
            matches=matches,
            total_matches=len(matches),
            config=config,
            search_time_ms=search_time_ms,
        )

    def search_by_objects(
        self,
        objects: List[str],
        config: Optional[FrameSearchConfig] = None,
    ) -> FrameSearchResults:
        """
        Search for frames containing specific objects

        Args:
            objects: List of object names to search for
            config: Search configuration

        Returns:
            FrameSearchResults
        """
        # Create query from objects
        query = "a scene with " + ", ".join(objects)

        return self.search(query, config)

    def search_by_scene_type(
        self,
        scene_type: str,
        config: Optional[FrameSearchConfig] = None,
    ) -> FrameSearchResults:
        """
        Search for frames of a specific scene type

        Args:
            scene_type: Type of scene (e.g., "indoor", "outdoor", "landscape")
            config: Search configuration

        Returns:
            FrameSearchResults
        """
        query = f"a {scene_type} scene"

        return self.search(query, config)

    def _convert_to_matches(
        self,
        raw_results: List[Dict[str, Any]],
    ) -> List[FrameMatch]:
        """Convert raw results to FrameMatch objects"""
        matches = []

        for result in raw_results:
            match = FrameMatch(
                frame_id=result.get("frame_id", ""),
                video_id=result.get("video_id", ""),
                frame_path=result.get("frame_path", ""),
                timestamp=result.get("timestamp", 0.0),
                frame_number=result.get("frame_number", 0),
                scene_id=result.get("scene_id"),
                scene_type=result.get("scene_type"),
                similarity_score=result.get("similarity", 0.0),
                description=result.get("description"),
                detected_objects=result.get("detected_objects", []),
                detected_actions=result.get("detected_actions", []),
                metadata=result.get("metadata", {}),
            )
            matches.append(match)

        return matches

    def _apply_filters(
        self,
        matches: List[FrameMatch],
        config: FrameSearchConfig,
    ) -> List[FrameMatch]:
        """Apply filters to matches"""
        filtered = matches

        # Filter by video IDs
        if config.video_ids:
            filtered = [
                m for m in filtered
                if m.video_id in config.video_ids
            ]

        # Filter by scene IDs
        if config.scene_ids:
            filtered = [
                m for m in filtered
                if m.scene_id in config.scene_ids
            ]

        # Filter by time range
        if config.time_range:
            start_time, end_time = config.time_range
            filtered = [
                m for m in filtered
                if start_time <= m.timestamp <= end_time
            ]

        # Filter by minimum similarity
        if config.min_similarity > 0.0:
            filtered = [
                m for m in filtered
                if m.similarity_score >= config.min_similarity
            ]

        return filtered

    def _group_nearby_frames(
        self,
        matches: List[FrameMatch],
        threshold: float,
    ) -> List[FrameMatch]:
        """Group nearby frames and keep best match per group"""
        if not matches:
            return matches

        # Sort by video_id and timestamp
        sorted_matches = sorted(
            matches,
            key=lambda m: (m.video_id, m.timestamp),
        )

        grouped = []
        current_group = [sorted_matches[0]]

        for match in sorted_matches[1:]:
            prev_match = current_group[-1]

            # Check if same video and nearby in time
            if (match.video_id == prev_match.video_id and
                match.timestamp - prev_match.timestamp <= threshold):
                # Add to current group
                current_group.append(match)
            else:
                # Save best from current group
                best_match = max(current_group, key=lambda m: m.similarity_score)
                grouped.append(best_match)

                # Start new group
                current_group = [match]

        # Add final group
        if current_group:
            best_match = max(current_group, key=lambda m: m.similarity_score)
            grouped.append(best_match)

        # Sort by similarity
        grouped = sorted(
            grouped,
            key=lambda m: m.similarity_score,
            reverse=True,
        )

        logger.info(
            f"Grouped {len(matches)} frames into {len(grouped)} groups "
            f"(threshold={threshold}s)"
        )

        return grouped

    def _enforce_diversity(
        self,
        matches: List[FrameMatch],
        min_gap: float,
    ) -> List[FrameMatch]:
        """Enforce minimum temporal gap between matches"""
        if not matches:
            return matches

        diverse = [matches[0]]

        for match in matches[1:]:
            # Check temporal gap to all selected matches
            too_close = False

            for selected in diverse:
                if match.video_id == selected.video_id:
                    gap = abs(match.timestamp - selected.timestamp)
                    if gap < min_gap:
                        too_close = True
                        break

            if not too_close:
                diverse.append(match)

        logger.info(
            f"Enforced diversity: {len(matches)} -> {len(diverse)} frames "
            f"(min_gap={min_gap}s)"
        )

        return diverse

    def get_frame_context(
        self,
        frame_match: FrameMatch,
        context_window: float = 5.0,
    ) -> List[FrameMatch]:
        """
        Get temporal context around a frame match

        Args:
            frame_match: Frame match to get context for
            context_window: Window size in seconds (±window/2)

        Returns:
            List of frames in context
        """
        if not self.frame_vector_store:
            return [frame_match]

        half_window = context_window / 2
        start_time = max(0, frame_match.timestamp - half_window)
        end_time = frame_match.timestamp + half_window

        # Get frames in window
        context_frames = self.frame_vector_store.get_frames_in_range(
            video_id=frame_match.video_id,
            start_time=start_time,
            end_time=end_time,
        )

        # Convert to matches
        matches = self._convert_to_matches(context_frames)

        # Sort by timestamp
        matches = sorted(matches, key=lambda m: m.timestamp)

        return matches

    def export_to_dict(
        self,
        results: FrameSearchResults,
    ) -> Dict[str, Any]:
        """Export results to dictionary"""
        return {
            "query": results.query,
            "total_matches": results.total_matches,
            "search_time_ms": results.search_time_ms,
            "num_groups": results.num_groups,
            "matches": [
                {
                    "frame_id": m.frame_id,
                    "video_id": m.video_id,
                    "frame_path": m.frame_path,
                    "timestamp": m.timestamp,
                    "frame_number": m.frame_number,
                    "scene_id": m.scene_id,
                    "scene_type": m.scene_type,
                    "similarity_score": m.similarity_score,
                    "description": m.description,
                    "detected_objects": m.detected_objects,
                    "detected_actions": m.detected_actions,
                    "rank": m.rank,
                    "metadata": m.metadata,
                }
                for m in results.matches
            ],
            "config": {
                "top_k": results.config.top_k,
                "min_similarity": results.config.min_similarity,
                "group_nearby_frames": results.config.group_nearby_frames,
                "enforce_diversity": results.config.enforce_diversity,
            },
            "metadata": results.metadata,
        }


def search_frames(
    query: str,
    frame_vector_store=None,
    clip_embedder=None,
    top_k: int = 10,
    min_similarity: float = 0.0,
) -> FrameSearchResults:
    """
    Convenience function to search frames

    Args:
        query: Visual search query
        frame_vector_store: Frame vector store
        clip_embedder: CLIP embedder
        top_k: Number of results
        min_similarity: Minimum similarity threshold

    Returns:
        FrameSearchResults
    """
    config = FrameSearchConfig(
        top_k=top_k,
        min_similarity=min_similarity,
    )

    engine = FrameSearchEngine(
        frame_vector_store=frame_vector_store,
        clip_embedder=clip_embedder,
        default_config=config,
    )

    return engine.search(query, config)
