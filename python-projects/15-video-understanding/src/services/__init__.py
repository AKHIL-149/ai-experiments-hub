"""
Video analysis and processing services
"""

from src.services.frame_extractor import (
    FrameExtractor,
    FrameMetadata,
    ExtractionMode,
    extract_frames_from_video,
)
from src.services.keyframe_detector import (
    KeyframeDetector,
    Keyframe,
    DetectionMethod,
    detect_keyframes,
)

__all__ = [
    'FrameExtractor',
    'FrameMetadata',
    'ExtractionMode',
    'extract_frames_from_video',
    'KeyframeDetector',
    'Keyframe',
    'DetectionMethod',
    'detect_keyframes',
]
