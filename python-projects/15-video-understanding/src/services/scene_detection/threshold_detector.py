"""
Threshold-based scene detection
Fast detection using simple threshold on frame differences
"""

import logging
from pathlib import Path
from typing import List, Optional
import cv2
import numpy as np

from src.services.scene_detection.base import (
    SceneDetector,
    Scene,
    SceneBoundary,
    SceneType,
    TransitionType,
    SceneDetectorConfig
)

logger = logging.getLogger(__name__)


class ThresholdSceneDetector(SceneDetector):
    """
    Fast scene detection using threshold on frame differences
    Compares consecutive frames and detects changes above threshold
    """

    def __init__(
        self,
        config: Optional[SceneDetectorConfig] = None,
        method: str = "histogram"
    ):
        """
        Initialize threshold-based scene detector

        Args:
            config: Detector configuration
            method: Comparison method (histogram, mse, ssim)
        """
        super().__init__(config)
        self.method = method

    def detect_scenes(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Scene]:
        """
        Detect scenes using threshold-based method

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
            f"Detecting scenes in {video_path} using threshold method "
            f"(threshold={self.config.threshold}, method={self.method})"
        )

        try:
            # Open video
            cap = cv2.VideoCapture(str(video_path))

            if not cap.isOpened():
                raise RuntimeError(f"Failed to open video: {video_path}")

            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0

            logger.debug(f"Video: {frame_count} frames, {fps} fps, {duration:.2f}s")

            # Calculate frame range
            start_frame = int(start_time * fps) if start_time else 0
            end_frame = int(end_time * fps) if end_time else frame_count

            # Set start position
            if start_frame > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

            # Detect scene boundaries
            scene_boundaries = []
            prev_frame = None
            current_frame_num = start_frame

            while current_frame_num < end_frame:
                ret, frame = cap.read()

                if not ret:
                    break

                if prev_frame is not None:
                    # Calculate difference
                    diff = self._calculate_difference(prev_frame, frame)

                    # Check if exceeds threshold
                    if diff > self.config.threshold:
                        timestamp = current_frame_num / fps
                        scene_boundaries.append({
                            'frame': current_frame_num,
                            'timestamp': timestamp,
                            'diff': diff
                        })

                        logger.debug(
                            f"Scene change at frame {current_frame_num} "
                            f"({timestamp:.2f}s), diff={diff:.2f}"
                        )

                prev_frame = frame
                current_frame_num += 1

            cap.release()

            logger.info(f"Found {len(scene_boundaries)} scene boundaries")

            # Convert boundaries to scenes
            scenes = self._boundaries_to_scenes(
                scene_boundaries,
                fps,
                start_frame,
                end_frame,
                duration
            )

            # Post-process
            scenes = self._post_process_scenes(scenes)

            logger.info(
                f"Scene detection complete: {len(scenes)} final scenes "
                f"(average duration: {sum(s.duration for s in scenes) / max(len(scenes), 1):.2f}s)"
            )

            return scenes

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
        scenes = self.detect_scenes(video_path, start_time, end_time)

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

    def _calculate_difference(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray
    ) -> float:
        """
        Calculate difference between two frames

        Args:
            frame1: First frame
            frame2: Second frame

        Returns:
            Difference score
        """
        if self.method == "histogram":
            return self._histogram_difference(frame1, frame2)
        elif self.method == "mse":
            return self._mse_difference(frame1, frame2)
        elif self.method == "ssim":
            return self._ssim_difference(frame1, frame2)
        else:
            raise ValueError(f"Unknown method: {self.method}")

    def _histogram_difference(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray
    ) -> float:
        """
        Calculate histogram difference

        Args:
            frame1: First frame
            frame2: Second frame

        Returns:
            Histogram difference score
        """
        # Convert to grayscale
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        # Calculate histograms
        hist1 = cv2.calcHist([gray1], [0], None, [256], [0, 256])
        hist2 = cv2.calcHist([gray2], [0], None, [256], [0, 256])

        # Normalize
        hist1 = cv2.normalize(hist1, hist1).flatten()
        hist2 = cv2.normalize(hist2, hist2).flatten()

        # Calculate correlation
        correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)

        # Convert to difference score (0-100)
        diff = (1 - correlation) * 100

        return diff

    def _mse_difference(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray
    ) -> float:
        """
        Calculate Mean Squared Error

        Args:
            frame1: First frame
            frame2: Second frame

        Returns:
            MSE score
        """
        # Convert to float
        f1 = frame1.astype(np.float32)
        f2 = frame2.astype(np.float32)

        # Calculate MSE
        mse = np.mean((f1 - f2) ** 2)

        # Normalize to 0-100 range (approximate)
        diff = min(mse / 100, 100)

        return diff

    def _ssim_difference(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray
    ) -> float:
        """
        Calculate Structural Similarity Index

        Args:
            frame1: First frame
            frame2: Second frame

        Returns:
            SSIM-based difference score
        """
        from skimage.metrics import structural_similarity as ssim

        # Convert to grayscale
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        # Calculate SSIM
        ssim_score = ssim(gray1, gray2)

        # Convert to difference (0-100)
        diff = (1 - ssim_score) * 100

        return diff

    def _boundaries_to_scenes(
        self,
        boundaries: List[dict],
        fps: float,
        start_frame: int,
        end_frame: int,
        duration: float
    ) -> List[Scene]:
        """
        Convert boundaries to Scene objects

        Args:
            boundaries: List of boundary dicts
            fps: Video FPS
            start_frame: Start frame number
            end_frame: End frame number
            duration: Total video duration

        Returns:
            List of Scene objects
        """
        scenes = []

        # Add first scene (from start to first boundary)
        if boundaries:
            first_boundary_frame = boundaries[0]['frame']
            first_boundary_time = boundaries[0]['timestamp']

            if first_boundary_frame > start_frame:
                scene = Scene(
                    scene_id=1,
                    start_time=start_frame / fps,
                    end_time=first_boundary_time,
                    duration=first_boundary_time - (start_frame / fps),
                    start_frame=start_frame,
                    end_frame=first_boundary_frame,
                    frame_count=first_boundary_frame - start_frame,
                    scene_type=SceneType.UNKNOWN,
                    transition_type=TransitionType.CUT,
                    confidence=1.0,
                    metadata={'detector': 'threshold', 'method': self.method}
                )
                scenes.append(scene)

        # Add middle scenes (between boundaries)
        for i in range(len(boundaries) - 1):
            start_boundary = boundaries[i]
            end_boundary = boundaries[i + 1]

            start_time = start_boundary['timestamp']
            end_time = end_boundary['timestamp']
            start_frame_num = start_boundary['frame']
            end_frame_num = end_boundary['frame']

            scene = Scene(
                scene_id=len(scenes) + 1,
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                start_frame=start_frame_num,
                end_frame=end_frame_num,
                frame_count=end_frame_num - start_frame_num,
                scene_type=SceneType.UNKNOWN,
                transition_type=TransitionType.CUT,
                confidence=1.0,
                metadata={'detector': 'threshold', 'method': self.method}
            )
            scenes.append(scene)

        # Add last scene (from last boundary to end)
        if boundaries:
            last_boundary = boundaries[-1]
            last_boundary_time = last_boundary['timestamp']
            last_boundary_frame = last_boundary['frame']

            if last_boundary_frame < end_frame:
                scene = Scene(
                    scene_id=len(scenes) + 1,
                    start_time=last_boundary_time,
                    end_time=end_frame / fps,
                    duration=(end_frame / fps) - last_boundary_time,
                    start_frame=last_boundary_frame,
                    end_frame=end_frame,
                    frame_count=end_frame - last_boundary_frame,
                    scene_type=SceneType.UNKNOWN,
                    transition_type=TransitionType.CUT,
                    confidence=1.0,
                    metadata={'detector': 'threshold', 'method': self.method}
                )
                scenes.append(scene)
        else:
            # No boundaries found - entire video is one scene
            scene = Scene(
                scene_id=1,
                start_time=start_frame / fps,
                end_time=end_frame / fps,
                duration=(end_frame - start_frame) / fps,
                start_frame=start_frame,
                end_frame=end_frame,
                frame_count=end_frame - start_frame,
                scene_type=SceneType.UNKNOWN,
                transition_type=TransitionType.CUT,
                confidence=1.0,
                metadata={'detector': 'threshold', 'method': self.method}
            )
            scenes.append(scene)

        return scenes

    def _post_process_scenes(self, scenes: List[Scene]) -> List[Scene]:
        """Post-process detected scenes"""
        # Filter short scenes
        if self.config.min_scene_length > 0:
            scenes = self.filter_short_scenes(scenes)

        # Split long scenes if configured
        if self.config.max_scene_length:
            scenes = self.split_long_scenes(scenes)

        # Renumber scenes
        for idx, scene in enumerate(scenes, start=1):
            scene.scene_id = idx

        return scenes


def detect_scenes_threshold(
    video_path: Path,
    threshold: float = 30.0,
    method: str = "histogram",
    min_scene_length: float = 1.0
) -> List[Scene]:
    """
    Convenience function for threshold-based scene detection

    Args:
        video_path: Path to video file
        threshold: Detection threshold
        method: Comparison method (histogram, mse, ssim)
        min_scene_length: Minimum scene length in seconds

    Returns:
        List of detected scenes
    """
    config = SceneDetectorConfig(
        threshold=threshold,
        min_scene_length=min_scene_length
    )

    detector = ThresholdSceneDetector(config=config, method=method)
    return detector.detect_scenes(video_path)
