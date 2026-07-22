"""
Audio processing service
Handles audio extraction, format conversion, and audio analysis
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import tempfile
import subprocess

logger = logging.getLogger(__name__)


class AudioProcessor:
    """
    Audio processing service for video files
    Extracts, converts, and analyzes audio from videos
    """

    def __init__(self):
        """Initialize audio processor"""
        self._verify_ffmpeg()

    def _verify_ffmpeg(self):
        """Verify ffmpeg is available"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("ffmpeg not found. Audio processing may not work correctly.")

    def extract_audio(
        self,
        video_path: Path,
        output_path: Optional[Path] = None,
        format: str = "wav",
        sample_rate: int = 16000,
        channels: int = 1,
        bitrate: Optional[str] = None,
        start_time: Optional[float] = None,
        duration: Optional[float] = None
    ) -> Path:
        """
        Extract audio from video file

        Args:
            video_path: Path to video file
            output_path: Optional output path (temp file if None)
            format: Audio format (wav, mp3, flac, etc.)
            sample_rate: Sample rate in Hz
            channels: Number of audio channels (1=mono, 2=stereo)
            bitrate: Audio bitrate (e.g., "128k")
            start_time: Optional start time in seconds
            duration: Optional duration in seconds

        Returns:
            Path to extracted audio file

        Raises:
            ValueError: If video not found
            RuntimeError: If extraction fails
        """
        if not video_path.exists():
            raise ValueError(f"Video not found: {video_path}")

        # Create output path if not provided
        if output_path is None:
            temp_dir = Path(tempfile.gettempdir())
            output_path = temp_dir / f"{video_path.stem}_audio.{format}"

        logger.info(
            f"Extracting audio from {video_path} to {output_path} "
            f"(format={format}, sr={sample_rate}, channels={channels})"
        )

        # Build ffmpeg command
        cmd = ['ffmpeg', '-i', str(video_path)]

        # Add time range if specified
        if start_time is not None:
            cmd.extend(['-ss', str(start_time)])
        if duration is not None:
            cmd.extend(['-t', str(duration)])

        # Audio settings
        cmd.extend([
            '-vn',  # No video
            '-acodec', 'pcm_s16le' if format == 'wav' else 'libmp3lame',
            '-ar', str(sample_rate),
            '-ac', str(channels)
        ])

        if bitrate:
            cmd.extend(['-ab', bitrate])

        cmd.extend(['-y', str(output_path)])

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            logger.info(f"Audio extracted successfully to {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Audio extraction failed: {error_msg}") from e

    def convert_audio_format(
        self,
        input_path: Path,
        output_path: Path,
        format: str = "wav",
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None
    ) -> Path:
        """
        Convert audio file to different format

        Args:
            input_path: Input audio file
            output_path: Output audio file
            format: Target format
            sample_rate: Optional sample rate
            channels: Optional number of channels

        Returns:
            Path to converted audio file
        """
        if not input_path.exists():
            raise ValueError(f"Audio file not found: {input_path}")

        logger.info(f"Converting {input_path} to {format} format")

        cmd = ['ffmpeg', '-i', str(input_path)]

        if sample_rate:
            cmd.extend(['-ar', str(sample_rate)])
        if channels:
            cmd.extend(['-ac', str(channels)])

        cmd.extend(['-y', str(output_path)])

        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            logger.info(f"Audio converted to {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Audio conversion failed: {error_msg}") from e

    def get_audio_info(self, audio_path: Path) -> Dict[str, any]:
        """
        Get audio file information

        Args:
            audio_path: Path to audio file

        Returns:
            Dictionary with audio info
        """
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_path}")

        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(audio_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            import json
            data = json.loads(result.stdout.decode())

            # Extract audio stream info
            audio_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'audio':
                    audio_stream = stream
                    break

            if not audio_stream:
                raise RuntimeError("No audio stream found")

            info = {
                'duration': float(data.get('format', {}).get('duration', 0)),
                'sample_rate': int(audio_stream.get('sample_rate', 0)),
                'channels': int(audio_stream.get('channels', 0)),
                'codec': audio_stream.get('codec_name', 'unknown'),
                'bitrate': int(data.get('format', {}).get('bit_rate', 0)),
                'size': int(data.get('format', {}).get('size', 0))
            }

            return info

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Failed to get audio info: {error_msg}") from e

    def split_audio(
        self,
        audio_path: Path,
        segments: List[Tuple[float, float]],
        output_dir: Path
    ) -> List[Path]:
        """
        Split audio into segments

        Args:
            audio_path: Path to audio file
            segments: List of (start_time, end_time) tuples
            output_dir: Output directory for segments

        Returns:
            List of paths to audio segments
        """
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_path}")

        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Splitting audio into {len(segments)} segments")

        segment_paths = []

        for idx, (start_time, end_time) in enumerate(segments):
            duration = end_time - start_time

            output_path = output_dir / f"segment_{idx:04d}.wav"

            cmd = [
                'ffmpeg',
                '-i', str(audio_path),
                '-ss', str(start_time),
                '-t', str(duration),
                '-acodec', 'copy',
                '-y', str(output_path)
            ]

            try:
                subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True
                )

                segment_paths.append(output_path)

            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to extract segment {idx}: {e}")

        logger.info(f"Created {len(segment_paths)} audio segments")

        return segment_paths

    def normalize_audio(
        self,
        input_path: Path,
        output_path: Path,
        target_level: float = -20.0
    ) -> Path:
        """
        Normalize audio volume

        Args:
            input_path: Input audio file
            output_path: Output audio file
            target_level: Target level in dB

        Returns:
            Path to normalized audio
        """
        if not input_path.exists():
            raise ValueError(f"Audio file not found: {input_path}")

        logger.info(f"Normalizing audio to {target_level} dB")

        cmd = [
            'ffmpeg',
            '-i', str(input_path),
            '-af', f'loudnorm=I={target_level}',
            '-y', str(output_path)
        ]

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            logger.info(f"Audio normalized to {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Audio normalization failed: {error_msg}") from e

    def reduce_noise(
        self,
        input_path: Path,
        output_path: Path,
        noise_reduction: float = 0.21
    ) -> Path:
        """
        Apply noise reduction to audio

        Args:
            input_path: Input audio file
            output_path: Output audio file
            noise_reduction: Noise reduction amount (0-1)

        Returns:
            Path to processed audio
        """
        if not input_path.exists():
            raise ValueError(f"Audio file not found: {input_path}")

        logger.info(f"Applying noise reduction (amount={noise_reduction})")

        # Use afftdn filter for noise reduction
        cmd = [
            'ffmpeg',
            '-i', str(input_path),
            '-af', f'afftdn=nf={noise_reduction}',
            '-y', str(output_path)
        ]

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            logger.info(f"Noise reduction applied to {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Noise reduction failed: {error_msg}") from e

    def merge_audio_files(
        self,
        audio_paths: List[Path],
        output_path: Path
    ) -> Path:
        """
        Merge multiple audio files

        Args:
            audio_paths: List of audio files to merge
            output_path: Output audio file

        Returns:
            Path to merged audio
        """
        if not audio_paths:
            raise ValueError("No audio files provided")

        logger.info(f"Merging {len(audio_paths)} audio files")

        # Create concat file
        concat_file = Path(tempfile.gettempdir()) / "concat_list.txt"

        with open(concat_file, 'w') as f:
            for path in audio_paths:
                f.write(f"file '{path.absolute()}'\n")

        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',
            '-y', str(output_path)
        ]

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            concat_file.unlink()  # Clean up
            logger.info(f"Audio files merged to {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Audio merge failed: {error_msg}") from e

    def extract_audio_features(self, audio_path: Path) -> Dict[str, any]:
        """
        Extract basic audio features

        Args:
            audio_path: Path to audio file

        Returns:
            Dictionary of audio features
        """
        try:
            import librosa
            import numpy as np

            # Load audio
            y, sr = librosa.load(str(audio_path), sr=None)

            # Extract features
            features = {
                'duration': float(len(y) / sr),
                'sample_rate': int(sr),
                'rms_energy': float(np.sqrt(np.mean(y**2))),
                'zero_crossing_rate': float(np.mean(librosa.feature.zero_crossing_rate(y))),
            }

            # Spectral features
            spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            features['spectral_centroid_mean'] = float(np.mean(spectral_centroid))
            features['spectral_centroid_std'] = float(np.std(spectral_centroid))

            # Tempo
            try:
                tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                features['tempo'] = float(tempo)
            except:
                features['tempo'] = 0.0

            return features

        except ImportError:
            logger.warning("librosa not available for feature extraction")
            return self.get_audio_info(audio_path)

    def detect_silence(
        self,
        audio_path: Path,
        silence_threshold: float = -40.0,
        min_silence_duration: float = 0.5
    ) -> List[Tuple[float, float]]:
        """
        Detect silence periods in audio

        Args:
            audio_path: Path to audio file
            silence_threshold: Silence threshold in dB
            min_silence_duration: Minimum silence duration in seconds

        Returns:
            List of (start_time, end_time) tuples for silence periods
        """
        try:
            import librosa
            import numpy as np

            # Load audio
            y, sr = librosa.load(str(audio_path), sr=None)

            # Convert to dB
            db = librosa.amplitude_to_db(np.abs(y), ref=np.max)

            # Find silence frames
            hop_length = 512
            frame_duration = hop_length / sr

            silence_mask = db < silence_threshold

            # Find continuous silence periods
            silence_periods = []
            in_silence = False
            silence_start = 0

            for i, is_silent in enumerate(silence_mask):
                if is_silent and not in_silence:
                    silence_start = i * frame_duration
                    in_silence = True
                elif not is_silent and in_silence:
                    silence_end = i * frame_duration
                    duration = silence_end - silence_start

                    if duration >= min_silence_duration:
                        silence_periods.append((silence_start, silence_end))

                    in_silence = False

            return silence_periods

        except ImportError:
            logger.warning("librosa not available for silence detection")
            return []


def extract_audio_from_video(
    video_path: Path,
    output_path: Optional[Path] = None,
    sample_rate: int = 16000
) -> Path:
    """
    Convenience function to extract audio from video

    Args:
        video_path: Path to video file
        output_path: Optional output path
        sample_rate: Sample rate in Hz

    Returns:
        Path to extracted audio
    """
    processor = AudioProcessor()
    return processor.extract_audio(
        video_path,
        output_path=output_path,
        sample_rate=sample_rate
    )
