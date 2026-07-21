"""
Content-based scene detection using PySceneDetect
Detects scene changes based on content differences (histogram analysis)
"""

import logging
from pathlib import Path
from typing import List, Optional

from src.services.scene_detection.base import (
    SceneDetector,
    Scene,
    SceneBoundary,
    SceneType,
    TransitionType,
    SceneDetectorConfig
)

logger = logging.getLogger(__name__)


class ContentBasedSceneDetector(SceneDetector):
    """
    Detect scenes based on content changes using PySceneDetect
    Uses histogram differences to identify scene boundaries
    """

    def __init__(
        self,
        config: Optional[SceneDetectorConfig] = None,
        adaptive_threshold: bool = False
    ):
        """
        Initialize content-based scene detector

        Args:
            config: Detector configuration
            adaptive_threshold: Use adaptive threshold based on video content
        """
        super().__init__(config)
        self.adaptive_threshold = adaptive_threshold

    def detect_scenes(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Scene]:
        """
        Detect scenes using content analysis

        Args:
            video_path: Path to video file
            start_time: Optional start time in seconds
            end_time: Optional end time in seconds

        Returns:
            List of detected scenes

        Raises:
            ValueError: If video not found
            RuntimeError: If detection fails
        """
        if not video_path.exists():
            raise ValueError(f"Video not found: {video_path}")

        logger.info(
            f"Detecting scenes in {video_path} using content-based method "
            f"(threshold={self.config.threshold})"
        )

        try:
            from scenedetect import VideoManager, SceneManager
            from scenedetect.detectors import ContentDetector

            # Create video manager
            video_manager = VideoManager([str(video_path)])

            # Create scene manager
            scene_manager = SceneManager()

            # Add content detector
            scene_manager.add_detector(
                ContentDetector(
                    threshold=self.config.threshold,
                    min_scene_len=int(self.config.min_scene_length * 25)  # Frames at ~25fps
                )
            )

            # Set start/end times if specified
            start_frame = None
            end_frame = None

            if start_time is not None or end_time is not None:
                video_manager.set_duration(start_time=start_time, end_time=end_time)

            # Start video manager
            video_manager.start()

            # Perform scene detection
            scene_manager.detect_scenes(video_manager)

            # Get scene list
            scene_list = scene_manager.get_scene_list()

            # Get FPS for time calculations
            fps = video_manager.get_framerate()

            logger.info(f"Detected {len(scene_list)} scenes (FPS={fps})")

            # Convert to Scene objects
            scenes = []
            for idx, (start_frame_obj, end_frame_obj) in enumerate(scene_list, start=1):
                start_frame_num = start_frame_obj.get_frames()
                end_frame_num = end_frame_obj.get_frames()

                start_seconds = start_frame_obj.get_seconds()
                end_seconds = end_frame_obj.get_seconds()
                duration = end_seconds - start_seconds

                scene = Scene(
                    scene_id=idx,
                    start_time=start_seconds,
                    end_time=end_seconds,
                    duration=duration,
                    start_frame=start_frame_num,
                    end_frame=end_frame_num,
                    frame_count=end_frame_num - start_frame_num,
                    scene_type=SceneType.UNKNOWN,
                    transition_type=TransitionType.CUT,
                    confidence=1.0,
                    keyframe_timestamp=start_seconds + (duration / 2),
                    metadata={
                        'detector': 'content',
                        'threshold': self.config.threshold,
                        'fps': fps
                    }
                )

                scenes.append(scene)

            # Release video manager
            video_manager.release()

            # Apply post-processing
            scenes = self._post_process_scenes(scenes)

            logger.info(
                f"Scene detection complete: {len(scenes)} final scenes "
                f"(average duration: {sum(s.duration for s in scenes) / len(scenes):.2f}s)"
            )

            return scenes

        except ImportError:
            raise RuntimeError(
                "PySceneDetect not installed. "
                "Install with: pip install scenedetect[opencv]"
            )
        except Exception as e:
            raise RuntimeError(f"Scene detection failed: {e}") from e

    def detect_boundaries(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[SceneBoundary]:
        """
        Detect scene boundaries

        Args:
            video_path: Path to video file
            start_time: Optional start time
            end_time: Optional end time

        Returns:
            List of scene boundaries
        """
        # Detect scenes first
        scenes = self.detect_scenes(video_path, start_time, end_time)

        # Convert scenes to boundaries
        boundaries = []

        for scene in scenes:
            boundary = SceneBoundary(
                start_time=scene.start_time,
                end_time=scene.end_time,
                start_frame=scene.start_frame,
                end_frame=scene.end_frame,
                confidence=scene.confidence,
                transition_type=scene.transition_type,
                scene_type=scene.scene_type,
                metadata=scene.metadata
            )
            boundaries.append(boundary)

        return boundaries

    def _post_process_scenes(self, scenes: List[Scene]) -> List[Scene]:
        """
        Post-process detected scenes

        Args:
            scenes: Raw detected scenes

        Returns:
            Processed scenes
        """
        # Filter short scenes
        if self.config.min_scene_length > 0:
            scenes = self.filter_short_scenes(scenes)

        # Split long scenes if configured
        if self.config.max_scene_length:
            scenes = self.split_long_scenes(scenes)

        # Renumber scenes after filtering
        for idx, scene in enumerate(scenes, start=1):
            scene.scene_id = idx

        return scenes

    def detect_with_adaptive_threshold(
        self,
        video_path: Path
    ) -> List[Scene]:
        """
        Detect scenes with adaptive threshold

        Analyzes video content to determine optimal threshold

        Args:
            video_path: Path to video file

        Returns:
            List of detected scenes
        """
        logger.info("Using adaptive threshold mode")

        # Try multiple thresholds and pick best result
        thresholds = [15.0, 20.0, 27.0, 35.0, 40.0]
        best_scenes = []
        best_score = float('inf')

        original_threshold = self.config.threshold

        for threshold in thresholds:
            self.config.threshold = threshold

            try:
                scenes = self.detect_scenes(video_path)

                # Score based on scene count and average duration
                # Prefer moderate number of scenes with reasonable durations
                if len(scenes) == 0:
                    score = float('inf')
                else:
                    avg_duration = sum(s.duration for s in scenes) / len(scenes)

                    # Ideal: 10-50 scenes, 3-15 second average duration
                    scene_count_penalty = abs(30 - len(scenes)) / 30
                    duration_penalty = abs(8 - avg_duration) / 8

                    score = scene_count_penalty + duration_penalty

                logger.debug(
                    f"Threshold {threshold}: {len(scenes)} scenes, "
                    f"avg {avg_duration:.2f}s, score {score:.3f}"
                )

                if score < best_score:
                    best_score = score
                    best_scenes = scenes

            except Exception as e:
                logger.warning(f"Threshold {threshold} failed: {e}")
                continue

        # Restore original threshold
        self.config.threshold = original_threshold

        logger.info(
            f"Adaptive threshold selected: {len(best_scenes)} scenes "
            f"(score: {best_score:.3f})"
        )

        return best_scenes


def detect_scenes_content(
    video_path: Path,
    threshold: float = 27.0,
    min_scene_length: float = 1.0,
    adaptive: bool = False
) -> List[Scene]:
    """
    Convenience function for content-based scene detection

    Args:
        video_path: Path to video file
        threshold: Detection threshold
        min_scene_length: Minimum scene length in seconds
        adaptive: Use adaptive threshold

    Returns:
        List of detected scenes
    """
    config = SceneDetectorConfig(
        threshold=threshold,
        min_scene_length=min_scene_length
    )

    detector = ContentBasedSceneDetector(
        config=config,
        adaptive_threshold=adaptive
    )

    if adaptive:
        return detector.detect_with_adaptive_threshold(video_path)
    else:
        return detector.detect_scenes(video_path)
