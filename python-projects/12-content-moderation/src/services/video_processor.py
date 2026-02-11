"""
Video Processing Service for Content Moderation.

Handles frame extraction, video thumbnails, and frame management.
"""

import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import List, Tuple, Optional, Dict

logging.basicConfig(level=logging.INFO)


class VideoProcessor:
    """Process video files for moderation."""

    # Supported video formats
    SUPPORTED_FORMATS = {'.mp4', '.mov', '.avi', '.webm'}

    def __init__(
        self,
        frames_per_second: float = 1.0,
        max_frames: int = 100,
        thumbnail_time: float = 5.0,
        temp_dir: Optional[str] = None
    ):
        """
        Initialize video processor.

        Args:
            frames_per_second: Frame extraction rate (default 1 fps)
            max_frames: Maximum frames to extract
            thumbnail_time: Time in seconds to extract thumbnail
            temp_dir: Directory for temporary frames
        """
        self.fps = frames_per_second
        self.max_frames = max_frames
        self.thumbnail_time = thumbnail_time
        self.temp_dir = Path(temp_dir or tempfile.gettempdir())

        # Check ffmpeg availability
        self.ffmpeg_available = self._check_ffmpeg()

        logging.info(f"VideoProcessor initialized: fps={self.fps}, max_frames={self.max_frames}, ffmpeg={self.ffmpeg_available}")

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
        import subprocess

        try:
            import ffmpeg
            # Test ffmpeg by checking if it's in PATH
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (ImportError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logging.warning(f"ffmpeg not available: {e}. Video processing will be limited.")
            return False

    def extract_frames(
        self,
        video_path: str,
        output_dir: Optional[str] = None
    ) -> Tuple[bool, List[str], Optional[str]]:
        """
        Extract frames from video.

        Args:
            video_path: Path to video file
            output_dir: Directory to save frames (uses temp if None)

        Returns:
            Tuple of (success, frame_paths, error_message)
        """
        if not self.ffmpeg_available:
            return False, [], "ffmpeg not available"

        # Validate video file
        video_path = Path(video_path)
        if not video_path.exists():
            return False, [], f"Video file not found: {video_path}"

        if video_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            return False, [], f"Unsupported format: {video_path.suffix}"

        # Create output directory
        if output_dir is None:
            output_dir = self.temp_dir / f"frames_{uuid.uuid4().hex[:8]}"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            import ffmpeg

            # Get video duration
            probe = ffmpeg.probe(str(video_path))
            video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
            duration = float(probe['format']['duration'])

            logging.info(f"Video duration: {duration:.2f}s")

            # Calculate frame interval
            frame_interval = 1.0 / self.fps
            num_frames = min(int(duration * self.fps), self.max_frames)

            logging.info(f"Extracting {num_frames} frames at {self.fps} fps")

            # Extract frames using ffmpeg
            frame_paths = []
            for i in range(num_frames):
                time_offset = i * frame_interval
                if time_offset >= duration:
                    break

                output_path = output_dir / f"frame_{i:04d}.jpg"

                try:
                    (
                        ffmpeg
                        .input(str(video_path), ss=time_offset)
                        .filter('scale', 800, -1)  # Resize to 800px width
                        .output(str(output_path), vframes=1, format='image2', vcodec='mjpeg')
                        .overwrite_output()
                        .run(capture_stdout=True, capture_stderr=True, quiet=True)
                    )

                    if output_path.exists():
                        frame_paths.append(str(output_path))

                except ffmpeg.Error as e:
                    logging.warning(f"Failed to extract frame {i}: {e.stderr.decode()}")
                    continue

            if not frame_paths:
                return False, [], "No frames extracted"

            logging.info(f"Extracted {len(frame_paths)} frames")
            return True, frame_paths, None

        except Exception as e:
            logging.error(f"Frame extraction failed: {e}")
            return False, [], f"Frame extraction error: {str(e)}"

    def generate_video_thumbnail(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        time_offset: Optional[float] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Generate thumbnail from video.

        Args:
            video_path: Path to video file
            output_path: Path for thumbnail (auto-generated if None)
            time_offset: Time in seconds (uses self.thumbnail_time if None)

        Returns:
            Tuple of (success, thumbnail_path, error_message)
        """
        if not self.ffmpeg_available:
            return False, None, "ffmpeg not available"

        video_path = Path(video_path)
        if not video_path.exists():
            return False, None, f"Video file not found: {video_path}"

        # Generate output path if not provided
        if output_path is None:
            thumbnail_dir = Path(os.getenv('THUMBNAIL_DIR', './data/thumbnails'))
            thumbnail_dir.mkdir(parents=True, exist_ok=True)
            output_path = thumbnail_dir / f"thumb_{video_path.stem}.jpg"
        else:
            output_path = Path(output_path)

        # Use default time offset if not provided
        if time_offset is None:
            time_offset = self.thumbnail_time

        try:
            import ffmpeg

            # Get video duration to ensure we don't exceed it
            probe = ffmpeg.probe(str(video_path))
            duration = float(probe['format']['duration'])

            # Adjust time offset if it exceeds duration
            time_offset = min(time_offset, duration - 0.1)

            # Extract single frame at specified time
            (
                ffmpeg
                .input(str(video_path), ss=time_offset)
                .filter('scale', 300, -1)  # Resize to 300px width
                .output(str(output_path), vframes=1, format='image2', vcodec='mjpeg')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True, quiet=True)
            )

            if output_path.exists():
                logging.info(f"Thumbnail generated: {output_path}")
                return True, str(output_path), None
            else:
                return False, None, "Thumbnail file not created"

        except Exception as e:
            logging.error(f"Thumbnail generation failed: {e}")
            return False, None, f"Thumbnail generation error: {str(e)}"

    def get_video_info(self, video_path: str) -> Optional[Dict]:
        """
        Get video metadata.

        Args:
            video_path: Path to video file

        Returns:
            Dictionary with video info or None if error
        """
        if not self.ffmpeg_available:
            logging.warning("ffmpeg not available, cannot get video info")
            return None

        try:
            import ffmpeg

            probe = ffmpeg.probe(str(video_path))
            video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
            format_info = probe['format']

            return {
                'duration': float(format_info.get('duration', 0)),
                'width': int(video_info.get('width', 0)),
                'height': int(video_info.get('height', 0)),
                'codec': video_info.get('codec_name', 'unknown'),
                'fps': eval(video_info.get('r_frame_rate', '0/1')),
                'size_bytes': int(format_info.get('size', 0)),
                'format': format_info.get('format_name', 'unknown')
            }

        except Exception as e:
            logging.error(f"Failed to get video info for {video_path}: {e}")
            return None

    def cleanup_frames(self, frame_paths: List[str]) -> bool:
        """
        Delete extracted frames.

        Args:
            frame_paths: List of frame file paths

        Returns:
            True if all frames deleted successfully
        """
        success = True
        for frame_path in frame_paths:
            try:
                path = Path(frame_path)
                if path.exists():
                    path.unlink()
            except Exception as e:
                logging.error(f"Failed to delete frame {frame_path}: {e}")
                success = False

        # Try to remove parent directory if empty
        if frame_paths:
            try:
                parent_dir = Path(frame_paths[0]).parent
                if parent_dir.exists() and not any(parent_dir.iterdir()):
                    parent_dir.rmdir()
                    logging.info(f"Removed empty directory: {parent_dir}")
            except Exception as e:
                logging.debug(f"Could not remove directory: {e}")

        return success

    @staticmethod
    def is_video_file(filename: str) -> bool:
        """Check if filename is a video."""
        ext = Path(filename).suffix.lower()
        return ext in VideoProcessor.SUPPORTED_FORMATS


class VideoProcessorFallback:
    """
    Fallback video processor when ffmpeg is not available.

    Returns placeholder data for development/testing.
    """

    def __init__(
        self,
        frames_per_second: float = 1.0,
        max_frames: int = 100,
        thumbnail_time: float = 5.0,
        temp_dir: Optional[str] = None
    ):
        """Initialize fallback processor."""
        logging.warning("Using fallback video processor (ffmpeg not available)")
        self.ffmpeg_available = False
        self.fps = frames_per_second
        self.max_frames = max_frames
        self.thumbnail_time = thumbnail_time
        self.temp_dir = Path(temp_dir or tempfile.gettempdir())

    def extract_frames(self, video_path: str, output_dir: Optional[str] = None) -> Tuple[bool, List[str], Optional[str]]:
        """Return error for frame extraction."""
        return False, [], "ffmpeg not available - video processing disabled"

    def generate_video_thumbnail(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        time_offset: Optional[float] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Return error for thumbnail generation."""
        return False, None, "ffmpeg not available - video thumbnails disabled"

    def get_video_info(self, video_path: str) -> Optional[Dict]:
        """Return None for video info."""
        return None

    def cleanup_frames(self, frame_paths: List[str]) -> bool:
        """No-op cleanup."""
        return True

    @staticmethod
    def is_video_file(filename: str) -> bool:
        """Check if filename is a video."""
        ext = Path(filename).suffix.lower()
        return ext in {'.mp4', '.mov', '.avi', '.webm'}


# Global video processor instance
_video_processor_instance = None


def get_video_processor(
    frames_per_second: Optional[float] = None,
    max_frames: Optional[int] = None
) -> VideoProcessor:
    """
    Get global VideoProcessor instance.

    Args:
        frames_per_second: Optional fps override
        max_frames: Optional max frames override

    Returns:
        VideoProcessor instance
    """
    global _video_processor_instance

    # Reinitialize if parameters changed
    if _video_processor_instance is None or \
       (frames_per_second and frames_per_second != getattr(_video_processor_instance, 'fps', None)) or \
       (max_frames and max_frames != getattr(_video_processor_instance, 'max_frames', None)):
        try:
            _video_processor_instance = VideoProcessor(
                frames_per_second=frames_per_second or float(os.getenv('VIDEO_FPS', '1.0')),
                max_frames=max_frames or int(os.getenv('VIDEO_MAX_FRAMES', '100'))
            )
        except Exception as e:
            logging.error(f"Failed to initialize VideoProcessor: {e}")
            _video_processor_instance = VideoProcessorFallback()

    return _video_processor_instance
