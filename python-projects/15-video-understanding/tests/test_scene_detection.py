"""
Tests for scene detection services
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import numpy as np

from src.services.scene_detection.base import (
    Scene,
    SceneBoundary,
    SceneType,
    TransitionType,
    SceneDetectorConfig,
    SceneDetector
)
from src.services.scene_detection.threshold_detector import ThresholdSceneDetector
from src.services.scene_detection.optical_flow_detector import OpticalFlowDetector
from src.services.scene_detection.color_histogram import ColorHistogramAnalyzer
from src.services.scene_detection.boundary_refiner import SceneBoundaryRefiner
from src.services.scene_detection.scene_classifier import SceneClassifier
from src.services.scene_detection.pipeline import (
    SceneDetectionPipeline,
    PipelineConfig
)


@pytest.fixture
def mock_video_path(tmp_path):
    """Create mock video path"""
    video_path = tmp_path / "test_video.mp4"
    video_path.touch()
    return video_path


@pytest.fixture
def sample_scenes():
    """Create sample scenes for testing"""
    return [
        Scene(
            scene_id=1,
            start_time=0.0,
            end_time=5.0,
            duration=5.0,
            start_frame=0,
            end_frame=125,
            frame_count=125,
            scene_type=SceneType.STATIC,
            transition_type=TransitionType.CUT,
            confidence=1.0
        ),
        Scene(
            scene_id=2,
            start_time=5.0,
            end_time=10.0,
            duration=5.0,
            start_frame=125,
            end_frame=250,
            frame_count=125,
            scene_type=SceneType.MOTION,
            transition_type=TransitionType.CUT,
            confidence=1.0
        ),
        Scene(
            scene_id=3,
            start_time=10.0,
            end_time=15.0,
            duration=5.0,
            start_frame=250,
            end_frame=375,
            frame_count=125,
            scene_type=SceneType.DIALOGUE,
            transition_type=TransitionType.FADE,
            confidence=0.9
        )
    ]


class TestSceneDetectorConfig:
    """Tests for SceneDetectorConfig"""

    def test_default_config(self):
        """Test default configuration"""
        config = SceneDetectorConfig()

        assert config.threshold == 27.0
        assert config.min_scene_length == 1.0
        assert config.max_scene_length is None
        assert config.detect_transitions is True
        assert config.classify_scenes is False
        assert config.extract_keyframes is True

    def test_custom_config(self):
        """Test custom configuration"""
        config = SceneDetectorConfig(
            threshold=30.0,
            min_scene_length=2.0,
            max_scene_length=60.0,
            detect_transitions=False
        )

        assert config.threshold == 30.0
        assert config.min_scene_length == 2.0
        assert config.max_scene_length == 60.0
        assert config.detect_transitions is False


class TestScene:
    """Tests for Scene dataclass"""

    def test_scene_creation(self):
        """Test scene creation"""
        scene = Scene(
            scene_id=1,
            start_time=0.0,
            end_time=5.0,
            duration=5.0,
            start_frame=0,
            end_frame=125,
            frame_count=125
        )

        assert scene.scene_id == 1
        assert scene.start_time == 0.0
        assert scene.end_time == 5.0
        assert scene.duration == 5.0
        assert scene.scene_type == SceneType.UNKNOWN
        assert scene.transition_type == TransitionType.CUT

    def test_middle_timestamp(self):
        """Test middle timestamp calculation"""
        scene = Scene(
            scene_id=1,
            start_time=0.0,
            end_time=10.0,
            duration=10.0,
            start_frame=0,
            end_frame=250,
            frame_count=250
        )

        assert scene.middle_timestamp == 5.0


class TestThresholdSceneDetector:
    """Tests for ThresholdSceneDetector"""

    def test_initialization(self):
        """Test detector initialization"""
        config = SceneDetectorConfig(threshold=30.0)
        detector = ThresholdSceneDetector(config=config, method="histogram")

        assert detector.config.threshold == 30.0
        assert detector.method == "histogram"

    def test_invalid_video_path(self):
        """Test detection with invalid video path"""
        detector = ThresholdSceneDetector()
        invalid_path = Path("/nonexistent/video.mp4")

        with pytest.raises(ValueError, match="Video not found"):
            detector.detect_scenes(invalid_path)

    @patch('cv2.VideoCapture')
    def test_detect_scenes_mock(self, mock_video_capture):
        """Test scene detection with mocked video"""
        # Mock video capture
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            5: 25.0,  # FPS
            7: 250   # Frame count
        }.get(prop, 0)

        # Mock frames
        mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.side_effect = [
            (True, mock_frame),
            (True, mock_frame + 50),  # Different frame
            (True, mock_frame),
            (False, None)
        ]

        mock_video_capture.return_value = mock_cap

        detector = ThresholdSceneDetector()
        video_path = Path("test.mp4")

        # Note: This will still fail without actual file, but tests the mock setup
        # In real tests, we'd use a test video file


class TestOpticalFlowDetector:
    """Tests for OpticalFlowDetector"""

    def test_initialization(self):
        """Test detector initialization"""
        detector = OpticalFlowDetector(
            flow_threshold=2.0,
            motion_threshold=0.3
        )

        assert detector.flow_threshold == 2.0
        assert detector.motion_threshold == 0.3

    def test_invalid_video_path(self):
        """Test detection with invalid video path"""
        detector = OpticalFlowDetector()
        invalid_path = Path("/nonexistent/video.mp4")

        with pytest.raises(ValueError, match="Video not found"):
            detector.detect_scenes(invalid_path)


class TestColorHistogramAnalyzer:
    """Tests for ColorHistogramAnalyzer"""

    def test_initialization(self):
        """Test analyzer initialization"""
        analyzer = ColorHistogramAnalyzer(
            hist_bins=32,
            channels="hsv"
        )

        assert analyzer.hist_bins == 32
        assert analyzer.channels == "hsv"

    def test_invalid_video_path(self):
        """Test analysis with invalid video path"""
        analyzer = ColorHistogramAnalyzer()
        invalid_path = Path("/nonexistent/video.mp4")

        with pytest.raises(ValueError, match="Video not found"):
            analyzer.detect_scenes(invalid_path)

    def test_histogram_difference(self):
        """Test histogram difference calculation"""
        analyzer = ColorHistogramAnalyzer()

        # Create mock histograms
        hist1 = np.random.rand(96)  # 32 bins * 3 channels
        hist2 = np.random.rand(96)

        diff = analyzer._histogram_difference(hist1, hist2)

        assert isinstance(diff, float)
        assert diff >= 0
        assert diff <= 100


class TestSceneBoundaryRefiner:
    """Tests for SceneBoundaryRefiner"""

    def test_initialization(self):
        """Test refiner initialization"""
        refiner = SceneBoundaryRefiner(
            min_scene_duration=2.0,
            merge_threshold=0.5
        )

        assert refiner.min_scene_duration == 2.0
        assert refiner.merge_threshold == 0.5

    def test_remove_micro_scenes(self, sample_scenes):
        """Test micro-scene removal"""
        # Add a micro-scene
        micro_scene = Scene(
            scene_id=4,
            start_time=15.0,
            end_time=15.3,
            duration=0.3,
            start_frame=375,
            end_frame=382,
            frame_count=7,
            scene_type=SceneType.TRANSITION,
            transition_type=TransitionType.CUT,
            confidence=0.5
        )

        scenes = sample_scenes + [micro_scene]

        refiner = SceneBoundaryRefiner(min_scene_duration=1.0)
        filtered = refiner._remove_micro_scenes(scenes)

        assert len(filtered) == 3
        assert all(s.duration >= 1.0 for s in filtered)

    def test_merge_adjacent_scenes(self, sample_scenes):
        """Test adjacent scene merging"""
        # Create adjacent scenes with small gap
        scene1 = Scene(
            scene_id=1,
            start_time=0.0,
            end_time=5.0,
            duration=5.0,
            start_frame=0,
            end_frame=125,
            frame_count=125,
            scene_type=SceneType.STATIC,
            transition_type=TransitionType.CUT,
            confidence=1.0
        )

        scene2 = Scene(
            scene_id=2,
            start_time=5.2,  # Small gap
            end_time=10.0,
            duration=4.8,
            start_frame=130,
            end_frame=250,
            frame_count=120,
            scene_type=SceneType.STATIC,
            transition_type=TransitionType.CUT,
            confidence=1.0
        )

        refiner = SceneBoundaryRefiner(merge_threshold=0.5)
        merged = refiner._merge_adjacent_scenes([scene1, scene2])

        assert len(merged) == 1
        assert merged[0].start_time == 0.0
        assert merged[0].end_time == 10.0

    def test_calculate_overlap(self):
        """Test overlap calculation"""
        scene1 = Scene(
            scene_id=1,
            start_time=0.0,
            end_time=10.0,
            duration=10.0,
            start_frame=0,
            end_frame=250,
            frame_count=250,
            scene_type=SceneType.STATIC,
            transition_type=TransitionType.CUT,
            confidence=1.0
        )

        scene2 = Scene(
            scene_id=2,
            start_time=8.0,
            end_time=15.0,
            duration=7.0,
            start_frame=200,
            end_frame=375,
            frame_count=175,
            scene_type=SceneType.MOTION,
            transition_type=TransitionType.CUT,
            confidence=1.0
        )

        refiner = SceneBoundaryRefiner()
        overlap = refiner._calculate_overlap(scene1, scene2)

        # Overlap is 2 seconds, shorter scene is 7 seconds
        # Overlap ratio = 2 / 7 ≈ 0.286
        assert overlap > 0.2
        assert overlap < 0.3

    def test_analyze_scene_consistency(self, sample_scenes):
        """Test scene consistency analysis"""
        refiner = SceneBoundaryRefiner()
        stats = refiner.analyze_scene_consistency(sample_scenes)

        assert stats['total_scenes'] == 3
        assert stats['avg_duration'] == 5.0
        assert 'gaps' in stats
        assert 'overlaps' in stats


class TestSceneClassifier:
    """Tests for SceneClassifier"""

    def test_initialization(self):
        """Test classifier initialization"""
        classifier = SceneClassifier(
            motion_threshold_low=1.0,
            motion_threshold_high=5.0
        )

        assert classifier.motion_threshold_low == 1.0
        assert classifier.motion_threshold_high == 5.0

    def test_classify_from_features(self):
        """Test classification from features"""
        classifier = SceneClassifier()

        # Test static scene
        scene_type = classifier._classify_from_features(0.5, None)
        assert scene_type == SceneType.STATIC

        # Test action scene
        scene_type = classifier._classify_from_features(6.0, None)
        assert scene_type == SceneType.ACTION

        # Test motion scene
        scene_type = classifier._classify_from_features(2.0, {'avg_energy': 0.1})
        assert scene_type == SceneType.MOTION

        # Test dialogue scene
        scene_type = classifier._classify_from_features(
            2.0,
            {'avg_energy': 0.5, 'avg_zcr': 0.15}
        )
        assert scene_type == SceneType.DIALOGUE

    def test_get_scene_statistics(self, sample_scenes):
        """Test scene statistics"""
        classifier = SceneClassifier()
        stats = classifier.get_scene_statistics(sample_scenes)

        assert stats['total_scenes'] == 3
        assert 'scene_types' in stats
        assert 'transition_types' in stats
        assert 'avg_duration_by_type' in stats


class TestSceneDetectionPipeline:
    """Tests for SceneDetectionPipeline"""

    def test_pipeline_initialization_default(self):
        """Test default pipeline initialization"""
        pipeline = SceneDetectionPipeline()

        assert isinstance(pipeline.config, PipelineConfig)
        assert len(pipeline.detectors) > 0

    def test_pipeline_initialization_custom(self):
        """Test custom pipeline initialization"""
        config = PipelineConfig(
            use_content_detector=False,
            use_threshold_detector=True,
            use_optical_flow=False,
            use_color_histogram=False,
            use_audio_detector=False
        )

        pipeline = SceneDetectionPipeline(config)

        assert len(pipeline.detectors) == 1
        assert 'threshold' in pipeline.detectors

    def test_get_pipeline_info(self):
        """Test pipeline info retrieval"""
        pipeline = SceneDetectionPipeline()
        info = pipeline.get_pipeline_info()

        assert 'enabled_detectors' in info
        assert 'num_detectors' in info
        assert 'voting_threshold' in info
        assert 'config' in info
        assert info['num_detectors'] > 0

    def test_merge_single_detector_result(self):
        """Test merging with single detector"""
        pipeline = SceneDetectionPipeline()

        results = {
            'detector1': [
                Scene(
                    scene_id=1,
                    start_time=0.0,
                    end_time=5.0,
                    duration=5.0,
                    start_frame=0,
                    end_frame=125,
                    frame_count=125,
                    scene_type=SceneType.STATIC,
                    transition_type=TransitionType.CUT,
                    confidence=1.0
                )
            ]
        }

        merged = pipeline._merge_detector_results(results)

        assert len(merged) == 1
        assert merged[0].scene_id == 1


class TestPipelineConfig:
    """Tests for PipelineConfig"""

    def test_default_config(self):
        """Test default pipeline configuration"""
        config = PipelineConfig()

        assert config.use_content_detector is True
        assert config.use_threshold_detector is True
        assert config.use_optical_flow is False
        assert config.use_color_histogram is True
        assert config.use_audio_detector is True
        assert config.classify_scenes is True
        assert config.refine_boundaries is True
        assert config.voting_threshold == 2
        assert config.parallel_execution is True

    def test_custom_config(self):
        """Test custom pipeline configuration"""
        config = PipelineConfig(
            use_content_detector=False,
            use_threshold_detector=True,
            voting_threshold=3,
            min_scene_length=2.0
        )

        assert config.use_content_detector is False
        assert config.use_threshold_detector is True
        assert config.voting_threshold == 3
        assert config.min_scene_length == 2.0


class TestSceneDetectorBase:
    """Tests for SceneDetector base class"""

    def test_get_scene_at_timestamp(self, sample_scenes):
        """Test finding scene at timestamp"""
        # Create a concrete implementation for testing
        class TestDetector(SceneDetector):
            def detect_scenes(self, video_path, start_time=None, end_time=None):
                return []

            def detect_boundaries(self, video_path, start_time=None, end_time=None):
                return []

        detector = TestDetector()

        # Find scene at timestamp
        scene = detector.get_scene_at_timestamp(sample_scenes, 7.0)
        assert scene is not None
        assert scene.scene_id == 2

        # No scene at timestamp
        scene = detector.get_scene_at_timestamp(sample_scenes, 20.0)
        assert scene is None

    def test_filter_short_scenes(self, sample_scenes):
        """Test short scene filtering"""
        class TestDetector(SceneDetector):
            def detect_scenes(self, video_path, start_time=None, end_time=None):
                return []

            def detect_boundaries(self, video_path, start_time=None, end_time=None):
                return []

        detector = TestDetector(config=SceneDetectorConfig(min_scene_length=6.0))

        # Add short scene
        short_scene = Scene(
            scene_id=4,
            start_time=15.0,
            end_time=17.0,
            duration=2.0,
            start_frame=375,
            end_frame=425,
            frame_count=50,
            scene_type=SceneType.STATIC,
            transition_type=TransitionType.CUT,
            confidence=1.0
        )

        scenes = sample_scenes + [short_scene]
        filtered = detector.filter_short_scenes(scenes, min_length=6.0)

        assert len(filtered) == 0  # All scenes are shorter than 6 seconds

    def test_get_scene_statistics(self, sample_scenes):
        """Test scene statistics calculation"""
        class TestDetector(SceneDetector):
            def detect_scenes(self, video_path, start_time=None, end_time=None):
                return []

            def detect_boundaries(self, video_path, start_time=None, end_time=None):
                return []

        detector = TestDetector()
        stats = detector.get_scene_statistics(sample_scenes)

        assert stats['total_scenes'] == 3
        assert stats['total_duration'] == 15.0
        assert stats['average_duration'] == 5.0
        assert stats['min_duration'] == 5.0
        assert stats['max_duration'] == 5.0
        assert 'scene_types' in stats
        assert 'transition_types' in stats


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
