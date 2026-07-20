"""
Local file handler for uploaded video files
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

from src.sources.base import (
    VideoSourceHandler,
    VideoMetadata,
    ValidationError,
    DownloadError,
    MetadataError,
)
from src.models.video import SourceType
from src.core.config import settings

logger = logging.getLogger(__name__)


class LocalFileHandler(VideoSourceHandler):
    """
    Handler for local video files (uploaded or already on disk)
    
    Validates file format, size, and integrity before processing
    """
    
    # Supported video formats
    SUPPORTED_FORMATS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
    
    def __init__(self, file_path: str):
        """
        Initialize local file handler
        
        Args:
            file_path: Path to local video file
        """
        super().__init__(file_path, SourceType.LOCAL)
        self.file_path = Path(file_path)
        self._metadata: Optional[VideoMetadata] = None
    
    def validate(self) -> bool:
        """
        Validate local video file
        
        Returns:
            True if valid
            
        Raises:
            ValidationError: If validation fails
        """
        # Check file exists
        if not self.file_path.exists():
            raise ValidationError(f"File not found: {self.file_path}")
        
        # Check it's a file (not directory)
        if not self.file_path.is_file():
            raise ValidationError(f"Path is not a file: {self.file_path}")
        
        # Check file format
        file_ext = self.file_path.suffix.lower()
        if file_ext not in self.SUPPORTED_FORMATS:
            raise ValidationError(
                f"Unsupported file format: {file_ext}. "
                f"Supported formats: {', '.join(self.SUPPORTED_FORMATS)}"
            )
        
        # Check file size
        file_size_mb = self.file_path.stat().st_size / (1024 * 1024)
        max_size_mb = settings.max_video_size_mb
        
        if file_size_mb > max_size_mb:
            raise ValidationError(
                f"File size ({file_size_mb:.1f} MB) exceeds maximum "
                f"allowed size ({max_size_mb} MB)"
            )
        
        # Check file is readable
        try:
            with open(self.file_path, 'rb') as f:
                # Read first few bytes to verify file is accessible
                f.read(1024)
        except (PermissionError, IOError) as e:
            raise ValidationError(f"Cannot read file: {e}")
        
        self.logger.info(
            f"Local file validated - "
            f"Path: {self.file_path.name}, "
            f"Size: {file_size_mb:.1f} MB"
        )
        
        return True
    
    def download(self, destination: Path) -> Path:
        """
        Move or copy local file to destination
        
        Args:
            destination: Destination directory (not filename)
            
        Returns:
            Path to video file in destination
            
        Raises:
            DownloadError: If move/copy fails
        """
        try:
            # Ensure destination directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # If source and destination are on same filesystem, move
            # Otherwise, copy
            try:
                # Try to move first (faster)
                shutil.move(str(self.file_path), str(destination))
                self.logger.info(f"Moved file to: {destination}")
                
            except (OSError, shutil.Error):
                # Fall back to copy if move fails
                shutil.copy2(str(self.file_path), str(destination))
                self.logger.info(f"Copied file to: {destination}")
            
            return destination
            
        except Exception as e:
            raise DownloadError(f"Failed to move/copy file: {e}") from e
    
    def get_metadata(self) -> VideoMetadata:
        """
        Extract metadata from local video file
        
        Returns:
            VideoMetadata object
            
        Raises:
            MetadataError: If metadata extraction fails
        """
        if self._metadata:
            return self._metadata
        
        try:
            import ffmpeg
            
            # Use ffprobe to extract metadata
            probe = ffmpeg.probe(str(self.file_path))
            
            # Get video stream
            video_stream = next(
                (s for s in probe['streams'] if s['codec_type'] == 'video'),
                None
            )
            
            if not video_stream:
                raise MetadataError("No video stream found in file")
            
            # Extract metadata
            format_info = probe.get('format', {})
            
            # Parse duration
            duration = float(format_info.get('duration', 0))
            
            # Parse FPS
            fps_str = video_stream.get('r_frame_rate', '0/1')
            if '/' in fps_str:
                num, den = fps_str.split('/')
                fps = float(num) / float(den) if float(den) != 0 else 0
            else:
                fps = float(fps_str)
            
            # Parse bitrate
            bitrate = int(format_info.get('bit_rate', 0)) // 1000  # Convert to kbps
            
            self._metadata = VideoMetadata(
                title=self.file_path.stem,
                duration=duration,
                width=int(video_stream.get('width', 0)),
                height=int(video_stream.get('height', 0)),
                fps=fps,
                codec=video_stream.get('codec_name'),
                bitrate=bitrate,
                file_size=self.file_path.stat().st_size,
                format=format_info.get('format_name'),
                extra={
                    'codec_long_name': video_stream.get('codec_long_name'),
                    'pix_fmt': video_stream.get('pix_fmt'),
                    'nb_frames': video_stream.get('nb_frames'),
                }
            )
            
            return self._metadata
            
        except ImportError:
            raise MetadataError(
                "ffmpeg-python not installed. Install with: pip install ffmpeg-python"
            )
        except ffmpeg.Error as e:
            raise MetadataError(f"ffprobe error: {e.stderr.decode()}") from e
        except Exception as e:
            raise MetadataError(f"Failed to extract metadata: {e}") from e
    
    def cleanup(self):
        """Cleanup - no temporary resources for local files"""
        pass
