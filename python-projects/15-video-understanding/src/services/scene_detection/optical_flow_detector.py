"""
Optical flow-based scene detection
Detects scene changes using motion analysis and optical flow
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple
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


class OpticalFlowDetector(SceneDetector):
    """
    Detect scenes using optical flow analysis
    Analyzes motion patterns between consecutive frames
    """

    def __init__(
        self,
        config: Optional[SceneDetectorConfig] = None,
        flow_threshold: float = 2.0,
        motion_threshold: float = 0.3
    ):
        """
        Initialize optical flow scene detector

        Args:
            config: Detector configuration
            flow_threshold: Threshold for optical flow magnitude
            motion_threshold: Threshold for motion percentage
        """
        super().__init__(config)
        self.flow_threshold = flow_threshold
        self.motion_threshold = motion_threshold

    def detect_scenes(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Scene]:
        """
        Detect scenes using optical flow analysis

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
            f"Detecting scenes in {video_path} using optical flow method "
            f"(flow_threshold={self.flow_threshold}, motion_threshold={self.motion_threshold})"
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

            # Detect scene boundaries using optical flow
            scene_boundaries = []
            prev_gray = None
            current_frame_num = start_frame
            motion_history = []

            while current_frame_num < end_frame:
                ret, frame = cap.read()

                if not ret:
                    break

                # Convert to grayscale
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if prev_gray is not None:
                    # Calculate optical flow
                    flow_magnitude = self._calculate_optical_flow(prev_gray, gray)

                    # Track motion history for smoothing
                    motion_history.append(flow_magnitude)
                    if len(motion_history) > 5:
                        motion_history.pop(0)

                    # Detect scene change
                    if self._is_scene_change(flow_magnitude, motion_history):
                        timestamp = current_frame_num / fps
                        scene_boundaries.append({
                            'frame': current_frame_num,
                            'timestamp': timestamp,
                            'flow_magnitude': flow_magnitude
                        })

                        logger.debug(
                            f"Scene change at frame {current_frame_num} "
                            f"({timestamp:.2f}s), flow_magnitude={flow_magnitude:.2f}"
                        )

                prev_gray = gray
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

    def _calculate_optical_flow(
        self,
        prev_frame: np.ndarray,
        curr_frame: np.ndarray
    ) -> float:
        """
        Calculate optical flow between two frames

        Args:
            prev_frame: Previous grayscale frame
            curr_frame: Current grayscale frame

        Returns:
            Average flow magnitude
        """
        # Calculate dense optical flow using Farneback method
        flow = cv2.calcOpticalFlowFarneback(
            prev_frame,
            curr_frame,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0
        )

        # Calculate magnitude of flow vectors
        magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])

        # Return average magnitude
        return float(np.mean(magnitude))

    def _is_scene_change(
        self,
        flow_magnitude: float,
        motion_history: List[float]
    ) -> bool:
        """
        Determine if current flow indicates a scene change

        Args:
            flow_magnitude: Current flow magnitude
            motion_history: Recent motion history

        Returns:
            True if scene change detected
        """
        if len(motion_history) < 2:
            return False

        # Calculate average motion from history
        avg_motion = sum(motion_history) / len(motion_history)

        # Detect sudden drop in motion (cut)
        if avg_motion > self.flow_threshold and flow_magnitude < self.flow_threshold * 0.3:
            return True

        # Detect sudden spike in motion (transition start)
        if flow_magnitude > self.flow_threshold * 2 and avg_motion < self.flow_threshold:
            return True

        # Detect sustained high motion difference
        motion_diff = abs(flow_magnitude - avg_motion)
        if motion_diff > self.flow_threshold:
            return True

        return False

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
                    metadata={'detector': 'optical_flow'}
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

            # Determine scene type based on motion
            flow_magnitude = start_boundary.get('flow_magnitude', 0)
            scene_type = self._classify_scene_type(flow_magnitude)

            scene = Scene(
                scene_id=len(scenes) + 1,
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                start_frame=start_frame_num,
                end_frame=end_frame_num,
                frame_count=end_frame_num - start_frame_num,
                scene_type=scene_type,
                transition_type=TransitionType.CUT,
                confidence=1.0,
                metadata={
                    'detector': 'optical_flow',
                    'flow_magnitude': flow_magnitude
                }
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
                    metadata={'detector': 'optical_flow'}
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
                metadata={'detector': 'optical_flow'}
            )
            scenes.append(scene)

        return scenes

    def _classify_scene_type(self, flow_magnitude: float) -> SceneType:
        """
        Classify scene type based on motion

        Args:
            flow_magnitude: Average optical flow magnitude

        Returns:
            Classified scene type
        """
        if flow_magnitude < 1.0:
            return SceneType.STATIC
        elif flow_magnitude < 3.0:
            return SceneType.MOTION
        else:
            return SceneType.ACTION

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


def detect_scenes_optical_flow(
    video_path: Path,
    flow_threshold: float = 2.0,
    motion_threshold: float = 0.3,
    min_scene_length: float = 1.0
) -> List[Scene]:
    """
    Convenience function for optical flow-based scene detection

    Args:
        video_path: Path to video file
        flow_threshold: Optical flow magnitude threshold
        motion_threshold: Motion percentage threshold
        min_scene_length: Minimum scene length in seconds

    Returns:
        List of detected scenes
    """
    config = SceneDetectorConfig(
        min_scene_length=min_scene_length
    )

    detector = OpticalFlowDetector(
        config=config,
        flow_threshold=flow_threshold,
        motion_threshold=motion_threshold
    )
    return detector.detect_scenes(video_path)
