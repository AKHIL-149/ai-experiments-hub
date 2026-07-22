"""
Audio feature extraction service
Extracts acoustic and spectral features from audio
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AudioFeatures:
    """Extracted audio features"""
    # Time-domain features
    duration: float
    rms_energy: float
    zero_crossing_rate: float

    # Spectral features
    spectral_centroid_mean: float
    spectral_centroid_std: float
    spectral_rolloff_mean: float
    spectral_rolloff_std: float
    spectral_bandwidth_mean: float
    spectral_bandwidth_std: float

    # Rhythm features
    tempo: float
    beat_frames: Optional[List[int]] = None

    # MFCCs (Mel-frequency cepstral coefficients)
    mfcc_mean: Optional[np.ndarray] = None
    mfcc_std: Optional[np.ndarray] = None

    # Additional metadata
    sample_rate: int = 0
    num_channels: int = 0


class AudioFeatureExtractor:
    """
    Extract audio features using librosa
    Provides rich acoustic and spectral feature extraction
    """

    def __init__(self):
        """Initialize audio feature extractor"""
        self._verify_librosa()

    def _verify_librosa(self):
        """Verify librosa is available"""
        try:
            import librosa
        except ImportError:
            logger.warning("librosa not installed. Feature extraction will not work.")

    def extract_features(
        self,
        audio_path: Path,
        include_mfcc: bool = True,
        include_beats: bool = True
    ) -> AudioFeatures:
        """
        Extract comprehensive audio features

        Args:
            audio_path: Path to audio file
            include_mfcc: Include MFCC features
            include_beats: Include beat tracking

        Returns:
            AudioFeatures object

        Raises:
            ValueError: If audio file not found
            RuntimeError: If extraction fails
        """
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_path}")

        logger.info(f"Extracting features from {audio_path}")

        try:
            import librosa

            # Load audio
            y, sr = librosa.load(str(audio_path), sr=None, mono=True)

            duration = len(y) / sr

            # Time-domain features
            rms = librosa.feature.rms(y=y)[0]
            rms_energy = float(np.mean(rms))

            zcr = librosa.feature.zero_crossing_rate(y)[0]
            zero_crossing_rate = float(np.mean(zcr))

            # Spectral features
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
            spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]

            # Tempo and beats
            tempo = 0.0
            beat_frames = None
            if include_beats:
                try:
                    tempo_val, beats = librosa.beat.beat_track(y=y, sr=sr)
                    tempo = float(tempo_val)
                    beat_frames = beats.tolist() if beats is not None else None
                except Exception as e:
                    logger.debug(f"Beat tracking failed: {e}")

            # MFCCs
            mfcc_mean = None
            mfcc_std = None
            if include_mfcc:
                mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
                mfcc_mean = np.mean(mfccs, axis=1)
                mfcc_std = np.std(mfccs, axis=1)

            features = AudioFeatures(
                duration=duration,
                rms_energy=rms_energy,
                zero_crossing_rate=zero_crossing_rate,
                spectral_centroid_mean=float(np.mean(spectral_centroids)),
                spectral_centroid_std=float(np.std(spectral_centroids)),
                spectral_rolloff_mean=float(np.mean(spectral_rolloff)),
                spectral_rolloff_std=float(np.std(spectral_rolloff)),
                spectral_bandwidth_mean=float(np.mean(spectral_bandwidth)),
                spectral_bandwidth_std=float(np.std(spectral_bandwidth)),
                tempo=tempo,
                beat_frames=beat_frames,
                mfcc_mean=mfcc_mean,
                mfcc_std=mfcc_std,
                sample_rate=sr,
                num_channels=1
            )

            logger.info(f"Feature extraction complete: {duration:.2f}s audio")

            return features

        except ImportError:
            raise RuntimeError("librosa required for feature extraction. Install with: pip install librosa")
        except Exception as e:
            raise RuntimeError(f"Feature extraction failed: {e}") from e

    def extract_segment_features(
        self,
        audio_path: Path,
        start_time: float,
        end_time: float
    ) -> AudioFeatures:
        """
        Extract features from audio segment

        Args:
            audio_path: Path to audio file
            start_time: Start time in seconds
            end_time: End time in seconds

        Returns:
            AudioFeatures for the segment
        """
        try:
            import librosa

            # Load segment
            duration = end_time - start_time
            y, sr = librosa.load(
                str(audio_path),
                sr=None,
                offset=start_time,
                duration=duration
            )

            # Extract features for this segment
            # (simplified version)
            rms = librosa.feature.rms(y=y)[0]
            zcr = librosa.feature.zero_crossing_rate(y)[0]

            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

            features = AudioFeatures(
                duration=duration,
                rms_energy=float(np.mean(rms)),
                zero_crossing_rate=float(np.mean(zcr)),
                spectral_centroid_mean=float(np.mean(spectral_centroids)),
                spectral_centroid_std=float(np.std(spectral_centroids)),
                spectral_rolloff_mean=0.0,
                spectral_rolloff_std=0.0,
                spectral_bandwidth_mean=0.0,
                spectral_bandwidth_std=0.0,
                tempo=0.0,
                sample_rate=sr
            )

            return features

        except Exception as e:
            raise RuntimeError(f"Segment feature extraction failed: {e}") from e

    def classify_audio_type(self, features: AudioFeatures) -> str:
        """
        Classify audio type based on features

        Args:
            features: Extracted audio features

        Returns:
            Audio type (speech, music, silence, noise)
        """
        # Simple heuristic-based classification
        # In production, use ML model

        # Silence detection
        if features.rms_energy < 0.01:
            return "silence"

        # Speech vs music discrimination
        # Speech typically has:
        # - Higher ZCR
        # - Lower spectral centroid variance
        # - No clear tempo

        if features.zero_crossing_rate > 0.15:
            if features.tempo > 0 and features.tempo < 60:
                return "speech"
            elif features.spectral_centroid_std < 500:
                return "speech"
            else:
                return "noise"
        else:
            # Lower ZCR suggests music or tonal content
            if features.tempo > 60:
                return "music"
            else:
                return "speech"

    def detect_music_segments(
        self,
        audio_path: Path,
        threshold: float = 0.5
    ) -> List[Tuple[float, float]]:
        """
        Detect music segments in audio

        Args:
            audio_path: Path to audio file
            threshold: Detection threshold

        Returns:
            List of (start_time, end_time) for music segments
        """
        try:
            import librosa

            logger.info(f"Detecting music segments in {audio_path}")

            # Load audio
            y, sr = librosa.load(str(audio_path), sr=None)

            # Compute spectral contrast (good for music detection)
            contrast = librosa.feature.spectral_contrast(y=y, sr=sr)

            # Average across frequency bands
            contrast_mean = np.mean(contrast, axis=0)

            # Detect music segments (high spectral contrast)
            hop_length = 512
            frame_duration = hop_length / sr

            music_mask = contrast_mean > threshold * np.max(contrast_mean)

            # Find continuous segments
            segments = []
            in_music = False
            start_time = 0

            for i, is_music in enumerate(music_mask):
                time = i * frame_duration

                if is_music and not in_music:
                    start_time = time
                    in_music = True
                elif not is_music and in_music:
                    segments.append((start_time, time))
                    in_music = False

            # Add final segment if still in music
            if in_music:
                segments.append((start_time, len(y) / sr))

            logger.info(f"Found {len(segments)} music segments")

            return segments

        except Exception as e:
            logger.warning(f"Music detection failed: {e}")
            return []

    def compute_loudness_over_time(
        self,
        audio_path: Path,
        frame_length: float = 0.1
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute loudness (RMS energy) over time

        Args:
            audio_path: Path to audio file
            frame_length: Frame length in seconds

        Returns:
            Tuple of (time_points, loudness_values)
        """
        try:
            import librosa

            y, sr = librosa.load(str(audio_path), sr=None)

            # Compute RMS energy
            hop_length = int(frame_length * sr)
            rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]

            # Time points
            times = librosa.frames_to_time(
                np.arange(len(rms)),
                sr=sr,
                hop_length=hop_length
            )

            return times, rms

        except Exception as e:
            logger.warning(f"Loudness computation failed: {e}")
            return np.array([]), np.array([])

    def extract_pitch_contour(
        self,
        audio_path: Path
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract pitch contour from audio

        Args:
            audio_path: Path to audio file

        Returns:
            Tuple of (time_points, pitch_values)
        """
        try:
            import librosa

            y, sr = librosa.load(str(audio_path), sr=None)

            # Extract pitch using pYIN algorithm
            f0, voiced_flag, voiced_probs = librosa.pyin(
                y,
                fmin=librosa.note_to_hz('C2'),
                fmax=librosa.note_to_hz('C7')
            )

            # Time points
            times = librosa.times_like(f0, sr=sr)

            # Filter out unvoiced segments
            f0_voiced = np.where(voiced_flag, f0, np.nan)

            return times, f0_voiced

        except Exception as e:
            logger.warning(f"Pitch extraction failed: {e}")
            return np.array([]), np.array([])

    def save_features(
        self,
        features: AudioFeatures,
        output_path: Path
    ):
        """
        Save extracted features to file

        Args:
            features: AudioFeatures object
            output_path: Output file path
        """
        import json

        logger.info(f"Saving features to {output_path}")

        data = {
            'duration': features.duration,
            'rms_energy': features.rms_energy,
            'zero_crossing_rate': features.zero_crossing_rate,
            'spectral_centroid_mean': features.spectral_centroid_mean,
            'spectral_centroid_std': features.spectral_centroid_std,
            'spectral_rolloff_mean': features.spectral_rolloff_mean,
            'spectral_rolloff_std': features.spectral_rolloff_std,
            'spectral_bandwidth_mean': features.spectral_bandwidth_mean,
            'spectral_bandwidth_std': features.spectral_bandwidth_std,
            'tempo': features.tempo,
            'sample_rate': features.sample_rate,
            'num_channels': features.num_channels
        }

        # Add MFCC if available
        if features.mfcc_mean is not None:
            data['mfcc_mean'] = features.mfcc_mean.tolist()
        if features.mfcc_std is not None:
            data['mfcc_std'] = features.mfcc_std.tolist()

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Features saved to {output_path}")


def extract_audio_features(
    audio_path: Path,
    include_mfcc: bool = True
) -> AudioFeatures:
    """
    Convenience function to extract audio features

    Args:
        audio_path: Path to audio file
        include_mfcc: Include MFCC features

    Returns:
        AudioFeatures object
    """
    extractor = AudioFeatureExtractor()
    return extractor.extract_features(audio_path, include_mfcc=include_mfcc)
