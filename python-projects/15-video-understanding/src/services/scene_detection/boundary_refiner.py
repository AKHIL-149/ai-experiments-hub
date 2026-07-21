"""
Scene boundary refinement
Post-processes scene detection results to merge, refine, and clean boundaries
"""

import logging
from typing import List, Set, Tuple, Optional
from collections import defaultdict

from src.services.scene_detection.base import (
    Scene,
    SceneBoundary,
    SceneType,
    TransitionType
)

logger = logging.getLogger(__name__)


class SceneBoundaryRefiner:
    """
    Refine scene boundaries from multiple detectors
    Merges overlapping scenes, removes micro-scenes, and refines boundaries
    """

    def __init__(
        self,
        min_scene_duration: float = 1.0,
        merge_threshold: float = 0.5,
        overlap_threshold: float = 0.8
    ):
        """
        Initialize boundary refiner

        Args:
            min_scene_duration: Minimum scene duration in seconds
            merge_threshold: Time threshold for merging adjacent scenes
            overlap_threshold: Overlap ratio threshold for merging
        """
        self.min_scene_duration = min_scene_duration
        self.merge_threshold = merge_threshold
        self.overlap_threshold = overlap_threshold

    def refine_scenes(self, scenes: List[Scene]) -> List[Scene]:
        """
        Refine scene list

        Args:
            scenes: List of detected scenes

        Returns:
            Refined list of scenes
        """
        if not scenes:
            return []

        logger.info(f"Refining {len(scenes)} scenes")

        # Sort by start time
        scenes = sorted(scenes, key=lambda s: s.start_time)

        # Remove micro-scenes (very short scenes)
        scenes = self._remove_micro_scenes(scenes)

        # Merge adjacent similar scenes
        scenes = self._merge_adjacent_scenes(scenes)

        # Merge overlapping scenes
        scenes = self._merge_overlapping_scenes(scenes)

        # Fill gaps between scenes
        scenes = self._fill_gaps(scenes)

        # Renumber scenes
        for idx, scene in enumerate(scenes, start=1):
            scene.scene_id = idx

        logger.info(f"Refinement complete: {len(scenes)} final scenes")

        return scenes

    def merge_multi_detector_results(
        self,
        scene_lists: List[List[Scene]],
        voting_threshold: int = 2
    ) -> List[Scene]:
        """
        Merge results from multiple scene detectors

        Args:
            scene_lists: List of scene lists from different detectors
            voting_threshold: Minimum number of detectors that must agree

        Returns:
            Merged scene list
        """
        if not scene_lists:
            return []

        logger.info(f"Merging results from {len(scene_lists)} detectors")

        # Collect all boundaries from all detectors
        all_boundaries = []

        for scene_list in scene_lists:
            for scene in scene_list:
                all_boundaries.append({
                    'timestamp': scene.start_time,
                    'type': 'start',
                    'detector': scene.metadata.get('detector', 'unknown') if scene.metadata else 'unknown'
                })
                all_boundaries.append({
                    'timestamp': scene.end_time,
                    'type': 'end',
                    'detector': scene.metadata.get('detector', 'unknown') if scene.metadata else 'unknown'
                })

        # Cluster boundaries by timestamp (within 0.5 seconds)
        boundary_clusters = self._cluster_boundaries(all_boundaries, tolerance=0.5)

        # Filter clusters by voting threshold
        consensus_boundaries = []
        for cluster in boundary_clusters:
            if len(cluster) >= voting_threshold:
                # Use average timestamp
                avg_timestamp = sum(b['timestamp'] for b in cluster) / len(cluster)
                consensus_boundaries.append(avg_timestamp)

        # Sort boundaries
        consensus_boundaries.sort()

        # Create scenes from consensus boundaries
        if not consensus_boundaries:
            logger.warning("No consensus boundaries found")
            return []

        # Get video duration from longest scene list
        max_duration = max(
            max(s.end_time for s in sl) if sl else 0
            for sl in scene_lists
        )

        # Get FPS from first scene
        fps = 25.0  # Default
        for scene_list in scene_lists:
            if scene_list:
                first_scene = scene_list[0]
                if first_scene.frame_count > 0 and first_scene.duration > 0:
                    fps = first_scene.frame_count / first_scene.duration
                    break

        # Build merged scenes
        merged_scenes = []
        for i in range(len(consensus_boundaries) - 1):
            start_time = consensus_boundaries[i]
            end_time = consensus_boundaries[i + 1]
            duration = end_time - start_time

            if duration < self.min_scene_duration:
                continue

            scene = Scene(
                scene_id=len(merged_scenes) + 1,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                start_frame=int(start_time * fps),
                end_frame=int(end_time * fps),
                frame_count=int(duration * fps),
                scene_type=SceneType.UNKNOWN,
                transition_type=TransitionType.CUT,
                confidence=len(boundary_clusters[i]) / len(scene_lists),  # Confidence based on agreement
                metadata={
                    'detector': 'ensemble',
                    'detectors_agreed': len(boundary_clusters[i])
                }
            )
            merged_scenes.append(scene)

        logger.info(f"Merged {len(scene_lists)} detector results into {len(merged_scenes)} scenes")

        return merged_scenes

    def _remove_micro_scenes(self, scenes: List[Scene]) -> List[Scene]:
        """
        Remove very short scenes (micro-scenes)

        Args:
            scenes: List of scenes

        Returns:
            Filtered scenes
        """
        filtered = [
            s for s in scenes
            if s.duration >= self.min_scene_duration
        ]

        removed = len(scenes) - len(filtered)
        if removed > 0:
            logger.debug(f"Removed {removed} micro-scenes (< {self.min_scene_duration}s)")

        return filtered

    def _merge_adjacent_scenes(self, scenes: List[Scene]) -> List[Scene]:
        """
        Merge adjacent scenes that are very close in time

        Args:
            scenes: List of scenes

        Returns:
            Merged scenes
        """
        if len(scenes) <= 1:
            return scenes

        merged = []
        current = scenes[0]

        for next_scene in scenes[1:]:
            gap = next_scene.start_time - current.end_time

            # Merge if gap is very small
            if gap < self.merge_threshold:
                # Merge scenes
                current = Scene(
                    scene_id=current.scene_id,
                    start_time=current.start_time,
                    end_time=next_scene.end_time,
                    duration=next_scene.end_time - current.start_time,
                    start_frame=current.start_frame,
                    end_frame=next_scene.end_frame,
                    frame_count=current.frame_count + next_scene.frame_count,
                    scene_type=current.scene_type,
                    transition_type=current.transition_type,
                    confidence=min(current.confidence, next_scene.confidence),
                    metadata=current.metadata
                )
            else:
                merged.append(current)
                current = next_scene

        merged.append(current)

        if len(merged) < len(scenes):
            logger.debug(f"Merged adjacent scenes: {len(scenes)} -> {len(merged)}")

        return merged

    def _merge_overlapping_scenes(self, scenes: List[Scene]) -> List[Scene]:
        """
        Merge scenes that overlap significantly

        Args:
            scenes: List of scenes

        Returns:
            Merged scenes
        """
        if len(scenes) <= 1:
            return scenes

        merged = []
        current = scenes[0]

        for next_scene in scenes[1:]:
            overlap = self._calculate_overlap(current, next_scene)

            # Merge if overlap is significant
            if overlap > self.overlap_threshold:
                # Merge scenes - extend to cover both
                current = Scene(
                    scene_id=current.scene_id,
                    start_time=min(current.start_time, next_scene.start_time),
                    end_time=max(current.end_time, next_scene.end_time),
                    duration=max(current.end_time, next_scene.end_time) - min(current.start_time, next_scene.start_time),
                    start_frame=min(current.start_frame, next_scene.start_frame),
                    end_frame=max(current.end_frame, next_scene.end_frame),
                    frame_count=max(current.end_frame, next_scene.end_frame) - min(current.start_frame, next_scene.start_frame),
                    scene_type=current.scene_type,
                    transition_type=current.transition_type,
                    confidence=max(current.confidence, next_scene.confidence),
                    metadata=current.metadata
                )
            else:
                merged.append(current)
                current = next_scene

        merged.append(current)

        if len(merged) < len(scenes):
            logger.debug(f"Merged overlapping scenes: {len(scenes)} -> {len(merged)}")

        return merged

    def _fill_gaps(self, scenes: List[Scene]) -> List[Scene]:
        """
        Fill small gaps between scenes by extending scene boundaries

        Args:
            scenes: List of scenes

        Returns:
            Scenes with gaps filled
        """
        if len(scenes) <= 1:
            return scenes

        filled = [scenes[0]]

        for i in range(1, len(scenes)):
            prev_scene = filled[-1]
            curr_scene = scenes[i]

            gap = curr_scene.start_time - prev_scene.end_time

            # If gap is small, extend scenes to meet in the middle
            if 0 < gap < self.merge_threshold:
                middle = prev_scene.end_time + (gap / 2)

                # Extend previous scene
                prev_scene.end_time = middle
                prev_scene.duration = prev_scene.end_time - prev_scene.start_time
                prev_scene.end_frame = int(middle * (prev_scene.frame_count / prev_scene.duration))

                # Extend current scene
                curr_scene.start_time = middle
                curr_scene.duration = curr_scene.end_time - curr_scene.start_time
                curr_scene.start_frame = int(middle * (curr_scene.frame_count / curr_scene.duration))

            filled.append(curr_scene)

        return filled

    def _calculate_overlap(self, scene1: Scene, scene2: Scene) -> float:
        """
        Calculate overlap ratio between two scenes

        Args:
            scene1: First scene
            scene2: Second scene

        Returns:
            Overlap ratio (0-1)
        """
        # Calculate overlap
        overlap_start = max(scene1.start_time, scene2.start_time)
        overlap_end = min(scene1.end_time, scene2.end_time)

        if overlap_end <= overlap_start:
            return 0.0

        overlap_duration = overlap_end - overlap_start

        # Calculate overlap ratio relative to shorter scene
        min_duration = min(scene1.duration, scene2.duration)

        return overlap_duration / min_duration if min_duration > 0 else 0.0

    def _cluster_boundaries(
        self,
        boundaries: List[dict],
        tolerance: float = 0.5
    ) -> List[List[dict]]:
        """
        Cluster boundaries that are close in time

        Args:
            boundaries: List of boundary dicts
            tolerance: Time tolerance for clustering (seconds)

        Returns:
            List of boundary clusters
        """
        if not boundaries:
            return []

        # Sort by timestamp
        boundaries = sorted(boundaries, key=lambda b: b['timestamp'])

        clusters = []
        current_cluster = [boundaries[0]]

        for boundary in boundaries[1:]:
            # Check if close to current cluster
            cluster_avg = sum(b['timestamp'] for b in current_cluster) / len(current_cluster)

            if abs(boundary['timestamp'] - cluster_avg) < tolerance:
                current_cluster.append(boundary)
            else:
                clusters.append(current_cluster)
                current_cluster = [boundary]

        clusters.append(current_cluster)

        return clusters

    def analyze_scene_consistency(self, scenes: List[Scene]) -> dict:
        """
        Analyze consistency of scene boundaries

        Args:
            scenes: List of scenes

        Returns:
            Consistency metrics
        """
        if not scenes:
            return {
                'total_scenes': 0,
                'avg_duration': 0.0,
                'std_duration': 0.0,
                'gaps': [],
                'overlaps': []
            }

        import numpy as np

        durations = [s.duration for s in scenes]

        # Find gaps
        gaps = []
        for i in range(len(scenes) - 1):
            gap = scenes[i + 1].start_time - scenes[i].end_time
            if gap > 0.1:  # More than 0.1 second gap
                gaps.append({
                    'after_scene': scenes[i].scene_id,
                    'gap_duration': gap
                })

        # Find overlaps
        overlaps = []
        for i in range(len(scenes) - 1):
            overlap = scenes[i].end_time - scenes[i + 1].start_time
            if overlap > 0:
                overlaps.append({
                    'scenes': (scenes[i].scene_id, scenes[i + 1].scene_id),
                    'overlap_duration': overlap
                })

        return {
            'total_scenes': len(scenes),
            'avg_duration': float(np.mean(durations)),
            'std_duration': float(np.std(durations)),
            'min_duration': min(durations),
            'max_duration': max(durations),
            'gaps': gaps,
            'overlaps': overlaps,
            'has_issues': len(gaps) > 0 or len(overlaps) > 0
        }


def refine_scene_boundaries(
    scenes: List[Scene],
    min_scene_duration: float = 1.0,
    merge_threshold: float = 0.5
) -> List[Scene]:
    """
    Convenience function for refining scene boundaries

    Args:
        scenes: List of scenes to refine
        min_scene_duration: Minimum scene duration
        merge_threshold: Time threshold for merging

    Returns:
        Refined scenes
    """
    refiner = SceneBoundaryRefiner(
        min_scene_duration=min_scene_duration,
        merge_threshold=merge_threshold
    )
    return refiner.refine_scenes(scenes)
