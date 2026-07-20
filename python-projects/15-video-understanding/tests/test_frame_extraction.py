"""
Tests for frame extraction pipeline
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil

from src.services.frame_extractor import (
    FrameExtractor,
    FrameMetadata,
    ExtractionMode,
    extract_frames_from_video
)
from src.services.keyframe_detector import (
    KeyframeDetector,
    Keyframe,
    DetectionMethod,
    detect_keyframes
)
from src.utils.frame_hasher import (
    FrameHasher,
    FrameHash,
    HashAlgorithm,
    compute_frame_hash,
    deduplicate_frame_list
)
from src.utils.frame_quality_filter import (
    FrameQualityFilter,
    QualityMetrics,
    filter_high_quality_frames
)
from src.services.frame_analyzer import (
    FrameAnalyzer,
    FrameAnalysisPipeline,
    analyze_video_frames
)


class TestFrameExtractor:
    """Tests for FrameExtractor service"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def mock_video_processor(self):
        """Mock VideoProcessor"""
        processor = Mock()
        processor.extract_frames.return_value = [
            Path("frame_1.jpg"),
            Path("frame_2.jpg"),
            Path("frame_3.jpg")
        ]
        return processor

    def test_extract_frames_interval_mode(self, mock_video_processor, temp_dir):
        """Test frame extraction in interval mode"""
        extractor = FrameExtractor(video_processor=mock_video_processor)

        video_path = Path("/fake/video.mp4")
        video_id = 1

        with patch('src.services.frame_extractor.storage_manager') as mock_storage:
            mock_storage.get_frames_directory.return_value = temp_dir

            # Mock frame paths
            for i in range(1, 4):
                frame_path = temp_dir / f"frame_{i}.jpg"
                frame_path.touch()

            metadata = extractor.extract_frames(
                video_path=video_path,
                video_id=video_id,
                fps=1.0,
                mode=ExtractionMode.INTERVAL
            )

            assert len(metadata) > 0
            assert all(isinstance(fm, FrameMetadata) for fm in metadata)

    def test_extract_single_frame(self, mock_video_processor, temp_dir):
        """Test single frame extraction"""
        extractor = FrameExtractor(video_processor=mock_video_processor)

        frame_path = temp_dir / "single_frame.jpg"
        frame_path.touch()

        mock_video_processor.extract_single_frame.return_value = frame_path

        with patch('src.services.frame_extractor.storage_manager') as mock_storage:
            mock_storage.get_frame_path.return_value = frame_path

            metadata = extractor.extract_single_frame(
                video_path=Path("/fake/video.mp4"),
                video_id=1,
                timestamp=5.0
            )

            assert isinstance(metadata, FrameMetadata)
            assert metadata.timestamp == 5.0
            assert metadata.file_path == frame_path

    def test_extraction_stats(self, temp_dir):
        """Test getting extraction statistics"""
        extractor = FrameExtractor()

        with patch('src.services.frame_extractor.storage_manager') as mock_storage:
            mock_storage.get_frames_directory.return_value = temp_dir

            # Create some test frames
            for i in range(5):
                (temp_dir / f"frame_{i}.jpg").touch()

            mock_storage.get_frames_directory.return_value.exists.return_value = True
            mock_storage.get_frames_directory.return_value.glob.return_value = [
                temp_dir / f"frame_{i}.jpg" for i in range(5)
            ]

            stats = extractor.get_extraction_stats(video_id=1)

            assert 'total_frames' in stats
            assert 'frames_dir' in stats


class TestKeyframeDetector:
    """Tests for KeyframeDetector"""

    @pytest.fixture
    def mock_video_processor(self):
        """Mock VideoProcessor"""
        processor = Mock()
        return processor

    def test_detect_keyframes(self, mock_video_processor):
        """Test keyframe detection"""
        detector = KeyframeDetector(video_processor=mock_video_processor)

        video_path = Path("/fake/video.mp4")

        # Mock ffprobe output
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = "0.0,I\n5.0,I\n10.0,I\n"
            mock_run.return_value.returncode = 0

            with patch.object(video_path, 'exists', return_value=True):
                keyframes = detector.detect_keyframes(
                    video_path=video_path,
                    method=DetectionMethod.SCENE_CHANGE,
                    threshold=0.3
                )

                assert isinstance(keyframes, list)
                assert all(isinstance(kf, Keyframe) for kf in keyframes)

    def test_multi_method_detection(self, mock_video_processor):
        """Test multi-method keyframe detection"""
        detector = KeyframeDetector(video_processor=mock_video_processor)

        video_path = Path("/fake/video.mp4")

        with patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = "0.0,I,1\n5.0,I,1\n"
            mock_run.return_value.returncode = 0

            with patch.object(video_path, 'exists', return_value=True):
                keyframes = detector.detect_keyframes_multi_method(
                    video_path=video_path,
                    methods=[DetectionMethod.SCENE_CHANGE, DetectionMethod.CODEC_KEYFRAME]
                )

                assert isinstance(keyframes, list)


class TestFrameHasher:
    """Tests for FrameHasher"""

    @pytest.fixture
    def temp_frame(self):
        """Create temporary test frame"""
        import numpy as np
        from PIL import Image

        temp_dir = Path(tempfile.mkdtemp())
        frame_path = temp_dir / "test_frame.jpg"

        # Create a simple test image
        image = Image.fromarray(np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8))
        image.save(frame_path)

        yield frame_path

        shutil.rmtree(temp_dir)

    def test_compute_hash(self, temp_frame):
        """Test hash computation"""
        hasher = FrameHasher()

        frame_hash = hasher.compute_hash(temp_frame)

        assert isinstance(frame_hash, FrameHash)
        assert frame_hash.md5_hash
        assert frame_hash.perceptual_hash
        assert frame_hash.dhash
        assert frame_hash.average_hash

    def test_find_duplicates(self, temp_frame):
        """Test duplicate detection"""
        hasher = FrameHasher()

        # Create hashes for same frame (will be duplicates)
        hash1 = hasher.compute_hash(temp_frame)
        hash2 = hasher.compute_hash(temp_frame)

        duplicates = hasher.find_duplicates([hash1, hash2])

        assert len(duplicates) > 0  # Should find duplicates

    def test_deduplicate_frames(self, temp_frame):
        """Test frame deduplication"""
        hasher = FrameHasher()

        hash1 = hasher.compute_hash(temp_frame)
        hash2 = hasher.compute_hash(temp_frame)

        unique, removed = hasher.deduplicate_frames([hash1, hash2])

        assert len(unique) == 1
        assert len(removed) == 1


class TestFrameQualityFilter:
    """Tests for FrameQualityFilter"""

    @pytest.fixture
    def temp_frame(self):
        """Create temporary test frame"""
        import numpy as np
        from PIL import Image

        temp_dir = Path(tempfile.mkdtemp())
        frame_path = temp_dir / "test_frame.jpg"

        # Create a test image with some content
        image = Image.fromarray(np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8))
        image.save(frame_path)

        yield frame_path

        shutil.rmtree(temp_dir)

    def test_compute_metrics(self, temp_frame):
        """Test quality metrics computation"""
        filter = FrameQualityFilter()

        metrics = filter.compute_metrics(temp_frame)

        assert isinstance(metrics, QualityMetrics)
        assert metrics.blur_score >= 0
        assert 0 <= metrics.brightness <= 255
        assert metrics.contrast >= 0
        assert 0 <= metrics.overall_quality <= 1

    def test_filter_frames(self, temp_frame):
        """Test frame filtering"""
        filter = FrameQualityFilter(blur_threshold=50.0)

        high_quality, low_quality = filter.filter_frames([temp_frame])

        assert len(high_quality) + len(low_quality) == 1

    def test_rank_by_quality(self, temp_frame):
        """Test quality ranking"""
        filter = FrameQualityFilter()

        ranked = filter.rank_by_quality([temp_frame])

        assert len(ranked) == 1
        assert isinstance(ranked[0], tuple)
        assert ranked[0][0] == temp_frame
        assert 0 <= ranked[0][1] <= 1


class TestFrameAnalyzer:
    """Tests for FrameAnalyzer pipeline"""

    @pytest.fixture
    def mock_components(self):
        """Mock all analyzer components"""
        mock_extractor = Mock()
        mock_detector = Mock()
        mock_hasher = Mock()
        mock_filter = Mock()

        return {
            'extractor': mock_extractor,
            'detector': mock_detector,
            'hasher': mock_hasher,
            'filter': mock_filter
        }

    def test_analyze_video(self, mock_components, tmp_path):
        """Test complete video analysis"""
        analyzer = FrameAnalyzer(
            frame_extractor=mock_components['extractor'],
            keyframe_detector=mock_components['detector'],
            frame_hasher=mock_components['hasher'],
            quality_filter=mock_components['filter']
        )

        video_path = Path("/fake/video.mp4")

        # Mock extraction
        mock_components['extractor'].extract_frames.return_value = [
            FrameMetadata(
                frame_number=1,
                timestamp=0.0,
                file_path=tmp_path / "frame_1.jpg",
                is_keyframe=False
            )
        ]

        # Mock keyframe detection
        mock_components['detector'].detect_keyframes.return_value = []

        # Mock deduplication
        mock_hash = FrameHash(
            frame_path=tmp_path / "frame_1.jpg",
            md5_hash="test",
            perceptual_hash="test",
            dhash="test",
            average_hash="test"
        )
        mock_components['hasher'].compute_hashes_batch.return_value = [mock_hash]
        mock_components['hasher'].deduplicate_frames.return_value = ([mock_hash], [])

        # Mock quality filtering
        mock_components['filter'].filter_frames.return_value = (
            [tmp_path / "frame_1.jpg"],
            [],
            []
        )

        with patch.object(video_path, 'exists', return_value=True):
            with patch('src.services.frame_analyzer.frame_storage') as mock_storage:
                mock_storage.get_frame_directory.return_value = tmp_path
                mock_storage.organize_frames.return_value = [tmp_path / "frame_1.jpg"]

                pipeline = FrameAnalysisPipeline()
                result = analyzer.analyze_video(
                    video_path=video_path,
                    video_id=1,
                    pipeline=pipeline
                )

                assert result.video_id == 1
                assert result.total_extracted > 0
                assert result.processing_time_seconds >= 0

    def test_pipeline_configuration(self):
        """Test pipeline configuration"""
        pipeline = FrameAnalysisPipeline()

        assert pipeline.extract_frames is True
        assert pipeline.deduplicate is True
        assert pipeline.quality_filter is True
        assert pipeline.detect_keyframes is True


class TestConvenienceFunctions:
    """Tests for convenience functions"""

    def test_extract_frames_from_video(self):
        """Test convenience function for frame extraction"""
        with patch('src.services.frame_extractor.FrameExtractor') as MockExtractor:
            mock_instance = MockExtractor.return_value
            mock_instance.extract_frames.return_value = []

            result = extract_frames_from_video(
                video_path=Path("/fake/video.mp4"),
                video_id=1
            )

            assert isinstance(result, list)

    def test_detect_keyframes_convenience(self):
        """Test convenience function for keyframe detection"""
        with patch('src.services.keyframe_detector.KeyframeDetector') as MockDetector:
            mock_instance = MockDetector.return_value
            mock_instance.detect_keyframes.return_value = []

            result = detect_keyframes(
                video_path=Path("/fake/video.mp4")
            )

            assert isinstance(result, list)

    def test_analyze_video_frames_convenience(self):
        """Test convenience function for video analysis"""
        with patch('src.services.frame_analyzer.FrameAnalyzer') as MockAnalyzer:
            from src.services.frame_analyzer import AnalysisResult

            mock_instance = MockAnalyzer.return_value
            mock_instance.analyze_video.return_value = AnalysisResult(
                video_id=1,
                total_extracted=10,
                after_deduplication=8,
                after_quality_filter=6,
                keyframes_detected=3,
                final_frame_count=6,
                frame_metadata=[],
                quality_metrics=[],
                storage_path=Path("/tmp"),
                processing_time_seconds=1.0
            )

            result = analyze_video_frames(
                video_path=Path("/fake/video.mp4"),
                video_id=1
            )

            assert result.video_id == 1
            assert result.final_frame_count == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
