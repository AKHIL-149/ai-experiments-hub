"""
Color histogram-based scene detection and transition classification
Analyzes color distribution changes to detect scenes and classify transitions
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Tuple
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


class ColorHistogramAnalyzer(SceneDetector):
    """
    Analyze color histograms to detect scenes and classify transitions
    Compares color distributions between consecutive frames
    """

    def __init__(
        self,
        config: Optional[SceneDetectorConfig] = None,
        hist_bins: int = 32,
        channels: str = "rgb"
    ):
        """
        Initialize color histogram analyzer

        Args:
            config: Detector configuration
            hist_bins: Number of histogram bins per channel
            channels: Color channels to analyze (rgb, hsv, lab)
        """
        super().__init__(config)
        self.hist_bins = hist_bins
        self.channels = channels.lower()

    def detect_scenes(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Scene]:
        """
        Detect scenes using color histogram analysis

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
            f"Detecting scenes in {video_path} using color histogram analysis "
            f"(threshold={self.config.threshold}, bins={self.hist_bins}, channels={self.channels})"
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
            prev_hist = None
            current_frame_num = start_frame

            while current_frame_num < end_frame:
                ret, frame = cap.read()

                if not ret:
                    break

                # Compute color histogram
                hist = self._compute_histogram(frame)

                if prev_hist is not None:
                    # Calculate histogram difference
                    diff = self._histogram_difference(prev_hist, hist)

                    # Classify transition type
                    transition_type = self._classify_transition(
                        prev_frame,
                        frame,
                        diff
                    )

                    # Check if exceeds threshold
                    if diff > self.config.threshold:
                        timestamp = current_frame_num / fps
                        scene_boundaries.append({
                            'frame': current_frame_num,
                            'timestamp': timestamp,
                            'diff': diff,
                            'transition_type': transition_type
                        })

                        logger.debug(
                            f"Scene change at frame {current_frame_num} "
                            f"({timestamp:.2f}s), diff={diff:.2f}, type={transition_type.value}"
                        )

                prev_frame = frame
                prev_hist = hist
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

    def _compute_histogram(self, frame: np.ndarray) -> np.ndarray:
        """
        Compute color histogram for frame

        Args:
            frame: BGR frame

        Returns:
            Normalized histogram
        """
        # Convert color space if needed
        if self.channels == "hsv":
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        elif self.channels == "lab":
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        # RGB is default (BGR in OpenCV)

        # Compute histogram for each channel
        hist = []
        for i in range(3):
            channel_hist = cv2.calcHist(
                [frame],
                [i],
                None,
                [self.hist_bins],
                [0, 256]
            )
            channel_hist = cv2.normalize(channel_hist, channel_hist).flatten()
            hist.extend(channel_hist)

        return np.array(hist)

    def _histogram_difference(
        self,
        hist1: np.ndarray,
        hist2: np.ndarray
    ) -> float:
        """
        Calculate difference between two histograms

        Args:
            hist1: First histogram
            hist2: Second histogram

        Returns:
            Difference score (0-100)
        """
        # Use Chi-Square distance for better sensitivity
        # Avoid division by zero
        epsilon = 1e-10
        chi_square = np.sum(
            ((hist1 - hist2) ** 2) / (hist1 + hist2 + epsilon)
        )

        # Normalize to 0-100 range
        diff = min(chi_square / 10, 100)

        return float(diff)

    def _classify_transition(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray,
        hist_diff: float
    ) -> TransitionType:
        """
        Classify the type of transition between frames

        Args:
            frame1: Previous frame
            frame2: Current frame
            hist_diff: Histogram difference score

        Returns:
            Classified transition type
        """
        # Hard cut: Large histogram difference
        if hist_diff > self.config.threshold * 2:
            return TransitionType.CUT

        # Check for fade/dissolve patterns
        # Calculate brightness histograms
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        brightness1 = np.mean(gray1)
        brightness2 = np.mean(gray2)

        # Fade to/from black
        if brightness1 < 30 or brightness2 < 30:
            return TransitionType.FADE

        # Check for dissolve (blended frames)
        # Compare edge detection results
        edges1 = cv2.Canny(gray1, 50, 150)
        edges2 = cv2.Canny(gray2, 50, 150)

        edge_diff = np.sum(np.abs(edges1.astype(float) - edges2.astype(float)))
        edge_ratio = edge_diff / (edges1.size * 255)

        # Dissolve typically has moderate edge changes
        if 0.1 < edge_ratio < 0.3:
            return TransitionType.DISSOLVE

        # Default to cut for other cases
        return TransitionType.CUT

    def analyze_transition_sequence(
        self,
        video_path: Path,
        start_frame: int,
        end_frame: int
    ) -> Dict[str, any]:
        """
        Analyze a sequence of frames to classify transition type

        Args:
            video_path: Path to video file
            start_frame: Start frame number
            end_frame: End frame number

        Returns:
            Dictionary with transition analysis
        """
        cap = cv2.VideoCapture(str(video_path))

        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        # Collect histograms and brightness values
        histograms = []
        brightness_values = []

        for frame_num in range(start_frame, end_frame + 1):
            ret, frame = cap.read()
            if not ret:
                break

            hist = self._compute_histogram(frame)
            histograms.append(hist)

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness_values.append(np.mean(gray))

        cap.release()

        # Analyze patterns
        hist_diffs = []
        for i in range(len(histograms) - 1):
            diff = self._histogram_difference(histograms[i], histograms[i + 1])
            hist_diffs.append(diff)

        avg_hist_diff = np.mean(hist_diffs) if hist_diffs else 0
        max_hist_diff = max(hist_diffs) if hist_diffs else 0

        brightness_change = abs(brightness_values[-1] - brightness_values[0]) if brightness_values else 0

        # Classify based on patterns
        if max_hist_diff > self.config.threshold * 3:
            transition_type = TransitionType.CUT
        elif brightness_change > 100:
            transition_type = TransitionType.FADE
        elif avg_hist_diff > self.config.threshold * 0.5:
            transition_type = TransitionType.DISSOLVE
        else:
            transition_type = TransitionType.UNKNOWN

        return {
            'transition_type': transition_type,
            'avg_hist_diff': avg_hist_diff,
            'max_hist_diff': max_hist_diff,
            'brightness_change': brightness_change,
            'frame_count': len(histograms)
        }

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
                    metadata={'detector': 'color_histogram', 'channels': self.channels}
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

            transition_type = start_boundary.get('transition_type', TransitionType.CUT)

            scene = Scene(
                scene_id=len(scenes) + 1,
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                start_frame=start_frame_num,
                end_frame=end_frame_num,
                frame_count=end_frame_num - start_frame_num,
                scene_type=SceneType.UNKNOWN,
                transition_type=transition_type,
                confidence=1.0,
                metadata={
                    'detector': 'color_histogram',
                    'channels': self.channels,
                    'diff': start_boundary.get('diff', 0)
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
                    metadata={'detector': 'color_histogram', 'channels': self.channels}
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
                metadata={'detector': 'color_histogram', 'channels': self.channels}
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


def detect_scenes_color_histogram(
    video_path: Path,
    threshold: float = 30.0,
    hist_bins: int = 32,
    channels: str = "rgb",
    min_scene_length: float = 1.0
) -> List[Scene]:
    """
    Convenience function for color histogram-based scene detection

    Args:
        video_path: Path to video file
        threshold: Detection threshold
        hist_bins: Number of histogram bins per channel
        channels: Color channels (rgb, hsv, lab)
        min_scene_length: Minimum scene length in seconds

    Returns:
        List of detected scenes
    """
    config = SceneDetectorConfig(
        threshold=threshold,
        min_scene_length=min_scene_length,
        detect_transitions=True
    )

    analyzer = ColorHistogramAnalyzer(
        config=config,
        hist_bins=hist_bins,
        channels=channels
    )
    return analyzer.detect_scenes(video_path)
