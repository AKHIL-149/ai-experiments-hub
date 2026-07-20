"""
Video analysis and processing services
"""

from src.services.frame_extractor import (
    FrameExtractor,
    FrameMetadata,
    ExtractionMode,
    extract_frames_from_video,
)

__all__ = [
    'FrameExtractor',
    'FrameMetadata',
    'ExtractionMode',
    'extract_frames_from_video',
]
