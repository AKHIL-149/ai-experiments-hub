"""
Core functionality for video understanding platform
"""

from src.core.video_processor import (
    VideoProcessor,
    VideoProcessingError,
    ProcessingProgress,
    create_video_processor,
)

__all__ = [
    'VideoProcessor',
    'VideoProcessingError',
    'ProcessingProgress',
    'create_video_processor',
]
