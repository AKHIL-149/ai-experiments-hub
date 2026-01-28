"""Video Processor - Extract audio from video files - Phase 5"""

import subprocess
import os
import logging
from pathlib import Path
from typing import Optional, Dict
import tempfile

logger = logging.getLogger(__name__)


class VideoProcessor:
    """
    Process video files and extract audio for transcription.

    Supports: MP4, AVI, MOV, MKV, WebM, FLV, WMV
    """

    SUPPORTED_VIDEO_FORMATS = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.3gp']

    def __init__(self, temp_dir: str = './data/temp'):
        """
        Initialize Video Processor

        Args:
            temp_dir: Temporary directory for extracted audio
        """
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def is_video_file(self, file_path: str) -> bool:
        """
        Check if file is a supported video format

        Args:
            file_path: Path to file

        Returns:
            True if file is a supported video format
        """
        file_ext = Path(file_path).suffix.lower()
        return file_ext in self.SUPPORTED_VIDEO_FORMATS

    def extract_audio(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        audio_format: str = 'mp3',
        audio_bitrate: str = '192k',
        sample_rate: int = 44100
    ) -> str:
        """
        Extract audio from video file using ffmpeg

        Args:
            video_path: Path to video file
            output_path: Path to output audio file (optional, auto-generated if None)
            audio_format: Output audio format (mp3, wav, etc.)
            audio_bitrate: Audio bitrate (e.g., '192k')
            sample_rate: Audio sample rate in Hz

        Returns:
            Path to extracted audio file

        Raises:
            FileNotFoundError: If video file not found
            RuntimeError: If audio extraction fails
        """
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if not self.is_video_file(str(video_path)):
            raise ValueError(f"Unsupported video format: {video_path.suffix}")

        # Generate output path if not provided
        if output_path is None:
            output_filename = f"{video_path.stem}_audio.{audio_format}"
            output_path = self.temp_dir / output_filename
        else:
            output_path = Path(output_path)

        # Check if ffmpeg is available
        if not self._check_ffmpeg():
            raise RuntimeError("ffmpeg not found. Please install ffmpeg to extract audio from videos.")

        try:
            # ffmpeg command to extract audio
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-vn',  # No video
                '-acodec', 'libmp3lame' if audio_format == 'mp3' else 'pcm_s16le',
                '-ar', str(sample_rate),
                '-ab', audio_bitrate,
                '-y',  # Overwrite output file if exists
                str(output_path)
            ]

            logger.info(f"Extracting audio from {video_path.name}...")

            # Run ffmpeg
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=600  # 10 minute timeout
            )

            if result.returncode != 0:
                error_msg = result.stderr.decode('utf-8', errors='ignore')
                raise RuntimeError(f"ffmpeg failed: {error_msg}")

            if not output_path.exists():
                raise RuntimeError(f"Audio extraction failed: output file not created")

            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"Audio extracted successfully: {output_path.name} ({file_size_mb:.2f} MB)")

            return str(output_path)

        except subprocess.TimeoutExpired:
            raise RuntimeError("Audio extraction timed out (max 10 minutes)")
        except Exception as e:
            # Cleanup on error
            if output_path and output_path.exists():
                output_path.unlink()
            raise RuntimeError(f"Audio extraction failed: {str(e)}")

    def get_video_info(self, video_path: str) -> Dict:
        """
        Get video file information using ffprobe

        Args:
            video_path: Path to video file

        Returns:
            Dictionary with video information
        """
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        try:
            # Use ffprobe to get video info
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(video_path)
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30
            )

            if result.returncode != 0:
                logger.warning(f"Failed to get video info for {video_path.name}")
                return self._get_basic_info(video_path)

            import json
            info = json.loads(result.stdout.decode('utf-8'))

            # Extract relevant information
            format_info = info.get('format', {})
            video_stream = next(
                (s for s in info.get('streams', []) if s.get('codec_type') == 'video'),
                None
            )
            audio_stream = next(
                (s for s in info.get('streams', []) if s.get('codec_type') == 'audio'),
                None
            )

            return {
                'filename': video_path.name,
                'format': format_info.get('format_name', 'unknown'),
                'duration_seconds': float(format_info.get('duration', 0)),
                'file_size_mb': float(format_info.get('size', 0)) / (1024 * 1024),
                'bitrate': int(format_info.get('bit_rate', 0)) if format_info.get('bit_rate') else None,
                'has_video': video_stream is not None,
                'has_audio': audio_stream is not None,
                'video_codec': video_stream.get('codec_name') if video_stream else None,
                'audio_codec': audio_stream.get('codec_name') if audio_stream else None,
                'width': int(video_stream.get('width', 0)) if video_stream else None,
                'height': int(video_stream.get('height', 0)) if video_stream else None
            }

        except Exception as e:
            logger.error(f"Error getting video info: {str(e)}")
            return self._get_basic_info(video_path)

    def _get_basic_info(self, video_path: Path) -> Dict:
        """Get basic file information without ffprobe"""
        return {
            'filename': video_path.name,
            'format': video_path.suffix.lstrip('.'),
            'file_size_mb': video_path.stat().st_size / (1024 * 1024),
            'duration_seconds': None,
            'has_video': True,
            'has_audio': None
        }

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return False

    def cleanup_temp_files(self, max_age_hours: int = 24):
        """
        Clean up old temporary audio files

        Args:
            max_age_hours: Maximum age of files to keep (in hours)
        """
        import time

        if not self.temp_dir.exists():
            return

        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        cleaned = 0

        for file_path in self.temp_dir.glob('*_audio.*'):
            try:
                file_age = current_time - file_path.stat().st_mtime
                if file_age > max_age_seconds:
                    file_path.unlink()
                    cleaned += 1
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old temporary audio files")
