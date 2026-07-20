"""
Video validation utilities for checking video file integrity and compatibility
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from src.core.config import settings

logger = logging.getLogger(__name__)


class VideoValidator:
    """
    Validates video files for integrity, format compatibility, and processing requirements
    """
    
    # Supported video codecs
    SUPPORTED_CODECS = {
        'h264', 'h265', 'hevc', 'vp8', 'vp9', 'av1',
        'mpeg4', 'mpeg2video', 'theora', 'wmv3'
    }
    
    # Supported audio codecs
    SUPPORTED_AUDIO_CODECS = {
        'aac', 'mp3', 'opus', 'vorbis', 'pcm_s16le', 'flac', 'ac3'
    }
    
    # Minimum requirements
    MIN_DURATION = 0.1  # 100ms minimum
    MAX_DURATION = 14400  # 4 hours maximum (can be adjusted)
    MIN_RESOLUTION = 144  # Minimum height in pixels
    MAX_RESOLUTION = 8192  # Maximum dimension (8K)
    
    def __init__(self):
        """Initialize video validator"""
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self._video_info: Optional[Dict[str, Any]] = None
    
    def validate_file(self, file_path: Path) -> bool:
        """
        Validate video file
        
        Args:
            file_path: Path to video file
            
        Returns:
            True if valid, False otherwise
        """
        self.errors = []
        self.warnings = []
        
        # Check file exists
        if not self._check_file_exists(file_path):
            return False
        
        # Check file size
        if not self._check_file_size(file_path):
            return False
        
        # Extract and validate video properties
        if not self._extract_video_info(file_path):
            return False
        
        # Validate video stream
        if not self._validate_video_stream():
            return False
        
        # Validate audio stream (warning only)
        self._validate_audio_stream()
        
        # Validate duration
        if not self._validate_duration():
            return False
        
        # Validate resolution
        if not self._validate_resolution():
            return False
        
        # Check for corruption
        if not self._check_corruption(file_path):
            return False
        
        # Log results
        if self.errors:
            logger.error(f"Video validation failed: {', '.join(self.errors)}")
            return False
        
        if self.warnings:
            logger.warning(f"Video validation warnings: {', '.join(self.warnings)}")
        
        logger.info(f"Video validation passed: {file_path.name}")
        return True
    
    def _check_file_exists(self, file_path: Path) -> bool:
        """Check if file exists"""
        if not file_path.exists():
            self.errors.append("File does not exist")
            return False
        
        if not file_path.is_file():
            self.errors.append("Path is not a file")
            return False
        
        return True
    
    def _check_file_size(self, file_path: Path) -> bool:
        """Check file size"""
        try:
            size_mb = file_path.stat().st_size / (1024 * 1024)
            
            if size_mb == 0:
                self.errors.append("File is empty")
                return False
            
            max_size_mb = settings.max_video_size_mb
            if size_mb > max_size_mb:
                self.errors.append(
                    f"File size ({size_mb:.1f} MB) exceeds maximum ({max_size_mb} MB)"
                )
                return False
            
            return True
            
        except Exception as e:
            self.errors.append(f"Failed to check file size: {e}")
            return False
    
    def _extract_video_info(self, file_path: Path) -> bool:
        """Extract video information using ffprobe"""
        try:
            import ffmpeg
            
            probe = ffmpeg.probe(str(file_path))
            self._video_info = probe
            return True
            
        except ImportError:
            self.errors.append("ffmpeg-python not installed")
            return False
        except ffmpeg.Error as e:
            self.errors.append(f"Failed to probe video: {e.stderr.decode()}")
            return False
        except Exception as e:
            self.errors.append(f"Failed to extract video info: {e}")
            return False
    
    def _validate_video_stream(self) -> bool:
        """Validate video stream properties"""
        if not self._video_info:
            self.errors.append("No video information available")
            return False
        
        # Find video stream
        video_stream = next(
            (s for s in self._video_info['streams'] if s['codec_type'] == 'video'),
            None
        )
        
        if not video_stream:
            self.errors.append("No video stream found")
            return False
        
        # Check codec
        codec = video_stream.get('codec_name', '').lower()
        if codec not in self.SUPPORTED_CODECS:
            self.warnings.append(
                f"Video codec '{codec}' may not be fully supported. "
                f"Recommended: {', '.join(list(self.SUPPORTED_CODECS)[:3])}"
            )
        
        # Check if video has frames
        nb_frames = video_stream.get('nb_frames')
        if nb_frames and int(nb_frames) == 0:
            self.errors.append("Video has no frames")
            return False
        
        return True
    
    def _validate_audio_stream(self) -> bool:
        """Validate audio stream (warnings only)"""
        if not self._video_info:
            return True
        
        # Find audio stream
        audio_stream = next(
            (s for s in self._video_info['streams'] if s['codec_type'] == 'audio'),
            None
        )
        
        if not audio_stream:
            self.warnings.append("No audio stream found (video-only)")
            return True
        
        # Check codec
        codec = audio_stream.get('codec_name', '').lower()
        if codec not in self.SUPPORTED_AUDIO_CODECS:
            self.warnings.append(
                f"Audio codec '{codec}' may not be fully supported"
            )
        
        return True
    
    def _validate_duration(self) -> bool:
        """Validate video duration"""
        if not self._video_info:
            return False
        
        format_info = self._video_info.get('format', {})
        duration = float(format_info.get('duration', 0))
        
        if duration < self.MIN_DURATION:
            self.errors.append(
                f"Video too short: {duration:.2f}s (minimum: {self.MIN_DURATION}s)"
            )
            return False
        
        if duration > self.MAX_DURATION:
            self.errors.append(
                f"Video too long: {duration/60:.1f}min (maximum: {self.MAX_DURATION/60:.0f}min)"
            )
            return False
        
        return True
    
    def _validate_resolution(self) -> bool:
        """Validate video resolution"""
        if not self._video_info:
            return False
        
        video_stream = next(
            (s for s in self._video_info['streams'] if s['codec_type'] == 'video'),
            None
        )
        
        if not video_stream:
            return False
        
        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        
        if width == 0 or height == 0:
            self.errors.append("Invalid video resolution")
            return False
        
        if height < self.MIN_RESOLUTION:
            self.errors.append(
                f"Resolution too low: {width}x{height} "
                f"(minimum height: {self.MIN_RESOLUTION}p)"
            )
            return False
        
        if width > self.MAX_RESOLUTION or height > self.MAX_RESOLUTION:
            self.warnings.append(
                f"Very high resolution: {width}x{height}. Processing may be slow."
            )
        
        return True
    
    def _check_corruption(self, file_path: Path) -> bool:
        """
        Check for video corruption by attempting to read frames
        
        This is a basic check - reads first few seconds
        """
        try:
            import ffmpeg
            
            # Try to read first 5 seconds of video
            probe_duration = min(5.0, float(self._video_info['format'].get('duration', 5.0)))
            
            stream = ffmpeg.input(str(file_path), t=probe_duration)
            stream = ffmpeg.output(stream, 'pipe:', format='null', loglevel='error')
            
            ffmpeg.run(stream, capture_stdout=True, capture_stderr=True)
            
            return True
            
        except ffmpeg.Error as e:
            self.errors.append(f"Video appears to be corrupted: {e.stderr.decode()}")
            return False
        except Exception as e:
            self.warnings.append(f"Could not check for corruption: {e}")
            return True  # Don't fail validation on this
    
    def get_errors(self) -> List[str]:
        """Get validation errors"""
        return self.errors
    
    def get_warnings(self) -> List[str]:
        """Get validation warnings"""
        return self.warnings
    
    def get_video_info(self) -> Optional[Dict[str, Any]]:
        """Get extracted video information"""
        return self._video_info
    
    def get_validation_report(self) -> Dict[str, Any]:
        """
        Get detailed validation report
        
        Returns:
            Dictionary with validation results
        """
        if not self._video_info:
            return {
                'valid': False,
                'errors': self.errors,
                'warnings': self.warnings,
            }
        
        video_stream = next(
            (s for s in self._video_info['streams'] if s['codec_type'] == 'video'),
            {}
        )
        
        audio_stream = next(
            (s for s in self._video_info['streams'] if s['codec_type'] == 'audio'),
            None
        )
        
        format_info = self._video_info.get('format', {})
        
        return {
            'valid': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings,
            'video': {
                'codec': video_stream.get('codec_name'),
                'width': video_stream.get('width'),
                'height': video_stream.get('height'),
                'fps': video_stream.get('r_frame_rate'),
                'duration': float(format_info.get('duration', 0)),
            },
            'audio': {
                'codec': audio_stream.get('codec_name') if audio_stream else None,
                'sample_rate': audio_stream.get('sample_rate') if audio_stream else None,
                'channels': audio_stream.get('channels') if audio_stream else None,
            } if audio_stream else None,
            'format': format_info.get('format_name'),
            'size_mb': float(format_info.get('size', 0)) / (1024 * 1024),
        }


def validate_video_file(file_path: Path) -> tuple[bool, Dict[str, Any]]:
    """
    Convenience function to validate a video file
    
    Args:
        file_path: Path to video file
        
    Returns:
        Tuple of (is_valid, validation_report)
    """
    validator = VideoValidator()
    is_valid = validator.validate_file(file_path)
    report = validator.get_validation_report()
    return is_valid, report
