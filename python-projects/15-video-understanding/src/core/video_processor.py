"""
Video processing utilities for frame and audio extraction using ffmpeg
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProcessingProgress:
    """Progress information for video processing"""
    stage: str
    current: int
    total: int
    percentage: float
    message: str


class VideoProcessingError(Exception):
    """Exception raised when video processing fails"""
    pass


class VideoProcessor:
    """
    Process videos using ffmpeg for frame extraction and audio processing
    """

    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe",
        progress_callback: Optional[Callable[[ProcessingProgress], None]] = None
    ):
        """
        Initialize video processor

        Args:
            ffmpeg_path: Path to ffmpeg executable
            ffprobe_path: Path to ffprobe executable
            progress_callback: Optional callback for progress updates
        """
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.progress_callback = progress_callback

    def extract_frames(
        self,
        video_path: Path,
        output_dir: Path,
        fps: float = 1.0,
        quality: int = 2,
        format: str = "jpg",
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        filename_pattern: str = "frame_%06d.jpg"
    ) -> List[Path]:
        """
        Extract frames from video at specified FPS

        Args:
            video_path: Path to input video
            output_dir: Directory to save frames
            fps: Frames per second to extract (default 1.0)
            quality: JPEG quality (1-31, lower is better, default 2)
            format: Output format (jpg, png)
            start_time: Optional start time in seconds
            end_time: Optional end time in seconds
            filename_pattern: Pattern for output filenames

        Returns:
            List of paths to extracted frames

        Raises:
            VideoProcessingError: If extraction fails
        """
        if not video_path.exists():
            raise VideoProcessingError(f"Video file not found: {video_path}")

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build ffmpeg command
        output_path = output_dir / filename_pattern

        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
        ]

        # Add time range if specified
        if start_time is not None:
            cmd.extend(["-ss", str(start_time)])
        if end_time is not None:
            cmd.extend(["-to", str(end_time)])

        # Add frame extraction parameters
        cmd.extend([
            "-vf", f"fps={fps}",
            "-q:v", str(quality),
            str(output_path),
            "-hide_banner",
            "-loglevel", "error",
        ])

        # Report progress
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="frame_extraction",
                current=0,
                total=100,
                percentage=0.0,
                message=f"Extracting frames at {fps} FPS"
            ))

        try:
            logger.info(f"Extracting frames from {video_path} at {fps} FPS")
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )

            # Get list of extracted frames
            frames = sorted(output_dir.glob(f"frame_*.{format}"))

            # Report completion
            if self.progress_callback:
                self.progress_callback(ProcessingProgress(
                    stage="frame_extraction",
                    current=100,
                    total=100,
                    percentage=100.0,
                    message=f"Extracted {len(frames)} frames"
                ))

            logger.info(f"Extracted {len(frames)} frames to {output_dir}")
            return frames

        except subprocess.CalledProcessError as e:
            error_msg = f"Frame extraction failed: {e.stderr}"
            logger.error(error_msg)
            raise VideoProcessingError(error_msg) from e

    def extract_audio(
        self,
        video_path: Path,
        output_path: Path,
        format: str = "wav",
        sample_rate: int = 16000,
        channels: int = 1,
        bitrate: Optional[str] = None
    ) -> Path:
        """
        Extract audio from video

        Args:
            video_path: Path to input video
            output_path: Path to output audio file
            format: Audio format (wav, mp3, flac, etc.)
            sample_rate: Audio sample rate in Hz
            channels: Number of audio channels (1=mono, 2=stereo)
            bitrate: Optional audio bitrate (e.g., "128k")

        Returns:
            Path to extracted audio file

        Raises:
            VideoProcessingError: If extraction fails
        """
        if not video_path.exists():
            raise VideoProcessingError(f"Video file not found: {video_path}")

        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build ffmpeg command
        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-vn",  # No video
            "-acodec", "pcm_s16le" if format == "wav" else "libmp3lame",
            "-ar", str(sample_rate),
            "-ac", str(channels),
        ]

        if bitrate:
            cmd.extend(["-b:a", bitrate])

        cmd.extend([
            str(output_path),
            "-y",  # Overwrite output file
            "-hide_banner",
            "-loglevel", "error",
        ])

        # Report progress
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="audio_extraction",
                current=0,
                total=100,
                percentage=0.0,
                message="Extracting audio"
            ))

        try:
            logger.info(f"Extracting audio from {video_path}")
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            # Report completion
            if self.progress_callback:
                self.progress_callback(ProcessingProgress(
                    stage="audio_extraction",
                    current=100,
                    total=100,
                    percentage=100.0,
                    message="Audio extraction complete"
                ))

            logger.info(f"Extracted audio to {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            error_msg = f"Audio extraction failed: {e.stderr}"
            logger.error(error_msg)
            raise VideoProcessingError(error_msg) from e

    def get_video_duration(self, video_path: Path) -> float:
        """
        Get video duration in seconds using ffprobe

        Args:
            video_path: Path to video file

        Returns:
            Duration in seconds

        Raises:
            VideoProcessingError: If duration cannot be determined
        """
        if not video_path.exists():
            raise VideoProcessingError(f"Video file not found: {video_path}")

        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            duration = float(result.stdout.strip())
            return duration

        except (subprocess.CalledProcessError, ValueError) as e:
            error_msg = f"Failed to get video duration: {e}"
            logger.error(error_msg)
            raise VideoProcessingError(error_msg) from e

    def get_frame_count(self, video_path: Path) -> int:
        """
        Get total number of frames in video

        Args:
            video_path: Path to video file

        Returns:
            Total frame count

        Raises:
            VideoProcessingError: If frame count cannot be determined
        """
        if not video_path.exists():
            raise VideoProcessingError(f"Video file not found: {video_path}")

        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-count_packets",
            "-show_entries", "stream=nb_read_packets",
            "-of", "default=nokey=1:noprint_wrappers=1",
            str(video_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            frame_count = int(result.stdout.strip())
            return frame_count

        except (subprocess.CalledProcessError, ValueError) as e:
            error_msg = f"Failed to get frame count: {e}"
            logger.error(error_msg)
            raise VideoProcessingError(error_msg) from e

    def extract_single_frame(
        self,
        video_path: Path,
        output_path: Path,
        timestamp: float,
        quality: int = 2
    ) -> Path:
        """
        Extract a single frame at specific timestamp

        Args:
            video_path: Path to input video
            output_path: Path to output frame
            timestamp: Time in seconds
            quality: JPEG quality (1-31, lower is better)

        Returns:
            Path to extracted frame

        Raises:
            VideoProcessingError: If extraction fails
        """
        if not video_path.exists():
            raise VideoProcessingError(f"Video file not found: {video_path}")

        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path,
            "-ss", str(timestamp),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", str(quality),
            str(output_path),
            "-y",
            "-hide_banner",
            "-loglevel", "error",
        ]

        try:
            logger.debug(f"Extracting frame at {timestamp}s from {video_path}")
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.debug(f"Extracted frame to {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            error_msg = f"Single frame extraction failed: {e.stderr}"
            logger.error(error_msg)
            raise VideoProcessingError(error_msg) from e

    def create_clip(
        self,
        video_path: Path,
        output_path: Path,
        start_time: float,
        end_time: float,
        copy_codec: bool = False
    ) -> Path:
        """
        Create a video clip from timestamp range

        Args:
            video_path: Path to input video
            output_path: Path to output clip
            start_time: Start time in seconds
            end_time: End time in seconds
            copy_codec: If True, copy codecs without re-encoding (faster)

        Returns:
            Path to created clip

        Raises:
            VideoProcessingError: If clip creation fails
        """
        if not video_path.exists():
            raise VideoProcessingError(f"Video file not found: {video_path}")

        if start_time >= end_time:
            raise VideoProcessingError("Start time must be less than end time")

        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)

        duration = end_time - start_time

        cmd = [
            self.ffmpeg_path,
            "-ss", str(start_time),
            "-i", str(video_path),
            "-t", str(duration),
        ]

        if copy_codec:
            cmd.extend(["-c", "copy"])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "fast",
            ])

        cmd.extend([
            str(output_path),
            "-y",
            "-hide_banner",
            "-loglevel", "error",
        ])

        # Report progress
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="clip_creation",
                current=0,
                total=100,
                percentage=0.0,
                message=f"Creating clip ({start_time}s - {end_time}s)"
            ))

        try:
            logger.info(f"Creating clip from {start_time}s to {end_time}s")
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            # Report completion
            if self.progress_callback:
                self.progress_callback(ProcessingProgress(
                    stage="clip_creation",
                    current=100,
                    total=100,
                    percentage=100.0,
                    message="Clip created"
                ))

            logger.info(f"Created clip at {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            error_msg = f"Clip creation failed: {e.stderr}"
            logger.error(error_msg)
            raise VideoProcessingError(error_msg) from e


def create_video_processor(
    ffmpeg_path: Optional[str] = None,
    ffprobe_path: Optional[str] = None,
    progress_callback: Optional[Callable[[ProcessingProgress], None]] = None
) -> VideoProcessor:
    """
    Convenience function to create VideoProcessor instance

    Args:
        ffmpeg_path: Optional path to ffmpeg executable
        ffprobe_path: Optional path to ffprobe executable
        progress_callback: Optional callback for progress updates

    Returns:
        VideoProcessor instance
    """
    from src.core.config import settings

    return VideoProcessor(
        ffmpeg_path=ffmpeg_path or settings.ffmpeg_path,
        ffprobe_path=ffprobe_path or settings.ffprobe_path,
        progress_callback=progress_callback
    )
