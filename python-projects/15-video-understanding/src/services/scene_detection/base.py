"""
Base class for scene detection
Provides abstract interface for different scene detection methods
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SceneType(str, Enum):
    """Types of scenes"""
    STATIC = "static"  # Minimal motion/changes
    MOTION = "motion"  # Significant motion
    DIALOGUE = "dialogue"  # Conversation/talking
    ACTION = "action"  # High-energy action
    TRANSITION = "transition"  # Transitional scene
    UNKNOWN = "unknown"  # Type not determined


class TransitionType(str, Enum):
    """Types of scene transitions"""
    CUT = "cut"  # Hard cut (instantaneous)
    FADE = "fade"  # Fade transition
    DISSOLVE = "dissolve"  # Dissolve/crossfade
    WIPE = "wipe"  # Wipe transition
    UNKNOWN = "unknown"  # Type not determined


@dataclass
class SceneBoundary:
    """Information about a scene boundary/transition"""
    start_time: float  # Scene start time in seconds
    end_time: float  # Scene end time in seconds
    start_frame: int  # Starting frame number
    end_frame: int  # Ending frame number
    confidence: float  # Detection confidence (0-1)
    transition_type: TransitionType = TransitionType.CUT
    scene_type: Optional[SceneType] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class Scene:
    """Detected scene with boundaries and metadata"""
    scene_id: int
    start_time: float  # Seconds
    end_time: float  # Seconds
    duration: float  # Seconds
    start_frame: int
    end_frame: int
    frame_count: int
    scene_type: SceneType = SceneType.UNKNOWN
    transition_type: TransitionType = TransitionType.CUT
    confidence: float = 1.0
    keyframe_timestamp: Optional[float] = None  # Representative frame
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @property
    def middle_timestamp(self) -> float:
        """Get timestamp of middle of scene"""
        return (self.start_time + self.end_time) / 2


class SceneDetectorConfig:
    """Configuration for scene detection"""

    def __init__(
        self,
        threshold: float = 27.0,
        min_scene_length: float = 1.0,
        max_scene_length: Optional[float] = None,
        detect_transitions: bool = True,
        classify_scenes: bool = False,
        extract_keyframes: bool = True
    ):
        """
        Initialize scene detector configuration

        Args:
            threshold: Detection threshold (meaning varies by detector)
            min_scene_length: Minimum scene length in seconds
            max_scene_length: Maximum scene length in seconds (None = no limit)
            detect_transitions: Detect transition types
            classify_scenes: Classify scene types
            extract_keyframes: Extract representative keyframe for each scene
        """
        self.threshold = threshold
        self.min_scene_length = min_scene_length
        self.max_scene_length = max_scene_length
        self.detect_transitions = detect_transitions
        self.classify_scenes = classify_scenes
        self.extract_keyframes = extract_keyframes


class SceneDetector(ABC):
    """
    Abstract base class for scene detection
    """

    def __init__(self, config: Optional[SceneDetectorConfig] = None):
        """
        Initialize scene detector

        Args:
            config: Detector configuration
        """
        self.config = config or SceneDetectorConfig()
        self.name = self.__class__.__name__

    @abstractmethod
    def detect_scenes(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Scene]:
        """
        Detect scenes in video

        Args:
            video_path: Path to video file
            start_time: Optional start time in seconds
            end_time: Optional end time in seconds

        Returns:
            List of detected Scene objects

        Raises:
            ValueError: If video not found or invalid parameters
            RuntimeError: If detection fails
        """
        pass

    @abstractmethod
    def detect_boundaries(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[SceneBoundary]:
        """
        Detect scene boundaries/transitions

        Args:
            video_path: Path to video file
            start_time: Optional start time in seconds
            end_time: Optional end time in seconds

        Returns:
            List of SceneBoundary objects

        Raises:
            ValueError: If video not found or invalid parameters
            RuntimeError: If detection fails
        """
        pass

    def get_scene_count(self, video_path: Path) -> int:
        """
        Get number of scenes in video

        Args:
            video_path: Path to video file

        Returns:
            Number of scenes detected
        """
        scenes = self.detect_scenes(video_path)
        return len(scenes)

    def get_scene_at_timestamp(
        self,
        scenes: List[Scene],
        timestamp: float
    ) -> Optional[Scene]:
        """
        Find scene at specific timestamp

        Args:
            scenes: List of detected scenes
            timestamp: Timestamp in seconds

        Returns:
            Scene containing timestamp, or None if not found
        """
        for scene in scenes:
            if scene.start_time <= timestamp <= scene.end_time:
                return scene
        return None

    def filter_short_scenes(
        self,
        scenes: List[Scene],
        min_length: Optional[float] = None
    ) -> List[Scene]:
        """
        Filter out scenes shorter than minimum length

        Args:
            scenes: List of scenes
            min_length: Minimum length in seconds (uses config if not specified)

        Returns:
            Filtered list of scenes
        """
        min_length = min_length or self.config.min_scene_length
        filtered = [s for s in scenes if s.duration >= min_length]

        logger.debug(
            f"Filtered {len(scenes) - len(filtered)} short scenes "
            f"(min_length={min_length}s)"
        )

        return filtered

    def merge_adjacent_scenes(
        self,
        scenes: List[Scene],
        similarity_threshold: float = 0.9
    ) -> List[Scene]:
        """
        Merge adjacent scenes that are very similar

        Args:
            scenes: List of scenes
            similarity_threshold: Similarity threshold for merging

        Returns:
            List of scenes with similar adjacent scenes merged
        """
        if len(scenes) <= 1:
            return scenes

        merged = []
        current_scene = scenes[0]

        for next_scene in scenes[1:]:
            # Check if scenes should be merged
            # This is a placeholder - subclasses can implement actual similarity
            should_merge = False

            if should_merge:
                # Merge scenes
                current_scene = Scene(
                    scene_id=current_scene.scene_id,
                    start_time=current_scene.start_time,
                    end_time=next_scene.end_time,
                    duration=next_scene.end_time - current_scene.start_time,
                    start_frame=current_scene.start_frame,
                    end_frame=next_scene.end_frame,
                    frame_count=current_scene.frame_count + next_scene.frame_count,
                    scene_type=current_scene.scene_type,
                    transition_type=current_scene.transition_type,
                    confidence=min(current_scene.confidence, next_scene.confidence)
                )
            else:
                merged.append(current_scene)
                current_scene = next_scene

        # Add last scene
        merged.append(current_scene)

        logger.debug(f"Merged scenes: {len(scenes)} -> {len(merged)}")

        return merged

    def split_long_scenes(
        self,
        scenes: List[Scene],
        max_length: Optional[float] = None
    ) -> List[Scene]:
        """
        Split scenes longer than maximum length

        Args:
            scenes: List of scenes
            max_length: Maximum length in seconds (uses config if not specified)

        Returns:
            List of scenes with long scenes split
        """
        max_length = max_length or self.config.max_scene_length

        if max_length is None:
            return scenes

        split_scenes = []

        for scene in scenes:
            if scene.duration <= max_length:
                split_scenes.append(scene)
            else:
                # Split scene into chunks
                num_splits = int(scene.duration / max_length) + 1
                chunk_duration = scene.duration / num_splits

                for i in range(num_splits):
                    chunk_start = scene.start_time + (i * chunk_duration)
                    chunk_end = min(
                        scene.start_time + ((i + 1) * chunk_duration),
                        scene.end_time
                    )

                    split_scene = Scene(
                        scene_id=len(split_scenes) + 1,
                        start_time=chunk_start,
                        end_time=chunk_end,
                        duration=chunk_end - chunk_start,
                        start_frame=scene.start_frame,  # Approximate
                        end_frame=scene.end_frame,  # Approximate
                        frame_count=int(scene.frame_count / num_splits),
                        scene_type=scene.scene_type,
                        transition_type=TransitionType.CUT,
                        confidence=scene.confidence
                    )

                    split_scenes.append(split_scene)

        logger.debug(
            f"Split long scenes: {len(scenes)} -> {len(split_scenes)} "
            f"(max_length={max_length}s)"
        )

        return split_scenes

    def get_scene_statistics(self, scenes: List[Scene]) -> Dict[str, Any]:
        """
        Get statistics about detected scenes

        Args:
            scenes: List of scenes

        Returns:
            Dictionary with scene statistics
        """
        if not scenes:
            return {
                'total_scenes': 0,
                'total_duration': 0.0,
                'average_duration': 0.0,
                'min_duration': 0.0,
                'max_duration': 0.0,
                'scene_types': {},
                'transition_types': {}
            }

        durations = [s.duration for s in scenes]

        # Count scene types
        scene_type_counts = {}
        for scene in scenes:
            scene_type_counts[scene.scene_type.value] = \
                scene_type_counts.get(scene.scene_type.value, 0) + 1

        # Count transition types
        transition_type_counts = {}
        for scene in scenes:
            transition_type_counts[scene.transition_type.value] = \
                transition_type_counts.get(scene.transition_type.value, 0) + 1

        return {
            'total_scenes': len(scenes),
            'total_duration': sum(durations),
            'average_duration': sum(durations) / len(durations),
            'min_duration': min(durations),
            'max_duration': max(durations),
            'scene_types': scene_type_counts,
            'transition_types': transition_type_counts
        }

    def __repr__(self) -> str:
        return f"{self.name}(threshold={self.config.threshold})"
