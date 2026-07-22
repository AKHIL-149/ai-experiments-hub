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
from src.services.frame_analyzer import (
    FrameAnalyzer,
    FrameAnalysisPipeline,
    AnalysisResult,
    analyze_video_frames,
)
from src.services.audio_processor import (
    AudioProcessor,
    extract_audio_from_video,
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
    'FrameAnalyzer',
    'FrameAnalysisPipeline',
    'AnalysisResult',
    'analyze_video_frames',
    'AudioProcessor',
    'extract_audio_from_video',
]
