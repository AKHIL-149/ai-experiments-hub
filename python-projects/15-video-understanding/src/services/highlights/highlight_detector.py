"""
Highlight detector for identifying highlight-worthy moments
Detect highlights using importance threshold and multiple types
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class HighlightType(str, Enum):
    """Types of highlights"""
    ACTION = "action"  # High action/movement
    DIALOGUE = "dialogue"  # Important dialogue
    KEY_MOMENT = "key_moment"  # Key moment in narrative
    TRANSITION = "transition"  # Important scene transition
    EMOTIONAL = "emotional"  # Emotional peak
    VISUAL = "visual"  # Visually striking
    AUTO = "auto"  # Automatically determined


@dataclass
class Highlight:
    """Video highlight"""
    highlight_id: str
    video_id: str

    # Time range
    start_time: float
    end_time: float
    duration: float

    # Classification
    highlight_type: HighlightType
    importance_score: float

    # Content
    title: Optional[str] = None
    description: Optional[str] = None
    thumbnail_path: Optional[str] = None

    # Scenes
    scene_ids: List[int] = field(default_factory=list)
    num_scenes: int = 0

    # Ranking
    rank: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HighlightCollection:
    """Collection of highlights for a video"""
    video_id: str
    highlights: List[Highlight]
    total_duration: float

    # Detection params
    detection_method: str = "importance_threshold"
    min_importance: float = 0.5
    max_highlights: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


class HighlightDetector:
    """
    Detect highlight-worthy moments in videos
    Use importance scores and configurable criteria
    """

    def __init__(
        self,
        importance_scorer=None,
        min_importance: float = 0.7,
        min_highlight_duration: float = 5.0,
        max_highlight_duration: float = 60.0,
        merge_nearby_highlights: bool = True,
        nearby_threshold: float = 10.0,
    ):
        """
        Initialize highlight detector

        Args:
            importance_scorer: ImportanceScorer instance
            min_importance: Minimum importance for highlights
            min_highlight_duration: Minimum highlight duration (seconds)
            max_highlight_duration: Maximum highlight duration (seconds)
            merge_nearby_highlights: Merge highlights that are close together
            nearby_threshold: Threshold for merging (seconds)
        """
        self.importance_scorer = importance_scorer
        self.min_importance = min_importance
        self.min_highlight_duration = min_highlight_duration
        self.max_highlight_duration = max_highlight_duration
        self.merge_nearby_highlights = merge_nearby_highlights
        self.nearby_threshold = nearby_threshold

        logger.info(
            f"Initialized HighlightDetector "
            f"(min_importance={min_importance})"
        )

    def detect_highlights(
        self,
        video_id: str,
        duration: float,
        scenes: Optional[List[Dict[str, Any]]] = None,
        enriched_scenes: Optional[List[Any]] = None,
        scene_scores: Optional[List[Any]] = None,
        max_highlights: Optional[int] = None,
    ) -> HighlightCollection:
        """
        Detect highlights in video

        Args:
            video_id: Video identifier
            duration: Video duration
            scenes: Scene list
            enriched_scenes: Enriched scenes
            scene_scores: Pre-computed scene importance scores
            max_highlights: Maximum number of highlights

        Returns:
            HighlightCollection
        """
        logger.info(f"Detecting highlights for video {video_id}")

        # Get importance scores
        if scene_scores:
            scores = scene_scores
        elif self.importance_scorer and (scenes or enriched_scenes):
            scores = self.importance_scorer.score_scenes_batch(
                scenes_data=scenes or [],
                enriched_scenes=enriched_scenes,
            )
        else:
            logger.warning("No scenes or scores provided, returning empty highlights")
            return HighlightCollection(
                video_id=video_id,
                highlights=[],
                total_duration=duration,
            )

        # Filter by importance threshold
        high_importance_scenes = [
            s for s in scores
            if s.importance_score >= self.min_importance
        ]

        logger.info(
            f"Found {len(high_importance_scenes)} scenes above "
            f"importance threshold {self.min_importance}"
        )

        # Create highlights from high-importance scenes
        highlights = self._create_highlights_from_scenes(
            video_id=video_id,
            importance_scores=high_importance_scenes,
        )

        # Merge nearby highlights if requested
        if self.merge_nearby_highlights:
            highlights = self._merge_nearby_highlights(highlights)

        # Classify highlight types
        highlights = self._classify_highlight_types(highlights, scores)

        # Generate titles and descriptions
        highlights = self._generate_highlight_metadata(highlights)

        # Limit to max highlights if specified
        if max_highlights and len(highlights) > max_highlights:
            # Sort by importance and take top K
            highlights = sorted(
                highlights,
                key=lambda x: x.importance_score,
                reverse=True
            )[:max_highlights]

        # Rank highlights
        highlights = self._rank_highlights(highlights)

        # Sort by start time for final output
        highlights = sorted(highlights, key=lambda x: x.start_time)

        return HighlightCollection(
            video_id=video_id,
            highlights=highlights,
            total_duration=duration,
            detection_method="importance_threshold",
            min_importance=self.min_importance,
            max_highlights=max_highlights,
            metadata={
                "num_highlights": len(highlights),
                "total_highlight_duration": sum(h.duration for h in highlights),
                "avg_importance": sum(h.importance_score for h in highlights) / len(highlights) if highlights else 0,
            },
        )

    def _create_highlights_from_scenes(
        self,
        video_id: str,
        importance_scores: List[Any],
    ) -> List[Highlight]:
        """Create highlights from high-importance scenes"""
        highlights = []

        for score in importance_scores:
            # Check duration constraints
            duration = score.end_time - score.start_time

            if duration < self.min_highlight_duration:
                logger.debug(f"Scene {score.scene_id} too short ({duration:.1f}s), skipping")
                continue

            if duration > self.max_highlight_duration:
                logger.debug(f"Scene {score.scene_id} too long ({duration:.1f}s), truncating")
                # Truncate to max duration
                end_time = score.start_time + self.max_highlight_duration
            else:
                end_time = score.end_time

            # Create highlight
            highlight = Highlight(
                highlight_id=f"{video_id}_highlight_{score.scene_id}",
                video_id=video_id,
                start_time=score.start_time,
                end_time=end_time,
                duration=end_time - score.start_time,
                highlight_type=HighlightType.AUTO,
                importance_score=score.importance_score,
                scene_ids=[score.scene_id],
                num_scenes=1,
            )

            highlights.append(highlight)

        return highlights

    def _merge_nearby_highlights(
        self,
        highlights: List[Highlight],
    ) -> List[Highlight]:
        """Merge highlights that are close together"""
        if not highlights:
            return highlights

        # Sort by start time
        sorted_highlights = sorted(highlights, key=lambda x: x.start_time)

        merged = []
        current = sorted_highlights[0]

        for next_highlight in sorted_highlights[1:]:
            # Check if next highlight is nearby
            time_gap = next_highlight.start_time - current.end_time

            if time_gap <= self.nearby_threshold:
                # Merge highlights
                current = self._merge_two_highlights(current, next_highlight)
            else:
                # Save current and start new
                merged.append(current)
                current = next_highlight

        # Add final highlight
        merged.append(current)

        logger.info(f"Merged {len(highlights)} highlights into {len(merged)}")

        return merged

    def _merge_two_highlights(
        self,
        highlight1: Highlight,
        highlight2: Highlight,
    ) -> Highlight:
        """Merge two highlights into one"""
        # Combine time ranges
        start_time = min(highlight1.start_time, highlight2.start_time)
        end_time = max(highlight1.end_time, highlight2.end_time)
        duration = end_time - start_time

        # Check max duration
        if duration > self.max_highlight_duration:
            # Truncate to max
            end_time = start_time + self.max_highlight_duration
            duration = self.max_highlight_duration

        # Combine scene IDs
        scene_ids = highlight1.scene_ids + highlight2.scene_ids

        # Average importance
        importance = (highlight1.importance_score + highlight2.importance_score) / 2

        return Highlight(
            highlight_id=f"{highlight1.highlight_id}_merged",
            video_id=highlight1.video_id,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            highlight_type=HighlightType.AUTO,
            importance_score=importance,
            scene_ids=scene_ids,
            num_scenes=len(scene_ids),
        )

    def _classify_highlight_types(
        self,
        highlights: List[Highlight],
        all_scores: List[Any],
    ) -> List[Highlight]:
        """Classify highlight types based on content"""
        # Create score lookup
        score_lookup = {s.scene_id: s for s in all_scores}

        for highlight in highlights:
            # Get scores for scenes in highlight
            scene_scores = [
                score_lookup[sid] for sid in highlight.scene_ids
                if sid in score_lookup
            ]

            if not scene_scores:
                continue

            # Analyze factors to determine type
            highlight.highlight_type = self._determine_highlight_type(scene_scores)

        return highlights

    def _determine_highlight_type(
        self,
        scene_scores: List[Any],
    ) -> HighlightType:
        """Determine highlight type from scene factors"""
        if not scene_scores:
            return HighlightType.AUTO

        # Average factors across scenes
        avg_action = np.mean([s.factors.action_count for s in scene_scores])
        avg_speaker = np.mean([s.factors.speaker_count for s in scene_scores])
        avg_visual = np.mean([s.factors.visual_activity for s in scene_scores])
        avg_faces = np.mean([s.factors.face_count for s in scene_scores])

        # Classify based on dominant factor
        if avg_action > 2:
            return HighlightType.ACTION
        elif avg_speaker > 1 or avg_faces > 2:
            return HighlightType.DIALOGUE
        elif avg_visual > 0.7:
            return HighlightType.VISUAL
        else:
            return HighlightType.KEY_MOMENT

    def _generate_highlight_metadata(
        self,
        highlights: List[Highlight],
    ) -> List[Highlight]:
        """Generate titles and descriptions for highlights"""
        for i, highlight in enumerate(highlights, 1):
            # Generate title
            if not highlight.title:
                type_name = highlight.highlight_type.value.replace("_", " ").title()
                highlight.title = f"{type_name} Highlight {i}"

            # Generate description
            if not highlight.description:
                highlight.description = (
                    f"{highlight.highlight_type.value.title()} highlight from "
                    f"{self._format_timestamp(highlight.start_time)} to "
                    f"{self._format_timestamp(highlight.end_time)} "
                    f"(importance: {highlight.importance_score:.2f})"
                )

        return highlights

    def _rank_highlights(
        self,
        highlights: List[Highlight],
    ) -> List[Highlight]:
        """Rank highlights by importance"""
        sorted_highlights = sorted(
            highlights,
            key=lambda x: x.importance_score,
            reverse=True
        )

        for i, highlight in enumerate(sorted_highlights, 1):
            highlight.rank = i

        return highlights

    def _format_timestamp(self, seconds: float) -> str:
        """Format timestamp"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def export_highlights_to_dict(
        self,
        highlights: HighlightCollection,
    ) -> Dict[str, Any]:
        """Export highlights to dictionary"""
        return {
            "video_id": highlights.video_id,
            "total_duration": highlights.total_duration,
            "detection_method": highlights.detection_method,
            "min_importance": highlights.min_importance,
            "highlights": [
                {
                    "highlight_id": h.highlight_id,
                    "start_time": h.start_time,
                    "end_time": h.end_time,
                    "duration": h.duration,
                    "highlight_type": h.highlight_type.value,
                    "importance_score": h.importance_score,
                    "title": h.title,
                    "description": h.description,
                    "scene_ids": h.scene_ids,
                    "num_scenes": h.num_scenes,
                    "rank": h.rank,
                    "metadata": h.metadata,
                }
                for h in highlights.highlights
            ],
            "metadata": highlights.metadata,
        }


def detect_highlights(
    video_id: str,
    duration: float,
    scenes: Optional[List[Dict[str, Any]]] = None,
    enriched_scenes: Optional[List[Any]] = None,
    importance_scorer=None,
    min_importance: float = 0.7,
    max_highlights: Optional[int] = 10,
) -> HighlightCollection:
    """
    Convenience function to detect highlights

    Args:
        video_id: Video identifier
        duration: Video duration
        scenes: Scene list
        enriched_scenes: Enriched scenes
        importance_scorer: ImportanceScorer instance
        min_importance: Minimum importance threshold
        max_highlights: Maximum number of highlights

    Returns:
        HighlightCollection
    """
    detector = HighlightDetector(
        importance_scorer=importance_scorer,
        min_importance=min_importance,
    )

    return detector.detect_highlights(
        video_id=video_id,
        duration=duration,
        scenes=scenes,
        enriched_scenes=enriched_scenes,
        max_highlights=max_highlights,
    )
