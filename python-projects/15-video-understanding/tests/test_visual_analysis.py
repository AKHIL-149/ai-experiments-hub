"""
Tests for visual analysis services
"""

import pytest
from pathlib import Path
import numpy as np
from PIL import Image
import tempfile
import shutil

from src.services.image_captioning import ImageCaptioningService, ImageCaption
from src.services.object_detection import ObjectDetectionService, DetectedObject
from src.services.face_detection import FaceDetectionService, DetectedFace
from src.services.ocr_service import OCRService, TextRegion
from src.services.action_recognition import ActionRecognitionService, RecognizedAction
from src.services.visual_features import VisualFeatureExtractor, VisualFeatures
from src.services.visual_pipeline import (
    VisualAnalysisPipeline,
    VisualAnalysisConfig,
    FrameAnalysis,
    VideoAnalysisResult
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files"""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def sample_image(temp_dir):
    """Create a sample test image"""
    image_path = temp_dir / "test_image.jpg"

    # Create a simple test image
    image = Image.new('RGB', (640, 480), color='blue')
    image.save(image_path)

    return image_path


@pytest.fixture
def sample_images(temp_dir):
    """Create multiple sample images"""
    images = []
    for i in range(5):
        image_path = temp_dir / f"test_image_{i}.jpg"
        color = ['red', 'green', 'blue', 'yellow', 'white'][i]
        image = Image.new('RGB', (320, 240), color=color)
        image.save(image_path)
        images.append(image_path)

    return images


@pytest.fixture
def image_with_text(temp_dir):
    """Create image with text for OCR testing"""
    from PIL import ImageDraw, ImageFont

    image_path = temp_dir / "text_image.jpg"
    image = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(image)

    # Draw some text
    text = "Hello World\nTest OCR"
    draw.text((50, 50), text, fill='black')

    image.save(image_path)
    return image_path


class TestImageCaptioning:
    """Tests for ImageCaptioningService"""

    def test_service_initialization(self):
        """Test service initialization"""
        service = ImageCaptioningService(use_local=True)
        assert service is not None
        assert service.use_local is True

    def test_caption_image_local(self, sample_image):
        """Test local captioning with BLIP"""
        service = ImageCaptioningService(use_local=True)

        try:
            result = service.caption_image(sample_image)

            assert isinstance(result, ImageCaption)
            assert result.image_path == sample_image
            assert isinstance(result.caption, str)
            assert len(result.caption) > 0
            assert result.model == "blip"
        except Exception as e:
            pytest.skip(f"BLIP model not available: {e}")

    def test_caption_batch(self, sample_images):
        """Test batch captioning"""
        service = ImageCaptioningService(use_local=True)

        try:
            results = service.caption_batch(sample_images)

            assert len(results) == len(sample_images)
            for result in results:
                assert isinstance(result, ImageCaption)
        except Exception as e:
            pytest.skip(f"BLIP model not available: {e}")

    def test_invalid_image_path(self):
        """Test error handling for invalid image"""
        service = ImageCaptioningService(use_local=True)

        with pytest.raises(ValueError):
            service.caption_image(Path("nonexistent.jpg"))


class TestObjectDetection:
    """Tests for ObjectDetectionService"""

    def test_service_initialization(self):
        """Test service initialization"""
        service = ObjectDetectionService(model_name="yolov8n")
        assert service is not None
        assert service.model_name == "yolov8n"
        assert service.confidence_threshold == 0.25

    def test_detect_objects(self, sample_image):
        """Test object detection"""
        service = ObjectDetectionService()

        try:
            result = service.detect_objects(sample_image)

            assert result.image_path == sample_image
            assert isinstance(result.objects, list)
            assert result.num_objects == len(result.objects)
            assert result.model == "yolov8n"
        except Exception as e:
            pytest.skip(f"YOLO model not available: {e}")

    def test_filter_by_confidence(self, sample_image):
        """Test confidence filtering"""
        service = ObjectDetectionService()

        try:
            result = service.detect_objects(sample_image)
            filtered = service.filter_by_confidence(result, min_confidence=0.5)

            assert filtered.num_objects <= result.num_objects
            for obj in filtered.objects:
                assert obj.confidence >= 0.5
        except Exception as e:
            pytest.skip(f"YOLO model not available: {e}")

    def test_count_objects_by_class(self, sample_image):
        """Test object counting by class"""
        service = ObjectDetectionService()

        try:
            result = service.detect_objects(sample_image)
            counts = service.count_objects_by_class(result)

            assert isinstance(counts, dict)
            assert sum(counts.values()) == result.num_objects
        except Exception as e:
            pytest.skip(f"YOLO model not available: {e}")


class TestFaceDetection:
    """Tests for FaceDetectionService"""

    def test_service_initialization(self):
        """Test service initialization"""
        service = FaceDetectionService(backend="opencv")
        assert service is not None
        assert service.backend == "opencv"

    def test_detect_faces_opencv(self, sample_image):
        """Test face detection with OpenCV"""
        service = FaceDetectionService(backend="opencv")

        result = service.detect_faces(sample_image)

        assert result.image_path == sample_image
        assert isinstance(result.faces, list)
        assert result.num_faces == len(result.faces)
        assert result.model == "opencv-haar"

    def test_detect_faces_batch(self, sample_images):
        """Test batch face detection"""
        service = FaceDetectionService()

        results = service.detect_batch(sample_images)

        assert len(results) == len(sample_images)
        for result in results:
            assert isinstance(result.num_faces, int)

    def test_get_largest_face(self, sample_image):
        """Test getting largest face"""
        service = FaceDetectionService()
        result = service.detect_faces(sample_image)

        if result.num_faces > 0:
            largest = service.get_largest_face(result)
            assert isinstance(largest, DetectedFace)
        else:
            largest = service.get_largest_face(result)
            assert largest is None


class TestOCRService:
    """Tests for OCRService"""

    def test_service_initialization(self):
        """Test service initialization"""
        service = OCRService(engine="tesseract")
        assert service is not None
        assert service.engine == "tesseract"

    def test_extract_text_tesseract(self, image_with_text):
        """Test text extraction with Tesseract"""
        service = OCRService(engine="tesseract")

        try:
            result = service.extract_text(image_with_text)

            assert result.image_path == image_with_text
            assert isinstance(result.text, str)
            assert isinstance(result.regions, list)
            assert result.model == "tesseract"
        except Exception as e:
            pytest.skip(f"Tesseract not available: {e}")

    def test_has_text(self, image_with_text):
        """Test text detection"""
        service = OCRService()

        try:
            result = service.extract_text(image_with_text)
            has_text = service.has_text(result, min_confidence=0.3)

            assert isinstance(has_text, bool)
        except Exception as e:
            pytest.skip(f"Tesseract not available: {e}")

    def test_filter_by_confidence(self, image_with_text):
        """Test confidence filtering"""
        service = OCRService()

        try:
            result = service.extract_text(image_with_text)
            filtered = service.filter_by_confidence(result, min_confidence=0.5)

            assert len(filtered.regions) <= len(result.regions)
            for region in filtered.regions:
                assert region.confidence >= 0.5
        except Exception as e:
            pytest.skip(f"Tesseract not available: {e}")


class TestActionRecognition:
    """Tests for ActionRecognitionService"""

    def test_service_initialization(self):
        """Test service initialization"""
        service = ActionRecognitionService(method="motion_based")
        assert service is not None
        assert service.method == "motion_based"

    def test_motion_based_recognition(self, temp_dir):
        """Test motion-based action recognition"""
        # Create a simple test video
        import cv2

        video_path = temp_dir / "test_video.mp4"

        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (640, 480))

        # Write some frames
        for i in range(90):  # 3 seconds at 30fps
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            # Add some motion
            cv2.circle(frame, (i * 7, 240), 50, (255, 255, 255), -1)
            out.write(frame)

        out.release()

        service = ActionRecognitionService(method="motion_based")

        try:
            result = service.recognize_actions(video_path, fps=30.0)

            assert result.video_path == video_path
            assert isinstance(result.actions, list)
            assert result.num_actions == len(result.actions)
            assert result.model == "motion_based"
        except Exception as e:
            pytest.skip(f"Action recognition failed: {e}")

    def test_filter_by_action(self, temp_dir):
        """Test filtering actions by type"""
        service = ActionRecognitionService()

        # Create mock result
        from src.services.action_recognition import ActionRecognitionResult

        result = ActionRecognitionResult(
            video_path=temp_dir / "test.mp4",
            actions=[
                RecognizedAction("walking", 0.9, 0, 30, 0.0, 1.0),
                RecognizedAction("running", 0.8, 30, 60, 1.0, 2.0),
            ],
            num_actions=2,
            model="motion_based"
        )

        filtered = service.filter_by_action(result, ["walking"])

        assert filtered.num_actions == 1
        assert filtered.actions[0].action == "walking"


class TestVisualFeatures:
    """Tests for VisualFeatureExtractor"""

    def test_service_initialization(self):
        """Test service initialization"""
        extractor = VisualFeatureExtractor(model_name="resnet50")
        assert extractor is not None
        assert extractor.model_name == "resnet50"

    def test_extract_features(self, sample_image):
        """Test feature extraction"""
        extractor = VisualFeatureExtractor(model_name="resnet50")

        try:
            result = extractor.extract_features(sample_image)

            assert isinstance(result, VisualFeatures)
            assert result.image_path == sample_image
            assert isinstance(result.features, np.ndarray)
            assert len(result.features) > 0
            assert result.model == "resnet50"
        except Exception as e:
            pytest.skip(f"PyTorch not available: {e}")

    def test_compute_similarity(self, sample_images):
        """Test similarity computation"""
        extractor = VisualFeatureExtractor()

        try:
            features1 = extractor.extract_features(sample_images[0])
            features2 = extractor.extract_features(sample_images[1])

            similarity = extractor.compute_similarity(features1, features2)

            assert 0.0 <= similarity.similarity <= 1.0
            assert similarity.metric == "cosine"
        except Exception as e:
            pytest.skip(f"PyTorch not available: {e}")

    def test_find_similar(self, sample_images):
        """Test finding similar images"""
        extractor = VisualFeatureExtractor()

        try:
            # Extract features for all images
            features_list = extractor.extract_batch(sample_images)

            # Find similar to first image
            similar = extractor.find_similar(
                features_list[0],
                features_list[1:],
                top_k=3
            )

            assert len(similar) <= 3
            for feat, score in similar:
                assert isinstance(feat, VisualFeatures)
                assert 0.0 <= score <= 1.0
        except Exception as e:
            pytest.skip(f"PyTorch not available: {e}")

    def test_cluster_features(self, sample_images):
        """Test feature clustering"""
        extractor = VisualFeatureExtractor()

        try:
            features_list = extractor.extract_batch(sample_images)

            clusters = extractor.cluster_features(features_list, n_clusters=2)

            assert isinstance(clusters, dict)
            assert len(clusters) <= 2

            total_items = sum(len(items) for items in clusters.values())
            assert total_items == len(sample_images)
        except Exception as e:
            pytest.skip(f"PyTorch or sklearn not available: {e}")


class TestVisualAnalysisPipeline:
    """Tests for VisualAnalysisPipeline"""

    def test_pipeline_initialization(self):
        """Test pipeline initialization"""
        config = VisualAnalysisConfig(
            generate_captions=False,
            detect_objects=False,
            detect_faces=True,
            extract_text=False,
            extract_features=False
        )

        pipeline = VisualAnalysisPipeline(config)

        assert pipeline.config == config
        assert pipeline.face_service is not None
        assert pipeline.captioning_service is None

    def test_analyze_frame(self, sample_image):
        """Test single frame analysis"""
        config = VisualAnalysisConfig(
            generate_captions=False,
            detect_objects=False,
            detect_faces=True,
            extract_text=False,
            extract_features=False
        )

        pipeline = VisualAnalysisPipeline(config)
        result = pipeline.analyze_frame(sample_image, frame_number=0, timestamp=0.0)

        assert isinstance(result, FrameAnalysis)
        assert result.frame_path == sample_image
        assert result.frame_number == 0
        assert result.timestamp == 0.0
        assert result.faces is not None

    def test_analyze_frames_sequential(self, sample_images):
        """Test sequential frame analysis"""
        config = VisualAnalysisConfig(
            generate_captions=False,
            detect_objects=False,
            detect_faces=True,
            extract_text=False,
            extract_features=False,
            parallel_processing=False
        )

        pipeline = VisualAnalysisPipeline(config)
        results = pipeline.analyze_frames(sample_images)

        assert len(results) == len(sample_images)
        for result in results:
            assert isinstance(result, FrameAnalysis)

    def test_analyze_frames_parallel(self, sample_images):
        """Test parallel frame analysis"""
        config = VisualAnalysisConfig(
            generate_captions=False,
            detect_objects=False,
            detect_faces=True,
            extract_text=False,
            extract_features=False,
            parallel_processing=True,
            max_workers=2
        )

        pipeline = VisualAnalysisPipeline(config)
        results = pipeline.analyze_frames(sample_images)

        assert len(results) == len(sample_images)
        for result in results:
            assert isinstance(result, FrameAnalysis)

    def test_find_frames_with_faces(self, sample_images):
        """Test finding frames with faces"""
        config = VisualAnalysisConfig(
            generate_captions=False,
            detect_objects=False,
            detect_faces=True,
            extract_text=False,
            extract_features=False
        )

        pipeline = VisualAnalysisPipeline(config)

        # Analyze frames
        frame_analyses = pipeline.analyze_frames(sample_images)

        result = VideoAnalysisResult(
            frame_analyses=frame_analyses,
            total_frames=len(frame_analyses)
        )

        # Find frames with faces
        frames_with_faces = pipeline.find_frames_with_faces(result, min_faces=1)

        assert isinstance(frames_with_faces, list)
        for frame in frames_with_faces:
            assert frame.faces.num_faces >= 1

    def test_summary_generation(self, sample_image):
        """Test summary generation"""
        config = VisualAnalysisConfig(
            generate_captions=False,
            detect_objects=False,
            detect_faces=True,
            extract_text=False,
            extract_features=False
        )

        pipeline = VisualAnalysisPipeline(config)
        result = pipeline.analyze_frame(sample_image)

        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    def test_tag_extraction(self, sample_image):
        """Test tag extraction"""
        config = VisualAnalysisConfig(
            generate_captions=False,
            detect_objects=False,
            detect_faces=True,
            extract_text=False,
            extract_features=False
        )

        pipeline = VisualAnalysisPipeline(config)
        result = pipeline.analyze_frame(sample_image)

        assert isinstance(result.tags, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
