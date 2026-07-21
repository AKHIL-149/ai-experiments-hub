"""
Scene classification
Classifies scenes into different types based on visual and audio features
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import numpy as np
import cv2

from src.services.scene_detection.base import (
    Scene,
    SceneType,
    TransitionType
)

logger = logging.getLogger(__name__)


class SceneClassifier:
    """
    Classify scenes based on visual and audio features
    Determines scene type: static, motion, dialogue, action, transition
    """

    def __init__(
        self,
        motion_threshold_low: float = 1.0,
        motion_threshold_high: float = 5.0,
        audio_energy_threshold: float = 0.3
    ):
        """
        Initialize scene classifier

        Args:
            motion_threshold_low: Low motion threshold
            motion_threshold_high: High motion threshold
            audio_energy_threshold: Audio energy threshold
        """
        self.motion_threshold_low = motion_threshold_low
        self.motion_threshold_high = motion_threshold_high
        self.audio_energy_threshold = audio_energy_threshold

    def classify_scenes(
        self,
        scenes: List[Scene],
        video_path: Path,
        include_audio: bool = True
    ) -> List[Scene]:
        """
        Classify all scenes in video

        Args:
            scenes: List of scenes to classify
            video_path: Path to video file
            include_audio: Whether to analyze audio features

        Returns:
            Scenes with updated scene_type
        """
        logger.info(f"Classifying {len(scenes)} scenes from {video_path}")

        for scene in scenes:
            scene_type = self.classify_scene(
                scene,
                video_path,
                include_audio=include_audio
            )
            scene.scene_type = scene_type

        # Log classification results
        type_counts = {}
        for scene in scenes:
            type_counts[scene.scene_type.value] = type_counts.get(scene.scene_type.value, 0) + 1

        logger.info(f"Scene classification complete: {type_counts}")

        return scenes

    def classify_scene(
        self,
        scene: Scene,
        video_path: Path,
        include_audio: bool = True
    ) -> SceneType:
        """
        Classify a single scene

        Args:
            scene: Scene to classify
            video_path: Path to video file
            include_audio: Whether to analyze audio

        Returns:
            Scene type
        """
        # Extract visual features
        motion_score = self._calculate_motion_score(video_path, scene)

        # Extract audio features if available
        audio_features = None
        if include_audio:
            audio_features = self._extract_audio_features(video_path, scene)

        # Classify based on features
        scene_type = self._classify_from_features(
            motion_score,
            audio_features
        )

        logger.debug(
            f"Scene {scene.scene_id} classified as {scene_type.value} "
            f"(motion={motion_score:.2f})"
        )

        return scene_type

    def _calculate_motion_score(
        self,
        video_path: Path,
        scene: Scene
    ) -> float:
        """
        Calculate motion score for scene

        Args:
            video_path: Path to video file
            scene: Scene to analyze

        Returns:
            Motion score (0-10)
        """
        try:
            cap = cv2.VideoCapture(str(video_path))

            if not cap.isOpened():
                logger.warning(f"Failed to open video: {video_path}")
                return 0.0

            fps = cap.get(cv2.CAP_PROP_FPS)

            # Sample frames from scene
            sample_frames = self._sample_frames(
                cap,
                scene.start_frame,
                scene.end_frame,
                num_samples=10
            )

            if len(sample_frames) < 2:
                cap.release()
                return 0.0

            # Calculate optical flow between consecutive frames
            flow_magnitudes = []

            for i in range(len(sample_frames) - 1):
                flow_mag = self._calculate_optical_flow_magnitude(
                    sample_frames[i],
                    sample_frames[i + 1]
                )
                flow_magnitudes.append(flow_mag)

            cap.release()

            # Return average motion
            return float(np.mean(flow_magnitudes)) if flow_magnitudes else 0.0

        except Exception as e:
            logger.warning(f"Motion calculation failed: {e}")
            return 0.0

    def _extract_audio_features(
        self,
        video_path: Path,
        scene: Scene
    ) -> Optional[Dict[str, float]]:
        """
        Extract audio features for scene

        Args:
            video_path: Path to video file
            scene: Scene to analyze

        Returns:
            Dictionary of audio features
        """
        try:
            import librosa

            # Load audio for scene timerange
            audio, sr = librosa.load(
                str(video_path),
                sr=None,
                offset=scene.start_time,
                duration=scene.duration
            )

            if len(audio) == 0:
                return None

            # Calculate features
            # 1. RMS Energy
            rms = librosa.feature.rms(y=audio)[0]
            avg_energy = float(np.mean(rms))
            max_energy = float(np.max(rms))

            # 2. Zero Crossing Rate (speech indicator)
            zcr = librosa.feature.zero_crossing_rate(audio)[0]
            avg_zcr = float(np.mean(zcr))

            # 3. Spectral Centroid (brightness)
            spectral_centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)[0]
            avg_centroid = float(np.mean(spectral_centroid))

            # 4. Tempo (if detectable)
            try:
                tempo, _ = librosa.beat.beat_track(y=audio, sr=sr)
                tempo = float(tempo)
            except:
                tempo = 0.0

            return {
                'avg_energy': avg_energy,
                'max_energy': max_energy,
                'avg_zcr': avg_zcr,
                'avg_centroid': avg_centroid,
                'tempo': tempo
            }

        except ImportError:
            logger.debug("librosa not available for audio feature extraction")
            return None
        except Exception as e:
            logger.debug(f"Audio feature extraction failed: {e}")
            return None

    def _classify_from_features(
        self,
        motion_score: float,
        audio_features: Optional[Dict[str, float]]
    ) -> SceneType:
        """
        Classify scene based on extracted features

        Args:
            motion_score: Motion score
            audio_features: Audio features dict

        Returns:
            Scene type
        """
        # Static scene: low motion, low audio
        if motion_score < self.motion_threshold_low:
            if audio_features is None or audio_features['avg_energy'] < 0.1:
                return SceneType.STATIC
            else:
                # Low motion but with audio - likely dialogue
                return SceneType.DIALOGUE

        # High motion scene
        if motion_score > self.motion_threshold_high:
            return SceneType.ACTION

        # Medium motion
        if audio_features and audio_features['avg_energy'] > self.audio_energy_threshold:
            # Medium motion with significant audio
            # Check if it's speech (high ZCR) or music (tempo)
            if audio_features.get('avg_zcr', 0) > 0.1:
                return SceneType.DIALOGUE
            else:
                return SceneType.MOTION
        else:
            return SceneType.MOTION

    def _sample_frames(
        self,
        cap: cv2.VideoCapture,
        start_frame: int,
        end_frame: int,
        num_samples: int = 10
    ) -> List[np.ndarray]:
        """
        Sample frames from video

        Args:
            cap: Video capture object
            start_frame: Start frame number
            end_frame: End frame number
            num_samples: Number of frames to sample

        Returns:
            List of sampled frames
        """
        frame_count = end_frame - start_frame
        if frame_count <= 0:
            return []

        # Calculate sample interval
        interval = max(1, frame_count // num_samples)

        frames = []
        for i in range(0, frame_count, interval):
            frame_num = start_frame + i

            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()

            if ret:
                # Convert to grayscale for motion analysis
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frames.append(gray)

            if len(frames) >= num_samples:
                break

        return frames

    def _calculate_optical_flow_magnitude(
        self,
        frame1: np.ndarray,
        frame2: np.ndarray
    ) -> float:
        """
        Calculate optical flow magnitude between frames

        Args:
            frame1: First frame (grayscale)
            frame2: Second frame (grayscale)

        Returns:
            Average flow magnitude
        """
        # Calculate optical flow
        flow = cv2.calcOpticalFlowFarneback(
            frame1,
            frame2,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0
        )

        # Calculate magnitude
        magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])

        return float(np.mean(magnitude))

    def classify_transition(
        self,
        scene: Scene,
        video_path: Path
    ) -> TransitionType:
        """
        Classify transition type for scene

        Args:
            scene: Scene to analyze
            video_path: Path to video file

        Returns:
            Transition type
        """
        try:
            cap = cv2.VideoCapture(str(video_path))

            if not cap.isOpened():
                return TransitionType.UNKNOWN

            # Sample frames around scene boundary
            boundary_frames = []

            # Get 3 frames before and after scene start
            for offset in [-3, -2, -1, 0, 1, 2, 3]:
                frame_num = scene.start_frame + offset
                if frame_num >= 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                    ret, frame = cap.read()
                    if ret:
                        boundary_frames.append(frame)

            cap.release()

            if len(boundary_frames) < 4:
                return TransitionType.CUT

            # Analyze transition pattern
            transition_type = self._analyze_transition_pattern(boundary_frames)

            return transition_type

        except Exception as e:
            logger.debug(f"Transition classification failed: {e}")
            return TransitionType.CUT

    def _analyze_transition_pattern(
        self,
        frames: List[np.ndarray]
    ) -> TransitionType:
        """
        Analyze frame sequence to determine transition type

        Args:
            frames: Sequence of frames around transition

        Returns:
            Transition type
        """
        # Calculate brightness for each frame
        brightness = []
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness.append(np.mean(gray))

        # Analyze brightness pattern
        if len(brightness) < 4:
            return TransitionType.CUT

        # Check for fade pattern (gradual brightness change)
        brightness_diff = np.diff(brightness)
        max_diff = np.max(np.abs(brightness_diff))

        if max_diff < 30:  # Gradual change
            # Check if fading to/from black
            min_brightness = min(brightness)
            if min_brightness < 30:
                return TransitionType.FADE
            else:
                return TransitionType.DISSOLVE
        else:
            # Abrupt change
            return TransitionType.CUT

    def get_scene_statistics(
        self,
        scenes: List[Scene]
    ) -> Dict[str, any]:
        """
        Get statistics about scene classifications

        Args:
            scenes: List of classified scenes

        Returns:
            Statistics dictionary
        """
        stats = {
            'total_scenes': len(scenes),
            'scene_types': {},
            'transition_types': {},
            'avg_duration_by_type': {}
        }

        # Count scene types
        for scene in scenes:
            scene_type = scene.scene_type.value
            stats['scene_types'][scene_type] = stats['scene_types'].get(scene_type, 0) + 1

        # Count transition types
        for scene in scenes:
            trans_type = scene.transition_type.value
            stats['transition_types'][trans_type] = stats['transition_types'].get(trans_type, 0) + 1

        # Calculate average duration by type
        duration_by_type = {}
        count_by_type = {}

        for scene in scenes:
            scene_type = scene.scene_type.value
            duration_by_type[scene_type] = duration_by_type.get(scene_type, 0) + scene.duration
            count_by_type[scene_type] = count_by_type.get(scene_type, 0) + 1

        for scene_type in duration_by_type:
            stats['avg_duration_by_type'][scene_type] = duration_by_type[scene_type] / count_by_type[scene_type]

        return stats


def classify_scenes(
    scenes: List[Scene],
    video_path: Path,
    include_audio: bool = True
) -> List[Scene]:
    """
    Convenience function for scene classification

    Args:
        scenes: List of scenes to classify
        video_path: Path to video file
        include_audio: Whether to use audio features

    Returns:
        Classified scenes
    """
    classifier = SceneClassifier()
    return classifier.classify_scenes(scenes, video_path, include_audio)
