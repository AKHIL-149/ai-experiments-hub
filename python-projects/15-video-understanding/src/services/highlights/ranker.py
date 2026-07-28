"""
Highlight ranker for ranking and diversifying highlight selection
Rank by importance and ensure temporal diversity
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RankingConfig:
    """Configuration for highlight ranking"""
    # Importance weighting
    importance_weight: float = 0.7
    diversity_weight: float = 0.3

    # Temporal diversity
    min_time_gap: float = 30.0  # Minimum seconds between highlights
    prefer_spread: bool = True  # Prefer highlights spread across video

    # Type diversity
    prefer_type_diversity: bool = True
    max_same_type: int = 3  # Maximum consecutive highlights of same type

    # Duration preferences
    prefer_longer: bool = False  # Prefer longer highlights
    duration_weight: float = 0.1


class HighlightRanker:
    """
    Rank highlights by importance and diversity
    Ensure temporal and type diversity in selection
    """

    def __init__(
        self,
        config: Optional[RankingConfig] = None,
    ):
        """
        Initialize highlight ranker

        Args:
            config: Ranking configuration
        """
        self.config = config or RankingConfig()

        logger.info("Initialized HighlightRanker")

    def rank_highlights(
        self,
        highlights: List[Any],
        max_highlights: Optional[int] = None,
    ) -> List[Any]:
        """
        Rank highlights by importance and diversity

        Args:
            highlights: List of Highlight objects
            max_highlights: Maximum number of highlights to return

        Returns:
            Ranked list of highlights
        """
        if not highlights:
            return []

        logger.info(f"Ranking {len(highlights)} highlights")

        # Calculate composite scores
        scored_highlights = self._calculate_composite_scores(highlights)

        # Sort by composite score
        ranked = sorted(
            scored_highlights,
            key=lambda x: x["composite_score"],
            reverse=True,
        )

        # Extract highlights
        ranked_highlights = [item["highlight"] for item in ranked]

        # Apply diversity filtering if max_highlights specified
        if max_highlights and len(ranked_highlights) > max_highlights:
            ranked_highlights = self._apply_diversity_selection(
                ranked_highlights,
                max_highlights,
            )

        # Update ranks
        for i, highlight in enumerate(ranked_highlights, 1):
            highlight.rank = i

        logger.info(f"Ranked to {len(ranked_highlights)} highlights")

        return ranked_highlights

    def _calculate_composite_scores(
        self,
        highlights: List[Any],
    ) -> List[Dict[str, Any]]:
        """Calculate composite scores for highlights"""
        scored = []

        # Normalize importance scores
        if highlights:
            importance_scores = [h.importance_score for h in highlights]
            min_importance = min(importance_scores)
            max_importance = max(importance_scores)
            importance_range = max_importance - min_importance

            if importance_range < 1e-6:
                # All same importance
                normalized_importance = [1.0] * len(highlights)
            else:
                normalized_importance = [
                    (score - min_importance) / importance_range
                    for score in importance_scores
                ]
        else:
            normalized_importance = []

        # Calculate composite scores
        for i, highlight in enumerate(highlights):
            # Base importance
            importance = normalized_importance[i]

            # Duration factor (if preferred)
            duration_factor = 0.0
            if self.config.prefer_longer:
                # Normalize duration (assume typical highlight is 10-30s)
                normalized_duration = min(1.0, highlight.duration / 30.0)
                duration_factor = normalized_duration * self.config.duration_weight

            # Composite score
            composite_score = (
                importance * self.config.importance_weight +
                duration_factor
            )

            scored.append({
                "highlight": highlight,
                "composite_score": composite_score,
                "normalized_importance": importance,
            })

        return scored

    def _apply_diversity_selection(
        self,
        highlights: List[Any],
        max_highlights: int,
    ) -> List[Any]:
        """
        Select diverse subset of highlights

        Args:
            highlights: Ranked list of highlights
            max_highlights: Maximum number to select

        Returns:
            Diversified subset
        """
        if len(highlights) <= max_highlights:
            return highlights

        logger.info(
            f"Applying diversity selection: {len(highlights)} -> {max_highlights}"
        )

        # Start with highest-ranked highlight
        selected = [highlights[0]]
        candidates = highlights[1:]

        # Iteratively select most diverse remaining highlight
        while len(selected) < max_highlights and candidates:
            # Score candidates by diversity
            diversity_scores = []

            for candidate in candidates:
                diversity_score = self._calculate_diversity_score(
                    candidate,
                    selected,
                )
                diversity_scores.append({
                    "highlight": candidate,
                    "diversity_score": diversity_score,
                })

            # Select candidate with highest diversity score
            best_candidate = max(
                diversity_scores,
                key=lambda x: x["diversity_score"],
            )

            selected.append(best_candidate["highlight"])
            candidates.remove(best_candidate["highlight"])

        return selected

    def _calculate_diversity_score(
        self,
        candidate: Any,
        selected: List[Any],
    ) -> float:
        """
        Calculate diversity score for candidate relative to selected

        Args:
            candidate: Candidate highlight
            selected: Already selected highlights

        Returns:
            Diversity score (higher = more diverse)
        """
        scores = []

        # Temporal diversity
        temporal_score = self._calculate_temporal_diversity(
            candidate,
            selected,
        )
        scores.append(temporal_score * self.config.diversity_weight)

        # Type diversity
        if self.config.prefer_type_diversity:
            type_score = self._calculate_type_diversity(
                candidate,
                selected,
            )
            scores.append(type_score * 0.3)

        # Importance (still matters)
        importance_score = candidate.importance_score
        scores.append(importance_score * self.config.importance_weight)

        return sum(scores) / len(scores)

    def _calculate_temporal_diversity(
        self,
        candidate: Any,
        selected: List[Any],
    ) -> float:
        """Calculate temporal diversity score"""
        if not selected:
            return 1.0

        # Find minimum time gap to any selected highlight
        min_gap = float('inf')

        for highlight in selected:
            # Gap from candidate start to highlight end
            gap1 = abs(candidate.start_time - highlight.end_time)
            # Gap from candidate end to highlight start
            gap2 = abs(candidate.end_time - highlight.start_time)

            gap = min(gap1, gap2)
            min_gap = min(min_gap, gap)

        # Normalize gap
        if min_gap < self.config.min_time_gap:
            # Penalize highlights too close together
            return min_gap / self.config.min_time_gap
        else:
            return 1.0

    def _calculate_type_diversity(
        self,
        candidate: Any,
        selected: List[Any],
    ) -> float:
        """Calculate type diversity score"""
        if not selected:
            return 1.0

        # Count recent highlights of same type
        same_type_count = 0
        recent_window = min(self.config.max_same_type, len(selected))

        for highlight in selected[-recent_window:]:
            if highlight.highlight_type == candidate.highlight_type:
                same_type_count += 1

        # Penalize if too many of same type
        if same_type_count >= self.config.max_same_type:
            return 0.0
        else:
            return 1.0 - (same_type_count / self.config.max_same_type)

    def ensure_temporal_spread(
        self,
        highlights: List[Any],
        video_duration: float,
    ) -> List[Any]:
        """
        Ensure highlights are spread across video timeline

        Args:
            highlights: List of highlights
            video_duration: Total video duration

        Returns:
            Reordered highlights for better temporal spread
        """
        if not highlights or not self.config.prefer_spread:
            return highlights

        logger.info("Ensuring temporal spread across video")

        # Divide video into segments
        num_segments = min(len(highlights), 10)
        segment_duration = video_duration / num_segments

        # Create segments
        segments = [[] for _ in range(num_segments)]

        # Assign highlights to segments
        for highlight in highlights:
            segment_idx = int(highlight.start_time / segment_duration)
            segment_idx = min(segment_idx, num_segments - 1)
            segments[segment_idx].append(highlight)

        # Select best from each segment
        spread_highlights = []

        for segment in segments:
            if segment:
                # Take highest-ranked from segment
                best = max(segment, key=lambda x: x.importance_score)
                spread_highlights.append(best)

        # Fill remaining slots with next-best highlights
        remaining = [
            h for h in highlights
            if h not in spread_highlights
        ]

        remaining_sorted = sorted(
            remaining,
            key=lambda x: x.importance_score,
            reverse=True,
        )

        # Add remaining to reach target count
        for highlight in remaining_sorted:
            if len(spread_highlights) >= len(highlights):
                break
            spread_highlights.append(highlight)

        # Sort by timestamp for final output
        spread_highlights.sort(key=lambda x: x.start_time)

        return spread_highlights

    def reorder_for_engagement(
        self,
        highlights: List[Any],
    ) -> List[Any]:
        """
        Reorder highlights for maximum engagement

        Strategy: Start strong, end strong, vary middle

        Args:
            highlights: List of highlights

        Returns:
            Reordered highlights
        """
        if len(highlights) <= 2:
            return highlights

        logger.info("Reordering highlights for engagement")

        # Sort by importance
        sorted_highlights = sorted(
            highlights,
            key=lambda x: x.importance_score,
            reverse=True,
        )

        # Engagement order: [best, varied middle, second-best]
        reordered = []

        # Start with best
        reordered.append(sorted_highlights[0])

        # Middle: alternate high and medium importance
        middle_highlights = sorted_highlights[2:-1] if len(sorted_highlights) > 3 else []

        for i, highlight in enumerate(middle_highlights):
            reordered.append(highlight)

        # End with second-best
        if len(sorted_highlights) > 1:
            reordered.append(sorted_highlights[1])

        return reordered

    def filter_overlapping_highlights(
        self,
        highlights: List[Any],
    ) -> List[Any]:
        """
        Remove overlapping highlights, keeping higher-ranked ones

        Args:
            highlights: List of highlights

        Returns:
            Non-overlapping highlights
        """
        if not highlights:
            return []

        logger.info("Filtering overlapping highlights")

        # Sort by importance (keep best)
        sorted_highlights = sorted(
            highlights,
            key=lambda x: x.importance_score,
            reverse=True,
        )

        filtered = []

        for candidate in sorted_highlights:
            # Check if overlaps with any already selected
            overlaps = False

            for selected in filtered:
                if self._highlights_overlap(candidate, selected):
                    overlaps = True
                    break

            if not overlaps:
                filtered.append(candidate)

        # Re-sort by timestamp
        filtered.sort(key=lambda x: x.start_time)

        logger.info(
            f"Filtered {len(highlights)} -> {len(filtered)} "
            f"(removed {len(highlights) - len(filtered)} overlaps)"
        )

        return filtered

    def _highlights_overlap(
        self,
        highlight1: Any,
        highlight2: Any,
    ) -> bool:
        """Check if two highlights overlap in time"""
        # Highlights overlap if one starts before the other ends
        return not (
            highlight1.end_time <= highlight2.start_time or
            highlight2.end_time <= highlight1.start_time
        )

    def get_ranking_stats(
        self,
        highlights: List[Any],
    ) -> Dict[str, Any]:
        """
        Get statistics about highlight ranking

        Args:
            highlights: List of highlights

        Returns:
            Statistics dictionary
        """
        if not highlights:
            return {}

        importance_scores = [h.importance_score for h in highlights]
        durations = [h.duration for h in highlights]

        # Temporal distribution
        if len(highlights) > 1:
            time_gaps = []
            sorted_by_time = sorted(highlights, key=lambda x: x.start_time)

            for i in range(len(sorted_by_time) - 1):
                gap = sorted_by_time[i + 1].start_time - sorted_by_time[i].end_time
                time_gaps.append(gap)

            min_gap = min(time_gaps)
            avg_gap = np.mean(time_gaps)
            max_gap = max(time_gaps)
        else:
            min_gap = avg_gap = max_gap = 0

        # Type distribution
        type_counts = {}
        for highlight in highlights:
            type_name = highlight.highlight_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        return {
            "num_highlights": len(highlights),
            "importance_stats": {
                "mean": np.mean(importance_scores),
                "median": np.median(importance_scores),
                "min": np.min(importance_scores),
                "max": np.max(importance_scores),
                "std": np.std(importance_scores),
            },
            "duration_stats": {
                "mean": np.mean(durations),
                "median": np.median(durations),
                "min": np.min(durations),
                "max": np.max(durations),
                "total": sum(durations),
            },
            "temporal_stats": {
                "min_gap": min_gap,
                "avg_gap": avg_gap,
                "max_gap": max_gap,
            },
            "type_distribution": type_counts,
        }


def rank_highlights(
    highlights: List[Any],
    max_highlights: Optional[int] = None,
    config: Optional[RankingConfig] = None,
) -> List[Any]:
    """
    Convenience function to rank highlights

    Args:
        highlights: List of Highlight objects
        max_highlights: Maximum number of highlights
        config: Ranking configuration

    Returns:
        Ranked highlights
    """
    ranker = HighlightRanker(config=config)

    return ranker.rank_highlights(
        highlights=highlights,
        max_highlights=max_highlights,
    )
