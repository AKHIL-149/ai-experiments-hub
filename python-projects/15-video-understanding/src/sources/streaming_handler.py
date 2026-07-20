"""
Streaming URL handler for HTTP/HTTPS video streams and M3U8 playlists
"""

import logging
import re
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse

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


class StreamingURLHandler(VideoSourceHandler):
    """
    Handler for streaming video URLs (HTTP/HTTPS and M3U8 playlists)
    
    Supports:
    - Direct video file URLs (mp4, webm, etc.)
    - HLS streams (m3u8 playlists)
    - Progressive download streams
    """
    
    # Supported video extensions for direct URLs
    VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.m4v'}
    
    # HLS playlist extensions
    HLS_EXTENSIONS = {'.m3u8', '.m3u'}
    
    def __init__(self, url: str):
        """
        Initialize streaming URL handler
        
        Args:
            url: Streaming video URL
        """
        super().__init__(url, SourceType.STREAM)
        self.url = url
        self.parsed_url = urlparse(url)
        self.is_hls = False
        self._response_headers: Optional[Dict[str, str]] = None
    
    def validate(self) -> bool:
        """
        Validate streaming URL
        
        Returns:
            True if valid
            
        Raises:
            ValidationError: If validation fails
        """
        # Check URL scheme
        if self.parsed_url.scheme not in ('http', 'https'):
            raise ValidationError(
                f"Invalid URL scheme: {self.parsed_url.scheme}. "
                f"Only HTTP and HTTPS are supported."
            )
        
        # Check if URL has a valid hostname
        if not self.parsed_url.netloc:
            raise ValidationError("URL must have a valid hostname")
        
        try:
            # Send HEAD request to check if resource exists
            response = requests.head(
                self.url,
                allow_redirects=True,
                timeout=10,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            # If HEAD not supported, try GET with range
            if response.status_code == 405:
                response = requests.get(
                    self.url,
                    stream=True,
                    timeout=10,
                    headers={
                        'User-Agent': 'Mozilla/5.0',
                        'Range': 'bytes=0-1024'
                    }
                )
            
            # Check response status
            if response.status_code not in (200, 206):
                raise ValidationError(
                    f"URL returned status code {response.status_code}"
                )
            
            # Store headers for later use
            self._response_headers = dict(response.headers)
            
            # Check content type
            content_type = response.headers.get('Content-Type', '').lower()
            
            # Check if it's an HLS playlist
            path_lower = self.parsed_url.path.lower()
            if any(path_lower.endswith(ext) for ext in self.HLS_EXTENSIONS):
                self.is_hls = True
                self.logger.info("Detected HLS stream (m3u8)")
            
            # Check if it's a video file
            elif 'video/' in content_type:
                self.is_hls = False
                self.logger.info(f"Detected video stream: {content_type}")
            
            # Check by file extension if content type is not video
            elif any(path_lower.endswith(ext) for ext in self.VIDEO_EXTENSIONS):
                self.is_hls = False
                self.logger.info("Detected video file by extension")
            
            else:
                # Try to detect from content
                if 'application/vnd.apple.mpegurl' in content_type or \
                   'application/x-mpegurl' in content_type:
                    self.is_hls = True
                    self.logger.info("Detected HLS stream by content type")
                else:
                    logger.warning(
                        f"Could not determine if URL is video. "
                        f"Content-Type: {content_type}, Path: {path_lower}"
                    )
            
            # Check content length if available
            content_length = response.headers.get('Content-Length')
            if content_length and not self.is_hls:
                size_mb = int(content_length) / (1024 * 1024)
                max_size_mb = settings.max_video_size_mb
                
                if size_mb > max_size_mb:
                    raise ValidationError(
                        f"Video size ({size_mb:.1f} MB) exceeds maximum "
                        f"allowed size ({max_size_mb} MB)"
                    )
                
                self.logger.info(f"Video size: {size_mb:.1f} MB")
            
            self.logger.info(f"Streaming URL validated: {self.url}")
            return True
            
        except requests.exceptions.RequestException as e:
            raise ValidationError(f"Failed to access URL: {e}") from e
        except Exception as e:
            raise ValidationError(f"URL validation failed: {e}") from e
    
    def download(self, destination: Path) -> Path:
        """
        Download streaming video
        
        Args:
            destination: Destination path for video file
            
        Returns:
            Path to downloaded video
            
        Raises:
            DownloadError: If download fails
        """
        try:
            # Ensure destination directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            if self.is_hls:
                # Use ffmpeg to download HLS stream
                return self._download_hls(destination)
            else:
                # Direct HTTP download
                return self._download_http(destination)
            
        except Exception as e:
            raise DownloadError(f"Failed to download stream: {e}") from e
    
    def _download_http(self, destination: Path) -> Path:
        """
        Download direct HTTP video stream
        
        Args:
            destination: Destination path
            
        Returns:
            Path to downloaded file
        """
        self.logger.info(f"Downloading HTTP stream to: {destination}")
        
        response = requests.get(
            self.url,
            stream=True,
            timeout=30,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        response.raise_for_status()
        
        # Get total size if available
        total_size = int(response.headers.get('Content-Length', 0))
        downloaded = 0
        
        # Download in chunks
        chunk_size = 8192
        with open(destination, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Log progress
                    if total_size > 0 and downloaded % (chunk_size * 100) == 0:
                        percent = (downloaded / total_size) * 100
                        self.logger.debug(f"Download progress: {percent:.1f}%")
        
        self.logger.info(f"HTTP download complete: {destination}")
        return destination
    
    def _download_hls(self, destination: Path) -> Path:
        """
        Download HLS stream using ffmpeg
        
        Args:
            destination: Destination path
            
        Returns:
            Path to downloaded file
        """
        import subprocess
        
        self.logger.info(f"Downloading HLS stream to: {destination}")
        
        # Ensure destination has video extension
        if not destination.suffix:
            destination = destination.with_suffix('.mp4')
        
        # Use ffmpeg to download HLS
        cmd = [
            settings.ffmpeg_path,
            '-i', self.url,
            '-c', 'copy',  # Copy without re-encoding
            '-bsf:a', 'aac_adtstoasc',  # Fix AAC bitstream
            '-y',  # Overwrite output file
            str(destination)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.processing_timeout_seconds
            )
            
            if result.returncode != 0:
                raise DownloadError(
                    f"ffmpeg failed with error: {result.stderr}"
                )
            
            self.logger.info(f"HLS download complete: {destination}")
            return destination
            
        except subprocess.TimeoutExpired:
            raise DownloadError("HLS download timed out")
        except FileNotFoundError:
            raise DownloadError(
                f"ffmpeg not found at: {settings.ffmpeg_path}. "
                f"Please install ffmpeg or update the path in settings."
            )
    
    def get_metadata(self) -> VideoMetadata:
        """
        Extract metadata from streaming URL
        
        Returns:
            VideoMetadata object
            
        Raises:
            MetadataError: If metadata extraction fails
        """
        try:
            # Extract filename from URL
            path_parts = self.parsed_url.path.split('/')
            filename = path_parts[-1] if path_parts else 'stream'
            
            # Remove query parameters and extension
            title = filename.split('?')[0]
            if '.' in title:
                title = '.'.join(title.split('.')[:-1])
            
            # Get file size from headers if available
            file_size = None
            if self._response_headers:
                content_length = self._response_headers.get('Content-Length')
                if content_length:
                    file_size = int(content_length)
            
            metadata = VideoMetadata(
                title=title or 'Streaming Video',
                description=f"Streaming video from {self.parsed_url.netloc}",
                file_size=file_size,
                extra={
                    'url': self.url,
                    'domain': self.parsed_url.netloc,
                    'is_hls': self.is_hls,
                    'content_type': self._response_headers.get('Content-Type') if self._response_headers else None,
                }
            )
            
            return metadata
            
        except Exception as e:
            raise MetadataError(f"Failed to extract metadata: {e}") from e
    
    def cleanup(self):
        """Cleanup - no temporary resources"""
        pass
