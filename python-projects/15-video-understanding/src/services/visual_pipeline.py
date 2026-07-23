"""
Visual analysis pipeline
Coordinates all visual analysis services for comprehensive frame understanding
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.services.image_captioning import ImageCaptioningService, ImageCaption
from src.services.object_detection import ObjectDetectionService, ObjectDetectionResult
from src.services.face_detection import FaceDetectionService, FaceDetectionResult
from src.services.ocr_service import OCRService, OCRResult
from src.services.action_recognition import ActionRecognitionService, ActionRecognitionResult
from src.services.visual_features import VisualFeatureExtractor, VisualFeatures

logger = logging.getLogger(__name__)


@dataclass
class VisualAnalysisConfig:
    """Configuration for visual analysis pipeline"""
    # Image captioning
    generate_captions: bool = True
    caption_model: str = "gpt4v"  # gpt4v or blip

    # Object detection
    detect_objects: bool = True
    object_model: str = "yolov8n"
    object_confidence: float = 0.25

    # Face detection
    detect_faces: bool = True
    face_backend: str = "opencv"
    face_confidence: float = 0.5

    # OCR
    extract_text: bool = True
    ocr_engine: str = "tesseract"
    ocr_language: str = "eng"

    # Action recognition (for video sequences)
    recognize_actions: bool = False
    action_method: str = "motion_based"

    # Visual features
    extract_features: bool = True
    feature_model: str = "resnet50"

    # Processing
    use_gpu: bool = True
    max_workers: int = 4
    parallel_processing: bool = True


@dataclass
class FrameAnalysis:
    """Complete visual analysis result for a single frame"""
    frame_path: Path
    frame_number: Optional[int] = None
    timestamp: Optional[float] = None

    # Analysis results
    caption: Optional[ImageCaption] = None
    objects: Optional[ObjectDetectionResult] = None
    faces: Optional[FaceDetectionResult] = None
    text: Optional[OCRResult] = None
    features: Optional[VisualFeatures] = None

    # Aggregated insights
    summary: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoAnalysisResult:
    """Complete visual analysis result for a video"""
    video_path: Optional[Path] = None
    frame_analyses: List[FrameAnalysis] = field(default_factory=list)
    actions: Optional[ActionRecognitionResult] = None

    # Aggregated statistics
    total_frames: int = 0
    total_objects: int = 0
    total_faces: int = 0
    total_text_regions: int = 0
    unique_objects: List[str] = field(default_factory=list)

    metadata: Dict[str, Any] = field(default_factory=dict)


class VisualAnalysisPipeline:
    """
    Comprehensive visual analysis pipeline
    Coordinates all visual services for unified frame understanding
    """

    def __init__(self, config: Optional[VisualAnalysisConfig] = None):
        """
        Initialize visual analysis pipeline

        Args:
            config: Pipeline configuration
        """
        self.config = config or VisualAnalysisConfig()

        # Initialize services
        self.captioning_service = None
        self.object_service = None
        self.face_service = None
        self.ocr_service = None
        self.action_service = None
        self.feature_extractor = None

        self._initialize_services()

    def _initialize_services(self):
        """Initialize all enabled services"""
        if self.config.generate_captions:
            self.captioning_service = ImageCaptioningService(
                use_local=(self.config.caption_model == "blip")
            )
            logger.info(f"Initialized captioning service: {self.config.caption_model}")

        if self.config.detect_objects:
            self.object_service = ObjectDetectionService(
                model_name=self.config.object_model,
                confidence_threshold=self.config.object_confidence
            )
            logger.info(f"Initialized object detection: {self.config.object_model}")

        if self.config.detect_faces:
            self.face_service = FaceDetectionService(
                backend=self.config.face_backend,
                min_confidence=self.config.face_confidence
            )
            logger.info(f"Initialized face detection: {self.config.face_backend}")

        if self.config.extract_text:
            self.ocr_service = OCRService(
                engine=self.config.ocr_engine,
                language=self.config.ocr_language
            )
            logger.info(f"Initialized OCR: {self.config.ocr_engine}")

        if self.config.recognize_actions:
            self.action_service = ActionRecognitionService(
                method=self.config.action_method
            )
            logger.info(f"Initialized action recognition: {self.config.action_method}")

        if self.config.extract_features:
            self.feature_extractor = VisualFeatureExtractor(
                model_name=self.config.feature_model,
                use_gpu=self.config.use_gpu
            )
            logger.info(f"Initialized feature extractor: {self.config.feature_model}")

    def analyze_frame(
        self,
        frame_path: Path,
        frame_number: Optional[int] = None,
        timestamp: Optional[float] = None
    ) -> FrameAnalysis:
        """
        Perform complete visual analysis on a single frame

        Args:
            frame_path: Path to frame image
            frame_number: Frame number in video
            timestamp: Timestamp in video

        Returns:
            FrameAnalysis with all results
        """
        logger.info(f"Analyzing frame: {frame_path.name}")

        analysis = FrameAnalysis(
            frame_path=frame_path,
            frame_number=frame_number,
            timestamp=timestamp
        )

        # Run all enabled analyses
        if self.captioning_service:
            try:
                analysis.caption = self.captioning_service.caption_image(frame_path)
            except Exception as e:
                logger.error(f"Captioning failed: {e}")

        if self.object_service:
            try:
                analysis.objects = self.object_service.detect_objects(frame_path)
            except Exception as e:
                logger.error(f"Object detection failed: {e}")

        if self.face_service:
            try:
                analysis.faces = self.face_service.detect_faces(frame_path)
            except Exception as e:
                logger.error(f"Face detection failed: {e}")

        if self.ocr_service:
            try:
                analysis.text = self.ocr_service.extract_text(frame_path)
            except Exception as e:
                logger.error(f"OCR failed: {e}")

        if self.feature_extractor:
            try:
                analysis.features = self.feature_extractor.extract_features(frame_path)
            except Exception as e:
                logger.error(f"Feature extraction failed: {e}")

        # Generate summary and tags
        analysis.summary = self._generate_frame_summary(analysis)
        analysis.tags = self._extract_tags(analysis)

        return analysis

    def analyze_frames(
        self,
        frame_paths: List[Path],
        frame_numbers: Optional[List[int]] = None,
        timestamps: Optional[List[float]] = None
    ) -> List[FrameAnalysis]:
        """
        Analyze multiple frames

        Args:
            frame_paths: List of frame paths
            frame_numbers: Optional frame numbers
            timestamps: Optional timestamps

        Returns:
            List of FrameAnalysis
        """
        logger.info(f"Analyzing {len(frame_paths)} frames")

        if frame_numbers is None:
            frame_numbers = [None] * len(frame_paths)
        if timestamps is None:
            timestamps = [None] * len(frame_paths)

        if self.config.parallel_processing:
            return self._analyze_frames_parallel(
                frame_paths, frame_numbers, timestamps
            )
        else:
            return self._analyze_frames_sequential(
                frame_paths, frame_numbers, timestamps
            )

    def _analyze_frames_sequential(
        self,
        frame_paths: List[Path],
        frame_numbers: List[Optional[int]],
        timestamps: List[Optional[float]]
    ) -> List[FrameAnalysis]:
        """Analyze frames sequentially"""
        results = []
        for frame_path, frame_num, ts in zip(frame_paths, frame_numbers, timestamps):
            analysis = self.analyze_frame(frame_path, frame_num, ts)
            results.append(analysis)
        return results

    def _analyze_frames_parallel(
        self,
        frame_paths: List[Path],
        frame_numbers: List[Optional[int]],
        timestamps: List[Optional[float]]
    ) -> List[FrameAnalysis]:
        """Analyze frames in parallel"""
        results = [None] * len(frame_paths)

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = {}
            for idx, (frame_path, frame_num, ts) in enumerate(
                zip(frame_paths, frame_numbers, timestamps)
            ):
                future = executor.submit(
                    self.analyze_frame, frame_path, frame_num, ts
                )
                futures[future] = idx

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Frame analysis failed: {e}")
                    results[idx] = FrameAnalysis(frame_path=frame_paths[idx])

        return results

    def analyze_video(
        self,
        video_path: Path,
        frame_paths: List[Path],
        fps: float = 30.0
    ) -> VideoAnalysisResult:
        """
        Analyze complete video

        Args:
            video_path: Path to video file
            frame_paths: List of extracted frame paths
            fps: Video frames per second

        Returns:
            VideoAnalysisResult
        """
        logger.info(f"Analyzing video: {video_path}")

        # Generate timestamps
        timestamps = [i / fps for i in range(len(frame_paths))]

        # Analyze all frames
        frame_analyses = self.analyze_frames(
            frame_paths,
            frame_numbers=list(range(len(frame_paths))),
            timestamps=timestamps
        )

        # Analyze actions if enabled
        actions = None
        if self.action_service:
            try:
                actions = self.action_service.recognize_actions(video_path, fps=fps)
            except Exception as e:
                logger.error(f"Action recognition failed: {e}")

        # Aggregate statistics
        result = VideoAnalysisResult(
            video_path=video_path,
            frame_analyses=frame_analyses,
            actions=actions,
            total_frames=len(frame_analyses)
        )

        self._aggregate_statistics(result)

        logger.info(f"Video analysis complete: {len(frame_analyses)} frames analyzed")

        return result

    def _generate_frame_summary(self, analysis: FrameAnalysis) -> str:
        """Generate natural language summary of frame analysis"""
        parts = []

        if analysis.caption:
            parts.append(analysis.caption.caption)

        if analysis.objects and analysis.objects.num_objects > 0:
            object_labels = [obj.label for obj in analysis.objects.objects]
            parts.append(f"Contains: {', '.join(set(object_labels))}")

        if analysis.faces and analysis.faces.num_faces > 0:
            parts.append(f"{analysis.faces.num_faces} face(s) detected")

        if analysis.text and analysis.text.text:
            text_preview = analysis.text.text[:100]
            parts.append(f"Text: '{text_preview}...'")

        return ". ".join(parts) if parts else "No significant content detected"

    def _extract_tags(self, analysis: FrameAnalysis) -> List[str]:
        """Extract tags from frame analysis"""
        tags = set()

        # Add object labels
        if analysis.objects:
            for obj in analysis.objects.objects:
                tags.add(obj.label)

        # Add face indicator
        if analysis.faces and analysis.faces.num_faces > 0:
            tags.add("faces")
            if analysis.faces.num_faces == 1:
                tags.add("person")
            elif analysis.faces.num_faces > 1:
                tags.add("people")

        # Add text indicator
        if analysis.text and analysis.text.text:
            tags.add("text")

        return sorted(list(tags))

    def _aggregate_statistics(self, result: VideoAnalysisResult):
        """Aggregate statistics across all frames"""
        all_objects = []
        total_faces = 0
        total_text_regions = 0

        for analysis in result.frame_analyses:
            if analysis.objects:
                total_objects = len(analysis.objects.objects)
                all_objects.extend([obj.label for obj in analysis.objects.objects])

            if analysis.faces:
                total_faces += analysis.faces.num_faces

            if analysis.text:
                total_text_regions += len(analysis.text.regions)

        result.total_objects = len(all_objects)
        result.total_faces = total_faces
        result.total_text_regions = total_text_regions
        result.unique_objects = sorted(list(set(all_objects)))

    def find_frames_with_objects(
        self,
        result: VideoAnalysisResult,
        object_labels: List[str]
    ) -> List[FrameAnalysis]:
        """
        Find frames containing specific objects

        Args:
            result: VideoAnalysisResult
            object_labels: List of object labels to search for

        Returns:
            List of FrameAnalysis containing the objects
        """
        matching_frames = []

        for analysis in result.frame_analyses:
            if analysis.objects:
                detected_labels = {obj.label for obj in analysis.objects.objects}
                if any(label in detected_labels for label in object_labels):
                    matching_frames.append(analysis)

        return matching_frames

    def find_frames_with_faces(
        self,
        result: VideoAnalysisResult,
        min_faces: int = 1,
        max_faces: Optional[int] = None
    ) -> List[FrameAnalysis]:
        """
        Find frames with specific number of faces

        Args:
            result: VideoAnalysisResult
            min_faces: Minimum number of faces
            max_faces: Maximum number of faces

        Returns:
            List of matching FrameAnalysis
        """
        matching_frames = []

        for analysis in result.frame_analyses:
            if analysis.faces:
                num_faces = analysis.faces.num_faces
                if num_faces >= min_faces:
                    if max_faces is None or num_faces <= max_faces:
                        matching_frames.append(analysis)

        return matching_frames

    def find_frames_with_text(
        self,
        result: VideoAnalysisResult,
        min_confidence: float = 0.5
    ) -> List[FrameAnalysis]:
        """
        Find frames containing text

        Args:
            result: VideoAnalysisResult
            min_confidence: Minimum OCR confidence

        Returns:
            List of FrameAnalysis with text
        """
        matching_frames = []

        for analysis in result.frame_analyses:
            if analysis.text:
                if analysis.text.confidence >= min_confidence and analysis.text.text:
                    matching_frames.append(analysis)

        return matching_frames

    def search_by_caption(
        self,
        result: VideoAnalysisResult,
        query: str
    ) -> List[FrameAnalysis]:
        """
        Search frames by caption content

        Args:
            result: VideoAnalysisResult
            query: Search query

        Returns:
            List of matching FrameAnalysis
        """
        query_lower = query.lower()
        matching_frames = []

        for analysis in result.frame_analyses:
            if analysis.caption and query_lower in analysis.caption.caption.lower():
                matching_frames.append(analysis)

        return matching_frames


def analyze_video_frames(
    video_path: Path,
    frame_paths: List[Path],
    config: Optional[VisualAnalysisConfig] = None
) -> VideoAnalysisResult:
    """
    Convenience function to analyze video frames

    Args:
        video_path: Path to video file
        frame_paths: List of frame paths
        config: Pipeline configuration

    Returns:
        VideoAnalysisResult
    """
    pipeline = VisualAnalysisPipeline(config)
    return pipeline.analyze_video(video_path, frame_paths)
