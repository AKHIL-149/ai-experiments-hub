"""
Core functionality for video understanding platform
"""

from src.core.video_processor import (
    VideoProcessor,
    VideoProcessingError,
    ProcessingProgress,
    create_video_processor,
)
from src.core.frame_storage import (
    FrameStorageManager,
    frame_storage,
)

__all__ = [
    'VideoProcessor',
    'VideoProcessingError',
    'ProcessingProgress',
    'create_video_processor',
    'FrameStorageManager',
    'frame_storage',
]
