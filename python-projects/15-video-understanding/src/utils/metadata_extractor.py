"""
Video metadata extraction utilities using ffprobe
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class VideoMetadataExtractor:
    """
    Extracts comprehensive metadata from video files using ffprobe
    """
    
    def __init__(self):
        """Initialize metadata extractor"""
        self._probe_data: Optional[Dict[str, Any]] = None
    
    def extract(self, video_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from video file
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary with extracted metadata
            
        Raises:
            ValueError: If video file not found
            RuntimeError: If metadata extraction fails
        """
        if not video_path.exists():
            raise ValueError(f"Video file not found: {video_path}")
        
        try:
            import ffmpeg
            
            # Probe video file
            self._probe_data = ffmpeg.probe(str(video_path))
            
            # Extract and organize metadata
            metadata = {
                'file': self._extract_file_info(video_path),
                'format': self._extract_format_info(),
                'video': self._extract_video_info(),
                'audio': self._extract_audio_info(),
                'subtitle': self._extract_subtitle_info(),
                'metadata_tags': self._extract_metadata_tags(),
            }
            
            logger.info(f"Metadata extracted from {video_path.name}")
            return metadata
            
        except ImportError:
            raise RuntimeError("ffmpeg-python not installed")
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Failed to extract metadata: {error_msg}") from e
        except Exception as e:
            raise RuntimeError(f"Metadata extraction failed: {e}") from e
    
    def _extract_file_info(self, video_path: Path) -> Dict[str, Any]:
        """Extract file information"""
        stat = video_path.stat()
        
        return {
            'path': str(video_path),
            'name': video_path.name,
            'extension': video_path.suffix,
            'size_bytes': stat.st_size,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'modified_time': stat.st_mtime,
        }
    
    def _extract_format_info(self) -> Dict[str, Any]:
        """Extract container format information"""
        if not self._probe_data:
            return {}
        
        format_data = self._probe_data.get('format', {})
        
        # Parse duration
        duration = float(format_data.get('duration', 0))
        
        # Parse bitrate
        bitrate = int(format_data.get('bit_rate', 0))
        
        return {
            'format_name': format_data.get('format_name'),
            'format_long_name': format_data.get('format_long_name'),
            'duration_seconds': duration,
            'duration_formatted': self._format_duration(duration),
            'bitrate_bps': bitrate,
            'bitrate_kbps': bitrate // 1000 if bitrate else 0,
            'nb_streams': int(format_data.get('nb_streams', 0)),
            'nb_programs': int(format_data.get('nb_programs', 0)),
            'probe_score': int(format_data.get('probe_score', 0)),
        }
    
    def _extract_video_info(self) -> Optional[Dict[str, Any]]:
        """Extract video stream information"""
        if not self._probe_data:
            return None
        
        # Find video stream
        video_stream = next(
            (s for s in self._probe_data['streams'] if s['codec_type'] == 'video'),
            None
        )
        
        if not video_stream:
            return None
        
        # Parse FPS
        fps_str = video_stream.get('r_frame_rate', '0/1')
        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = round(float(num) / float(den), 2) if float(den) != 0 else 0
        else:
            fps = float(fps_str)
        
        # Parse aspect ratio
        dar = video_stream.get('display_aspect_ratio', '')
        sar = video_stream.get('sample_aspect_ratio', '')
        
        return {
            'codec_name': video_stream.get('codec_name'),
            'codec_long_name': video_stream.get('codec_long_name'),
            'profile': video_stream.get('profile'),
            'width': int(video_stream.get('width', 0)),
            'height': int(video_stream.get('height', 0)),
            'resolution': f"{video_stream.get('width')}x{video_stream.get('height')}",
            'fps': fps,
            'fps_raw': fps_str,
            'bit_rate': int(video_stream.get('bit_rate', 0)),
            'pix_fmt': video_stream.get('pix_fmt'),
            'color_space': video_stream.get('color_space'),
            'color_range': video_stream.get('color_range'),
            'display_aspect_ratio': dar,
            'sample_aspect_ratio': sar,
            'nb_frames': video_stream.get('nb_frames'),
            'level': video_stream.get('level'),
            'refs': video_stream.get('refs'),
        }
    
    def _extract_audio_info(self) -> Optional[List[Dict[str, Any]]]:
        """Extract audio stream(s) information"""
        if not self._probe_data:
            return None
        
        # Find all audio streams
        audio_streams = [
            s for s in self._probe_data['streams']
            if s['codec_type'] == 'audio'
        ]
        
        if not audio_streams:
            return None
        
        audio_info = []
        for stream in audio_streams:
            audio_info.append({
                'index': stream.get('index'),
                'codec_name': stream.get('codec_name'),
                'codec_long_name': stream.get('codec_long_name'),
                'profile': stream.get('profile'),
                'sample_rate': int(stream.get('sample_rate', 0)),
                'channels': int(stream.get('channels', 0)),
                'channel_layout': stream.get('channel_layout'),
                'bit_rate': int(stream.get('bit_rate', 0)),
                'bits_per_sample': int(stream.get('bits_per_sample', 0)),
                'language': stream.get('tags', {}).get('language'),
            })
        
        return audio_info
    
    def _extract_subtitle_info(self) -> Optional[List[Dict[str, Any]]]:
        """Extract subtitle stream(s) information"""
        if not self._probe_data:
            return None
        
        # Find all subtitle streams
        subtitle_streams = [
            s for s in self._probe_data['streams']
            if s['codec_type'] == 'subtitle'
        ]
        
        if not subtitle_streams:
            return None
        
        subtitle_info = []
        for stream in subtitle_streams:
            subtitle_info.append({
                'index': stream.get('index'),
                'codec_name': stream.get('codec_name'),
                'codec_long_name': stream.get('codec_long_name'),
                'language': stream.get('tags', {}).get('language'),
                'title': stream.get('tags', {}).get('title'),
            })
        
        return subtitle_info
    
    def _extract_metadata_tags(self) -> Dict[str, Any]:
        """Extract metadata tags from container"""
        if not self._probe_data:
            return {}
        
        format_tags = self._probe_data.get('format', {}).get('tags', {})
        
        # Common metadata tags
        tags = {}
        
        # Title and description
        tags['title'] = format_tags.get('title')
        tags['description'] = format_tags.get('description') or format_tags.get('comment')
        
        # Author/creator info
        tags['artist'] = format_tags.get('artist') or format_tags.get('author')
        tags['album'] = format_tags.get('album')
        tags['genre'] = format_tags.get('genre')
        
        # Dates
        tags['creation_time'] = format_tags.get('creation_time')
        tags['date'] = format_tags.get('date')
        tags['year'] = format_tags.get('year')
        
        # Encoding info
        tags['encoder'] = format_tags.get('encoder')
        tags['encoded_by'] = format_tags.get('encoded_by')
        
        # Copyright
        tags['copyright'] = format_tags.get('copyright')
        
        # Custom tags
        tags['custom'] = {k: v for k, v in format_tags.items()
                         if k not in tags}
        
        # Remove None values
        tags = {k: v for k, v in tags.items() if v is not None}
        
        return tags
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """
        Format duration in seconds to HH:MM:SS.mmm
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted duration string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
        else:
            return f"{minutes:02d}:{secs:06.3f}"
    
    def get_probe_data(self) -> Optional[Dict[str, Any]]:
        """Get raw ffprobe data"""
        return self._probe_data


def extract_video_metadata(video_path: Path) -> Dict[str, Any]:
    """
    Convenience function to extract video metadata
    
    Args:
        video_path: Path to video file
        
    Returns:
        Dictionary with extracted metadata
    """
    extractor = VideoMetadataExtractor()
    return extractor.extract(video_path)
