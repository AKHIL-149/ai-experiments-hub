"""
Video source handlers for different video sources
"""

from src.sources.base import (
    VideoSourceHandler,
    VideoMetadata,
    VideoSourceError,
    ValidationError,
    DownloadError,
    MetadataError,
)
from src.sources.local_handler import LocalFileHandler
from src.sources.youtube_handler import YouTubeHandler
from src.sources.streaming_handler import StreamingURLHandler
from src.sources.factory import VideoSourceFactory, create_handler, detect_source_type

__all__ = [
    "VideoSourceHandler",
    "VideoMetadata",
    "VideoSourceError",
    "ValidationError",
    "DownloadError",
    "MetadataError",
    "LocalFileHandler",
    "YouTubeHandler",
    "StreamingURLHandler",
    "VideoSourceFactory",
    "create_handler",
    "detect_source_type",
]
