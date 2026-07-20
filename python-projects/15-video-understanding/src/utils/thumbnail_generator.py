"""
Thumbnail generation utilities for video files
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

from src.core.config import settings

logger = logging.getLogger(__name__)


class ThumbnailGenerator:
    """
    Generates thumbnails from video files at specified timestamps
    """
    
    # Default thumbnail dimensions
    DEFAULT_WIDTH = 1280
    DEFAULT_HEIGHT = 720
    DEFAULT_QUALITY = 85  # JPEG quality (1-100)
    
    def __init__(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        quality: int = DEFAULT_QUALITY
    ):
        """
        Initialize thumbnail generator
        
        Args:
            width: Thumbnail width (maintains aspect ratio if height not specified)
            height: Thumbnail height (maintains aspect ratio if width not specified)
            quality: JPEG quality (1-100)
        """
        self.width = width or self.DEFAULT_WIDTH
        self.height = height or self.DEFAULT_HEIGHT
        self.quality = max(1, min(100, quality))
    
    def generate(
        self,
        video_path: Path,
        output_path: Path,
        timestamp: Optional[float] = None,
    ) -> Path:
        """
        Generate thumbnail from video
        
        Args:
            video_path: Path to video file
            output_path: Path for output thumbnail
            timestamp: Timestamp in seconds (None for middle frame)
            
        Returns:
            Path to generated thumbnail
            
        Raises:
            ValueError: If video file not found or invalid
            RuntimeError: If thumbnail generation fails
        """
        if not video_path.exists():
            raise ValueError(f"Video file not found: {video_path}")
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # If timestamp not specified, use middle of video
        if timestamp is None:
            timestamp = self._get_middle_timestamp(video_path)
        
        try:
            import ffmpeg
            
            logger.info(
                f"Generating thumbnail from {video_path.name} "
                f"at {timestamp:.2f}s"
            )
            
            # Extract frame at timestamp
            stream = ffmpeg.input(str(video_path), ss=timestamp)
            
            # Apply scaling
            stream = ffmpeg.filter(stream, 'scale', self.width, self.height)
            
            # Output as JPEG
            stream = ffmpeg.output(
                stream,
                str(output_path),
                vframes=1,
                format='image2',
                vcodec='mjpeg',
                qscale=self._quality_to_qscale(self.quality)
            )
            
            # Run ffmpeg
            ffmpeg.run(stream, capture_stdout=True, capture_stderr=True, overwrite_output=True)
            
            if not output_path.exists():
                raise RuntimeError("Thumbnail file not created")
            
            logger.info(f"Thumbnail generated: {output_path}")
            return output_path
            
        except ImportError:
            raise RuntimeError("ffmpeg-python not installed")
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Failed to generate thumbnail: {error_msg}") from e
        except Exception as e:
            raise RuntimeError(f"Thumbnail generation failed: {e}") from e
    
    def generate_multiple(
        self,
        video_path: Path,
        output_dir: Path,
        count: int = 5,
        prefix: str = "thumb"
    ) -> list[Path]:
        """
        Generate multiple thumbnails at evenly spaced intervals
        
        Args:
            video_path: Path to video file
            output_dir: Directory for output thumbnails
            count: Number of thumbnails to generate
            prefix: Filename prefix for thumbnails
            
        Returns:
            List of paths to generated thumbnails
        """
        if count < 1:
            raise ValueError("Count must be at least 1")
        
        # Get video duration
        duration = self._get_video_duration(video_path)
        
        if duration <= 0:
            raise ValueError("Invalid video duration")
        
        # Calculate timestamps
        if count == 1:
            timestamps = [duration / 2]
        else:
            # Evenly spaced, avoiding very start and end
            step = duration / (count + 1)
            timestamps = [step * (i + 1) for i in range(count)]
        
        # Generate thumbnails
        thumbnails = []
        for i, timestamp in enumerate(timestamps):
            output_path = output_dir / f"{prefix}_{i:03d}.jpg"
            try:
                thumb_path = self.generate(video_path, output_path, timestamp)
                thumbnails.append(thumb_path)
            except Exception as e:
                logger.error(f"Failed to generate thumbnail {i}: {e}")
        
        return thumbnails
    
    def generate_grid(
        self,
        video_path: Path,
        output_path: Path,
        rows: int = 3,
        cols: int = 4
    ) -> Path:
        """
        Generate a grid of thumbnails (contact sheet)
        
        Args:
            video_path: Path to video file
            output_path: Path for output grid image
            rows: Number of rows in grid
            cols: Number of columns in grid
            
        Returns:
            Path to generated grid image
        """
        import subprocess
        
        count = rows * cols
        
        try:
            # Use ffmpeg to create thumbnail grid
            cmd = [
                settings.ffmpeg_path,
                '-i', str(video_path),
                '-vf', f'select=not(mod(n\\,{count})),scale={self.width}:{self.height},tile={cols}x{rows}',
                '-frames:v', '1',
                '-y',
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg error: {result.stderr}")
            
            logger.info(f"Thumbnail grid generated: {output_path}")
            return output_path
            
        except FileNotFoundError:
            raise RuntimeError(f"ffmpeg not found at: {settings.ffmpeg_path}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Thumbnail grid generation timed out")
        except Exception as e:
            raise RuntimeError(f"Failed to generate thumbnail grid: {e}") from e
    
    def _get_video_duration(self, video_path: Path) -> float:
        """Get video duration in seconds"""
        try:
            import ffmpeg
            
            probe = ffmpeg.probe(str(video_path))
            duration = float(probe['format'].get('duration', 0))
            return duration
            
        except Exception as e:
            logger.error(f"Failed to get video duration: {e}")
            return 0
    
    def _get_middle_timestamp(self, video_path: Path) -> float:
        """Get timestamp for middle of video"""
        duration = self._get_video_duration(video_path)
        return duration / 2 if duration > 0 else 0
    
    @staticmethod
    def _quality_to_qscale(quality: int) -> int:
        """
        Convert quality percentage (1-100) to ffmpeg qscale (2-31)
        Lower qscale = higher quality
        """
        # Invert and scale: 100% quality = qscale 2, 1% quality = qscale 31
        return int(31 - (quality - 1) * 29 / 99)
    
    def set_dimensions(self, width: int, height: int):
        """Update thumbnail dimensions"""
        self.width = width
        self.height = height
    
    def set_quality(self, quality: int):
        """Update thumbnail quality (1-100)"""
        self.quality = max(1, min(100, quality))


def generate_thumbnail(
    video_path: Path,
    output_path: Path,
    timestamp: Optional[float] = None,
    width: int = ThumbnailGenerator.DEFAULT_WIDTH,
    height: int = ThumbnailGenerator.DEFAULT_HEIGHT
) -> Path:
    """
    Convenience function to generate a single thumbnail
    
    Args:
        video_path: Path to video file
        output_path: Path for output thumbnail
        timestamp: Timestamp in seconds (None for middle)
        width: Thumbnail width
        height: Thumbnail height
        
    Returns:
        Path to generated thumbnail
    """
    generator = ThumbnailGenerator(width=width, height=height)
    return generator.generate(video_path, output_path, timestamp)
