"""
YouTube video handler using yt-dlp
"""

import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any

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


class YouTubeHandler(VideoSourceHandler):
    """
    Handler for YouTube videos using yt-dlp
    
    Supports:
    - Single videos
    - Playlist videos (downloads first video by default)
    - Various YouTube URL formats
    """
    
    # YouTube URL patterns
    URL_PATTERNS = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})',
    ]
    
    def __init__(self, url: str):
        """
        Initialize YouTube handler
        
        Args:
            url: YouTube video URL
        """
        super().__init__(url, SourceType.YOUTUBE)
        self.url = url
        self.video_id: Optional[str] = None
        self._info: Optional[Dict[str, Any]] = None
    
    def _extract_video_id(self) -> Optional[str]:
        """
        Extract video ID from URL
        
        Returns:
            Video ID or None if not found
        """
        for pattern in self.URL_PATTERNS:
            match = re.search(pattern, self.url)
            if match:
                return match.group(1)
        return None
    
    def validate(self) -> bool:
        """
        Validate YouTube URL
        
        Returns:
            True if valid
            
        Raises:
            ValidationError: If validation fails
        """
        # Extract video ID
        self.video_id = self._extract_video_id()
        
        if not self.video_id:
            raise ValidationError(
                f"Invalid YouTube URL: {self.url}. "
                f"Expected format: youtube.com/watch?v=VIDEO_ID or youtu.be/VIDEO_ID"
            )
        
        # Try to fetch video info to verify it exists
        try:
            import yt_dlp
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,  # Don't download, just get info
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self._info = ydl.extract_info(self.url, download=False)
            
            if not self._info:
                raise ValidationError("Could not fetch video information")
            
            # Check if video is available
            if self._info.get('is_live'):
                raise ValidationError("Live streams are not supported")
            
            # Check duration if available
            duration = self._info.get('duration', 0)
            if duration and duration > 7200:  # 2 hours
                logger.warning(f"Video is very long: {duration/60:.1f} minutes")
            
            self.logger.info(
                f"YouTube video validated - "
                f"ID: {self.video_id}, "
                f"Title: {self._info.get('title', 'Unknown')}"
            )
            
            return True
            
        except ImportError:
            raise ValidationError(
                "yt-dlp not installed. Install with: pip install yt-dlp"
            )
        except Exception as e:
            raise ValidationError(f"Failed to validate YouTube URL: {e}") from e
    
    def download(self, destination: Path) -> Path:
        """
        Download YouTube video
        
        Args:
            destination: Destination path for video file
            
        Returns:
            Path to downloaded video
            
        Raises:
            DownloadError: If download fails
        """
        try:
            import yt_dlp
            
            # Ensure destination directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # Setup download options
            ydl_opts = {
                'format': settings.yt_dlp_format,
                'outtmpl': str(destination.with_suffix('.%(ext)s')),
                'quiet': False,
                'no_warnings': False,
                'extract_flat': False,
                'max_filesize': settings.yt_dlp_max_filesize_mb * 1024 * 1024,
                'progress_hooks': [self._progress_hook],
            }
            
            # Download video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.logger.info(f"Downloading YouTube video: {self.video_id}")
                info = ydl.extract_info(self.url, download=True)
                
                # Store info for metadata extraction
                self._info = info
                
                # Get actual downloaded filename
                downloaded_file = Path(ydl.prepare_filename(info))
                
                if not downloaded_file.exists():
                    raise DownloadError(f"Downloaded file not found: {downloaded_file}")
                
                self.logger.info(f"YouTube video downloaded: {downloaded_file}")
                
                return downloaded_file
            
        except ImportError:
            raise DownloadError(
                "yt-dlp not installed. Install with: pip install yt-dlp"
            )
        except Exception as e:
            raise DownloadError(f"Failed to download YouTube video: {e}") from e
    
    def _progress_hook(self, d: Dict[str, Any]):
        """
        Progress hook for yt-dlp
        
        Args:
            d: Progress info dictionary
        """
        if d['status'] == 'downloading':
            if 'downloaded_bytes' in d and 'total_bytes' in d:
                percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                self.logger.debug(f"Download progress: {percent:.1f}%")
        elif d['status'] == 'finished':
            self.logger.info("Download finished, processing...")
    
    def get_metadata(self) -> VideoMetadata:
        """
        Extract metadata from YouTube video info
        
        Returns:
            VideoMetadata object
            
        Raises:
            MetadataError: If metadata extraction fails
        """
        if not self._info:
            raise MetadataError("Video info not available. Call validate() or download() first.")
        
        try:
            # Extract metadata from yt-dlp info
            metadata = VideoMetadata(
                title=self._info.get('title', 'Unknown'),
                description=self._info.get('description'),
                duration=float(self._info.get('duration', 0)),
                width=int(self._info.get('width', 0)),
                height=int(self._info.get('height', 0)),
                fps=float(self._info.get('fps', 0)),
                codec=self._info.get('vcodec'),
                format=self._info.get('ext'),
                thumbnail_url=self._info.get('thumbnail'),
                extra={
                    'video_id': self._info.get('id'),
                    'uploader': self._info.get('uploader'),
                    'upload_date': self._info.get('upload_date'),
                    'view_count': self._info.get('view_count'),
                    'like_count': self._info.get('like_count'),
                    'channel': self._info.get('channel'),
                    'channel_id': self._info.get('channel_id'),
                    'categories': self._info.get('categories', []),
                    'tags': self._info.get('tags', []),
                }
            )
            
            return metadata
            
        except Exception as e:
            raise MetadataError(f"Failed to extract metadata: {e}") from e
    
    def cleanup(self):
        """Cleanup - no temporary resources"""
        pass
