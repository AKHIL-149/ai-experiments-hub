"""
Factory for creating appropriate video source handlers
"""

import logging
from pathlib import Path
from typing import Union
from urllib.parse import urlparse

from src.sources.base import VideoSourceHandler
from src.sources.local_handler import LocalFileHandler
from src.sources.youtube_handler import YouTubeHandler
from src.sources.streaming_handler import StreamingURLHandler
from src.models.video import SourceType

logger = logging.getLogger(__name__)


class VideoSourceFactory:
    """
    Factory class for creating appropriate video source handlers
    based on the input source type
    """
    
    # YouTube domain patterns
    YOUTUBE_DOMAINS = {'youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com'}
    
    @staticmethod
    def create_handler(source: str) -> VideoSourceHandler:
        """
        Create appropriate source handler based on source string
        
        Args:
            source: Video source (file path or URL)
            
        Returns:
            VideoSourceHandler instance
            
        Raises:
            ValueError: If source type cannot be determined
        """
        source_type = VideoSourceFactory.detect_source_type(source)
        
        if source_type == SourceType.LOCAL:
            logger.debug(f"Creating LocalFileHandler for: {source}")
            return LocalFileHandler(source)
        
        elif source_type == SourceType.YOUTUBE:
            logger.debug(f"Creating YouTubeHandler for: {source}")
            return YouTubeHandler(source)
        
        elif source_type == SourceType.STREAM:
            logger.debug(f"Creating StreamingURLHandler for: {source}")
            return StreamingURLHandler(source)
        
        else:
            raise ValueError(f"Could not determine source type for: {source}")
    
    @staticmethod
    def detect_source_type(source: str) -> SourceType:
        """
        Detect source type from source string
        
        Args:
            source: Video source (file path or URL)
            
        Returns:
            SourceType enum value
            
        Raises:
            ValueError: If source type cannot be determined
        """
        # Check if it's a local file path
        if VideoSourceFactory._is_local_file(source):
            return SourceType.LOCAL
        
        # Check if it's a URL
        if VideoSourceFactory._is_url(source):
            parsed = urlparse(source)
            
            # Check if it's YouTube
            if parsed.netloc in VideoSourceFactory.YOUTUBE_DOMAINS:
                return SourceType.YOUTUBE
            
            # Otherwise treat as streaming URL
            return SourceType.STREAM
        
        # If we can't determine, raise error
        raise ValueError(
            f"Could not determine source type for: {source}. "
            f"Expected: local file path, YouTube URL, or streaming URL."
        )
    
    @staticmethod
    def _is_local_file(source: str) -> bool:
        """
        Check if source is a local file path
        
        Args:
            source: Source string
            
        Returns:
            True if local file path
        """
        try:
            path = Path(source)
            # Check if it exists or has file-like path structure
            return path.exists() or (
                # Has extension and doesn't look like URL
                path.suffix and
                not source.startswith(('http://', 'https://'))
            )
        except Exception:
            return False
    
    @staticmethod
    def _is_url(source: str) -> bool:
        """
        Check if source is a URL
        
        Args:
            source: Source string
            
        Returns:
            True if URL
        """
        try:
            result = urlparse(source)
            return result.scheme in ('http', 'https') and result.netloc != ''
        except Exception:
            return False
    
    @classmethod
    def create_from_upload(cls, file_path: Union[str, Path]) -> VideoSourceHandler:
        """
        Create handler specifically for uploaded file
        
        Args:
            file_path: Path to uploaded file
            
        Returns:
            LocalFileHandler instance
        """
        return LocalFileHandler(str(file_path))
    
    @classmethod
    def create_from_youtube(cls, url: str) -> VideoSourceHandler:
        """
        Create handler specifically for YouTube URL
        
        Args:
            url: YouTube video URL
            
        Returns:
            YouTubeHandler instance
        """
        return YouTubeHandler(url)
    
    @classmethod
    def create_from_stream(cls, url: str) -> VideoSourceHandler:
        """
        Create handler specifically for streaming URL
        
        Args:
            url: Streaming video URL
            
        Returns:
            StreamingURLHandler instance
        """
        return StreamingURLHandler(url)


# Convenience functions

def create_handler(source: str) -> VideoSourceHandler:
    """
    Convenience function to create appropriate handler
    
    Args:
        source: Video source (file path or URL)
        
    Returns:
        VideoSourceHandler instance
    """
    return VideoSourceFactory.create_handler(source)


def detect_source_type(source: str) -> SourceType:
    """
    Convenience function to detect source type
    
    Args:
        source: Video source (file path or URL)
        
    Returns:
        SourceType enum value
    """
    return VideoSourceFactory.detect_source_type(source)
