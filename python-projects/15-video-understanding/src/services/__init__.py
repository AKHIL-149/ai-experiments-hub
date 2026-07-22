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
from src.services.transcription_service import (
    TranscriptionService,
    TranscriptionSegment,
    TranscriptionResult,
    transcribe_audio,
)
from src.services.speaker_diarization import (
    SpeakerDiarization,
    SpeakerSegment,
    DiarizationResult,
    diarize_audio,
)
from src.services.transcript_segmenter import (
    TranscriptSegmenter,
    TranscriptSegment as SegmenterSegment,
    segment_transcript,
)
from src.services.audio_features import (
    AudioFeatureExtractor,
    AudioFeatures,
    extract_audio_features,
)
from src.services.language_detector import (
    LanguageDetector,
    LanguageDetection,
    detect_language_from_audio,
    detect_language_from_text,
)
from src.services.audio_pipeline import (
    AudioProcessingPipeline,
    AudioPipelineConfig,
    AudioPipelineResult,
    process_video_audio,
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
    'TranscriptionService',
    'TranscriptionSegment',
    'TranscriptionResult',
    'transcribe_audio',
    'SpeakerDiarization',
    'SpeakerSegment',
    'DiarizationResult',
    'diarize_audio',
    'TranscriptSegmenter',
    'SegmenterSegment',
    'segment_transcript',
    'AudioFeatureExtractor',
    'AudioFeatures',
    'extract_audio_features',
    'LanguageDetector',
    'LanguageDetection',
    'detect_language_from_audio',
    'detect_language_from_text',
    'AudioProcessingPipeline',
    'AudioPipelineConfig',
    'AudioPipelineResult',
    'process_video_audio',
]
