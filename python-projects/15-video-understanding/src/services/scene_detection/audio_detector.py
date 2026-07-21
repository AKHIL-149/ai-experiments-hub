"""
Audio-based scene detection
Detects scene changes using audio analysis (silence, energy, spectral features)
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple
import tempfile
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


class AudioBasedSceneDetector(SceneDetector):
    """
    Detect scenes using audio analysis
    Analyzes silence periods, energy changes, and spectral features
    """

    def __init__(
        self,
        config: Optional[SceneDetectorConfig] = None,
        silence_threshold: float = -40.0,  # dB
        min_silence_duration: float = 0.5,  # seconds
        energy_threshold: float = 0.3
    ):
        """
        Initialize audio-based scene detector

        Args:
            config: Detector configuration
            silence_threshold: Silence threshold in dB
            min_silence_duration: Minimum silence duration to detect
            energy_threshold: Energy change threshold (0-1)
        """
        super().__init__(config)
        self.silence_threshold = silence_threshold
        self.min_silence_duration = min_silence_duration
        self.energy_threshold = energy_threshold

    def detect_scenes(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Scene]:
        """
        Detect scenes using audio analysis

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
            f"Detecting scenes in {video_path} using audio analysis "
            f"(silence_threshold={self.silence_threshold}dB, "
            f"energy_threshold={self.energy_threshold})"
        )

        try:
            # Import audio processing dependencies
            try:
                import librosa
                import soundfile as sf
            except ImportError:
                raise RuntimeError(
                    "Audio analysis requires librosa and soundfile. "
                    "Install with: pip install librosa soundfile"
                )

            # Extract audio from video
            audio_data, sample_rate = self._extract_audio(video_path)

            if audio_data is None or len(audio_data) == 0:
                logger.warning("No audio found in video, returning single scene")
                return self._create_single_scene(video_path)

            duration = len(audio_data) / sample_rate

            logger.debug(f"Audio: {len(audio_data)} samples, {sample_rate} Hz, {duration:.2f}s")

            # Detect scene boundaries from audio
            scene_boundaries = []

            # Detect silence boundaries
            silence_boundaries = self._detect_silence(audio_data, sample_rate)
            scene_boundaries.extend(silence_boundaries)

            # Detect energy changes
            energy_boundaries = self._detect_energy_changes(audio_data, sample_rate)
            scene_boundaries.extend(energy_boundaries)

            # Remove duplicates and sort
            scene_boundaries = self._merge_boundaries(scene_boundaries)

            # Filter by time range
            if start_time or end_time:
                scene_boundaries = [
                    b for b in scene_boundaries
                    if (not start_time or b['timestamp'] >= start_time) and
                       (not end_time or b['timestamp'] <= end_time)
                ]

            logger.info(f"Found {len(scene_boundaries)} scene boundaries from audio")

            # Get video FPS for frame calculations
            fps = self._get_video_fps(video_path)

            # Convert boundaries to scenes
            scenes = self._boundaries_to_scenes(
                scene_boundaries,
                fps,
                int((start_time or 0) * fps),
                int((end_time or duration) * fps),
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
            raise RuntimeError(f"Audio scene detection failed: {e}") from e

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

    def _extract_audio(self, video_path: Path) -> Tuple[Optional[np.ndarray], int]:
        """
        Extract audio from video

        Args:
            video_path: Path to video file

        Returns:
            Tuple of (audio data, sample rate)
        """
        try:
            import librosa

            # Load audio from video
            audio_data, sample_rate = librosa.load(str(video_path), sr=None, mono=True)

            return audio_data, sample_rate

        except Exception as e:
            logger.warning(f"Failed to extract audio: {e}")
            return None, 0

    def _detect_silence(
        self,
        audio_data: np.ndarray,
        sample_rate: int
    ) -> List[dict]:
        """
        Detect silence periods in audio

        Args:
            audio_data: Audio samples
            sample_rate: Sample rate

        Returns:
            List of silence boundary dicts
        """
        import librosa

        # Convert to dB
        # Add small epsilon to avoid log(0)
        epsilon = 1e-10
        audio_db = librosa.amplitude_to_db(np.abs(audio_data) + epsilon, ref=np.max)

        # Find silence frames
        silence_mask = audio_db < self.silence_threshold

        # Find transitions (non-silence to silence and vice versa)
        boundaries = []
        in_silence = False
        silence_start = 0

        hop_length = 512
        frame_duration = hop_length / sample_rate

        for i in range(len(silence_mask)):
            if silence_mask[i] and not in_silence:
                # Start of silence
                silence_start = i * frame_duration
                in_silence = True
            elif not silence_mask[i] and in_silence:
                # End of silence
                silence_end = i * frame_duration
                silence_duration = silence_end - silence_start

                # Only mark as boundary if silence is long enough
                if silence_duration >= self.min_silence_duration:
                    # Mark end of silence as scene boundary
                    boundaries.append({
                        'timestamp': silence_end,
                        'type': 'silence',
                        'duration': silence_duration
                    })

                in_silence = False

        return boundaries

    def _detect_energy_changes(
        self,
        audio_data: np.ndarray,
        sample_rate: int
    ) -> List[dict]:
        """
        Detect energy changes in audio

        Args:
            audio_data: Audio samples
            sample_rate: Sample rate

        Returns:
            List of energy change boundary dicts
        """
        import librosa

        # Calculate RMS energy
        hop_length = 512
        frame_length = 2048

        rms = librosa.feature.rms(
            y=audio_data,
            frame_length=frame_length,
            hop_length=hop_length
        )[0]

        # Normalize
        rms_normalized = rms / (np.max(rms) + 1e-10)

        # Calculate energy differences
        energy_diff = np.abs(np.diff(rms_normalized))

        # Find significant changes
        boundaries = []
        threshold = self.energy_threshold

        for i in range(len(energy_diff)):
            if energy_diff[i] > threshold:
                timestamp = (i * hop_length) / sample_rate
                boundaries.append({
                    'timestamp': timestamp,
                    'type': 'energy',
                    'change': float(energy_diff[i])
                })

        return boundaries

    def _merge_boundaries(self, boundaries: List[dict]) -> List[dict]:
        """
        Merge and deduplicate boundaries

        Args:
            boundaries: List of boundary dicts

        Returns:
            Merged and sorted boundaries
        """
        if not boundaries:
            return []

        # Sort by timestamp
        boundaries.sort(key=lambda x: x['timestamp'])

        # Merge boundaries within 0.5 seconds
        merged = []
        current = boundaries[0]

        for next_boundary in boundaries[1:]:
            if next_boundary['timestamp'] - current['timestamp'] < 0.5:
                # Merge: keep the one with higher confidence/change
                if next_boundary.get('change', 0) > current.get('change', 0):
                    current = next_boundary
            else:
                merged.append(current)
                current = next_boundary

        merged.append(current)

        return merged

    def _get_video_fps(self, video_path: Path) -> float:
        """Get video FPS"""
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()

        return fps if fps > 0 else 25.0  # Default to 25 if unknown

    def _create_single_scene(self, video_path: Path) -> List[Scene]:
        """Create a single scene for the entire video"""
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        duration = frame_count / fps

        return [Scene(
            scene_id=1,
            start_time=0.0,
            end_time=duration,
            duration=duration,
            start_frame=0,
            end_frame=frame_count,
            frame_count=frame_count,
            scene_type=SceneType.UNKNOWN,
            transition_type=TransitionType.CUT,
            confidence=1.0,
            metadata={'detector': 'audio', 'note': 'no_audio_found'}
        )]

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
            first_boundary_time = boundaries[0]['timestamp']
            first_boundary_frame = int(first_boundary_time * fps)

            if first_boundary_frame > start_frame:
                # Determine scene type from audio features
                scene_type = SceneType.DIALOGUE if boundaries[0].get('type') == 'energy' else SceneType.STATIC

                scene = Scene(
                    scene_id=1,
                    start_time=start_frame / fps,
                    end_time=first_boundary_time,
                    duration=first_boundary_time - (start_frame / fps),
                    start_frame=start_frame,
                    end_frame=first_boundary_frame,
                    frame_count=first_boundary_frame - start_frame,
                    scene_type=scene_type,
                    transition_type=TransitionType.CUT,
                    confidence=1.0,
                    metadata={'detector': 'audio'}
                )
                scenes.append(scene)

        # Add middle scenes (between boundaries)
        for i in range(len(boundaries) - 1):
            start_boundary = boundaries[i]
            end_boundary = boundaries[i + 1]

            start_time = start_boundary['timestamp']
            end_time = end_boundary['timestamp']
            start_frame_num = int(start_time * fps)
            end_frame_num = int(end_time * fps)

            # Determine scene type
            scene_type = SceneType.DIALOGUE if start_boundary.get('type') == 'energy' else SceneType.STATIC

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
                    'detector': 'audio',
                    'boundary_type': start_boundary.get('type', 'unknown')
                }
            )
            scenes.append(scene)

        # Add last scene (from last boundary to end)
        if boundaries:
            last_boundary = boundaries[-1]
            last_boundary_time = last_boundary['timestamp']
            last_boundary_frame = int(last_boundary_time * fps)

            if last_boundary_frame < end_frame:
                scene_type = SceneType.DIALOGUE if last_boundary.get('type') == 'energy' else SceneType.STATIC

                scene = Scene(
                    scene_id=len(scenes) + 1,
                    start_time=last_boundary_time,
                    end_time=end_frame / fps,
                    duration=(end_frame / fps) - last_boundary_time,
                    start_frame=last_boundary_frame,
                    end_frame=end_frame,
                    frame_count=end_frame - last_boundary_frame,
                    scene_type=scene_type,
                    transition_type=TransitionType.CUT,
                    confidence=1.0,
                    metadata={'detector': 'audio'}
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
                metadata={'detector': 'audio', 'note': 'no_boundaries_detected'}
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


def detect_scenes_audio(
    video_path: Path,
    silence_threshold: float = -40.0,
    min_silence_duration: float = 0.5,
    energy_threshold: float = 0.3,
    min_scene_length: float = 1.0
) -> List[Scene]:
    """
    Convenience function for audio-based scene detection

    Args:
        video_path: Path to video file
        silence_threshold: Silence threshold in dB
        min_silence_duration: Minimum silence duration in seconds
        energy_threshold: Energy change threshold (0-1)
        min_scene_length: Minimum scene length in seconds

    Returns:
        List of detected scenes
    """
    config = SceneDetectorConfig(
        min_scene_length=min_scene_length
    )

    detector = AudioBasedSceneDetector(
        config=config,
        silence_threshold=silence_threshold,
        min_silence_duration=min_silence_duration,
        energy_threshold=energy_threshold
    )
    return detector.detect_scenes(video_path)
