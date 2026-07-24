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
from src.services.image_captioning import (
    ImageCaptioningService,
    ImageCaption,
    caption_image,
    caption_frames,
)
from src.services.object_detection import (
    ObjectDetectionService,
    DetectedObject,
    ObjectDetectionResult,
    detect_objects_in_image,
    detect_objects_in_frames,
)
from src.services.face_detection import (
    FaceDetectionService,
    DetectedFace,
    FaceDetectionResult,
    detect_faces_in_image,
    detect_faces_in_frames,
)
from src.services.ocr_service import (
    OCRService,
    TextRegion,
    OCRResult,
    extract_text_from_image,
    extract_text_from_frames,
)
from src.services.action_recognition import (
    ActionRecognitionService,
    RecognizedAction,
    ActionRecognitionResult,
    recognize_actions,
)
from src.services.visual_features import (
    VisualFeatureExtractor,
    VisualFeatures,
    SimilarityResult,
    extract_visual_features,
    extract_features_batch,
)
from src.services.visual_pipeline import (
    VisualAnalysisPipeline,
    VisualAnalysisConfig,
    FrameAnalysis,
    VideoAnalysisResult,
)
from src.services.clip import (
    CLIPModel,
    CLIPConfig,
    CLIPFrameEmbedder,
    FrameEmbedding,
    VideoEmbeddings,
    embed_video_frames,
    CLIPTextEmbedder,
    TextEmbedding,
    QueryResult,
    search_video_frames,
    SemanticSimilarityCalculator,
    SimilarityMatrix,
    SimilarityPair,
    compute_clip_similarity,
    EmbeddingIndexer,
    IndexConfig,
    SearchResult,
    create_frame_index,
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
    'ImageCaptioningService',
    'ImageCaption',
    'caption_image',
    'caption_frames',
    'ObjectDetectionService',
    'DetectedObject',
    'ObjectDetectionResult',
    'detect_objects_in_image',
    'detect_objects_in_frames',
    'FaceDetectionService',
    'DetectedFace',
    'FaceDetectionResult',
    'detect_faces_in_image',
    'detect_faces_in_frames',
    'OCRService',
    'TextRegion',
    'OCRResult',
    'extract_text_from_image',
    'extract_text_from_frames',
    'ActionRecognitionService',
    'RecognizedAction',
    'ActionRecognitionResult',
    'recognize_actions',
    'VisualFeatureExtractor',
    'VisualFeatures',
    'SimilarityResult',
    'extract_visual_features',
    'extract_features_batch',
    'VisualAnalysisPipeline',
    'VisualAnalysisConfig',
    'FrameAnalysis',
    'VideoAnalysisResult',
    'CLIPModel',
    'CLIPConfig',
    'CLIPFrameEmbedder',
    'FrameEmbedding',
    'VideoEmbeddings',
    'embed_video_frames',
    'CLIPTextEmbedder',
    'TextEmbedding',
    'QueryResult',
    'search_video_frames',
    'SemanticSimilarityCalculator',
    'SimilarityMatrix',
    'SimilarityPair',
    'compute_clip_similarity',
    'EmbeddingIndexer',
    'IndexConfig',
    'SearchResult',
    'create_frame_index',
]
