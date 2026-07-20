"""
Base interface for video source handlers
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

from src.models.video import SourceType

logger = logging.getLogger(__name__)


@dataclass
class VideoMetadata:
    """
    Container for video metadata extracted from source

    Attributes:
        title: Video title
        description: Video description
        duration: Duration in seconds
        width: Video width in pixels
        height: Video height in pixels
        fps: Frames per second
        codec: Video codec
        bitrate: Bitrate in kbps
        file_size: File size in bytes
        format: Video format/container
        thumbnail_url: URL to thumbnail (if available)
        extra: Additional metadata specific to source
    """
    title: str
    description: Optional[str] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    file_size: Optional[int] = None
    format: Optional[str] = None
    thumbnail_url: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'title': self.title,
            'description': self.description,
            'duration': self.duration,
            'resolution': f"{self.width}x{self.height}" if self.width and self.height else None,
            'fps': self.fps,
            'codec': self.codec,
            'bitrate': self.bitrate,
            'file_size': self.file_size,
            'format': self.format,
            'thumbnail_url': self.thumbnail_url,
            'extra': self.extra or {},
        }


class VideoSourceError(Exception):
    """Base exception for video source errors"""
    pass


class ValidationError(VideoSourceError):
    """Raised when source validation fails"""
    pass


class DownloadError(VideoSourceError):
    """Raised when download fails"""
    pass


class MetadataError(VideoSourceError):
    """Raised when metadata extraction fails"""
    pass


class VideoSourceHandler(ABC):
    """
    Abstract base class for video source handlers

    Subclasses must implement:
    - validate(): Validate the source
    - download(): Download/prepare the video file
    - get_metadata(): Extract video metadata
    """

    def __init__(self, source: str, source_type: SourceType):
        """
        Initialize handler

        Args:
            source: Source identifier (URL, file path, etc.)
            source_type: Type of source (LOCAL, YOUTUBE, STREAM)
        """
        self.source = source
        self.source_type = source_type
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def validate(self) -> bool:
        """
        Validate the video source

        Returns:
            True if valid, False otherwise

        Raises:
            ValidationError: If validation fails with details
        """
        pass

    @abstractmethod
    def download(self, destination: Path) -> Path:
        """
        Download or prepare video file

        Args:
            destination: Destination path for video file

        Returns:
            Path to downloaded/prepared video file

        Raises:
            DownloadError: If download fails
        """
        pass

    @abstractmethod
    def get_metadata(self) -> VideoMetadata:
        """
        Extract metadata from video source

        Returns:
            VideoMetadata object with extracted information

        Raises:
            MetadataError: If metadata extraction fails
        """
        pass

    def prepare_video(self, destination: Path) -> tuple[Path, VideoMetadata]:
        """
        Complete workflow: validate, download, and extract metadata

        Args:
            destination: Destination path for video file

        Returns:
            Tuple of (video_path, metadata)

        Raises:
            VideoSourceError: If any step fails
        """
        self.logger.info(f"Preparing video from {self.source_type.value} source")

        # Step 1: Validate
        try:
            self.logger.debug("Validating source...")
            if not self.validate():
                raise ValidationError(f"Source validation failed: {self.source}")
        except Exception as e:
            self.logger.error(f"Validation error: {e}")
            raise ValidationError(f"Failed to validate source: {e}") from e

        # Step 2: Download/prepare
        try:
            self.logger.debug("Downloading/preparing video...")
            video_path = self.download(destination)

            if not video_path.exists():
                raise DownloadError(f"Video file not found after download: {video_path}")

            self.logger.info(f"Video prepared at: {video_path}")

        except Exception as e:
            self.logger.error(f"Download error: {e}")
            raise DownloadError(f"Failed to download video: {e}") from e

        # Step 3: Extract metadata
        try:
            self.logger.debug("Extracting metadata...")
            metadata = self.get_metadata()
            self.logger.info(f"Metadata extracted - Title: {metadata.title}, Duration: {metadata.duration}s")

        except Exception as e:
            self.logger.error(f"Metadata extraction error: {e}")
            raise MetadataError(f"Failed to extract metadata: {e}") from e

        return video_path, metadata

    def cleanup(self):
        """
        Cleanup any temporary resources
        Override in subclasses if needed
        """
        pass

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources"""
        self.cleanup()
        return False
