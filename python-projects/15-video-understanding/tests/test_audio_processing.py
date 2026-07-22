"""
Tests for audio processing services
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import numpy as np

from src.services.audio_processor import AudioProcessor
from src.services.transcription_service import (
    TranscriptionService,
    TranscriptionSegment,
    TranscriptionResult
)
from src.services.speaker_diarization import (
    SpeakerDiarization,
    SpeakerSegment,
    DiarizationResult
)
from src.services.transcript_segmenter import TranscriptSegmenter
from src.services.audio_features import AudioFeatureExtractor, AudioFeatures
from src.services.language_detector import LanguageDetector, LanguageDetection
from src.services.audio_pipeline import (
    AudioProcessingPipeline,
    AudioPipelineConfig
)


@pytest.fixture
def mock_audio_path(tmp_path):
    """Create mock audio path"""
    audio_path = tmp_path / "test_audio.wav"
    audio_path.touch()
    return audio_path


@pytest.fixture
def mock_video_path(tmp_path):
    """Create mock video path"""
    video_path = tmp_path / "test_video.mp4"
    video_path.touch()
    return video_path


@pytest.fixture
def sample_transcription_segments():
    """Create sample transcription segments"""
    return [
        TranscriptionSegment(
            id=0,
            start=0.0,
            end=3.0,
            text="Hello world.",
            language="en"
        ),
        TranscriptionSegment(
            id=1,
            start=3.0,
            end=6.0,
            text="This is a test.",
            language="en"
        ),
        TranscriptionSegment(
            id=2,
            start=6.0,
            end=10.0,
            text="Testing audio processing.",
            language="en"
        )
    ]


class TestAudioProcessor:
    """Tests for AudioProcessor"""

    def test_initialization(self):
        """Test processor initialization"""
        processor = AudioProcessor()
        assert processor is not None

    def test_invalid_video_path(self):
        """Test extraction with invalid video path"""
        processor = AudioProcessor()
        invalid_path = Path("/nonexistent/video.mp4")

        with pytest.raises(ValueError, match="Video not found"):
            processor.extract_audio(invalid_path)

    def test_invalid_audio_path_for_info(self):
        """Test get_audio_info with invalid path"""
        processor = AudioProcessor()
        invalid_path = Path("/nonexistent/audio.wav")

        with pytest.raises(ValueError, match="Audio file not found"):
            processor.get_audio_info(invalid_path)


class TestTranscriptionService:
    """Tests for TranscriptionService"""

    def test_initialization_no_api_key(self):
        """Test initialization without API key"""
        service = TranscriptionService()
        assert service.api_key is None or len(service.api_key) > 0

    def test_initialization_with_api_key(self):
        """Test initialization with API key"""
        service = TranscriptionService(api_key="test-key-123")
        assert service.api_key == "test-key-123"

    def test_initialization_prefer_local(self):
        """Test initialization with prefer_local"""
        service = TranscriptionService(prefer_local=True, model_name="tiny")
        assert service.prefer_local is True
        assert service.model_name == "tiny"

    def test_transcribe_invalid_path(self):
        """Test transcription with invalid audio path"""
        service = TranscriptionService()
        invalid_path = Path("/nonexistent/audio.wav")

        with pytest.raises(ValueError, match="Audio file not found"):
            service.transcribe(invalid_path)

    def test_format_timestamp_srt(self):
        """Test SRT timestamp formatting"""
        service = TranscriptionService()
        timestamp = service._format_timestamp(65.5, srt=True)
        assert timestamp == "00:01:05,500"

    def test_format_timestamp_vtt(self):
        """Test VTT timestamp formatting"""
        service = TranscriptionService()
        timestamp = service._format_timestamp(65.5, srt=False)
        assert timestamp == "00:01:05.500"

    def test_get_transcript_text(self):
        """Test getting full transcript text"""
        service = TranscriptionService()

        result = TranscriptionResult(
            text="This is a test transcript.",
            segments=[],
            language="en",
            duration=10.0,
            source="test",
            model="test-model"
        )

        text = service.get_transcript_text(result)
        assert text == "This is a test transcript."


class TestSpeakerDiarization:
    """Tests for SpeakerDiarization"""

    def test_initialization(self):
        """Test diarization service initialization"""
        service = SpeakerDiarization()
        assert service.pipeline is None

    def test_initialization_with_params(self):
        """Test initialization with parameters"""
        service = SpeakerDiarization(
            min_speakers=2,
            max_speakers=4
        )
        assert service.min_speakers == 2
        assert service.max_speakers == 4

    def test_diarize_invalid_path(self):
        """Test diarization with invalid audio path"""
        service = SpeakerDiarization()
        invalid_path = Path("/nonexistent/audio.wav")

        with pytest.raises(ValueError, match="Audio file not found"):
            service.diarize(invalid_path)

    def test_find_speaker_at_time(self):
        """Test finding speaker at specific time"""
        service = SpeakerDiarization()

        segments = [
            SpeakerSegment(
                speaker_id="SPEAKER_00",
                start=0.0,
                end=5.0,
                duration=5.0
            ),
            SpeakerSegment(
                speaker_id="SPEAKER_01",
                start=5.0,
                end=10.0,
                duration=5.0
            )
        ]

        speaker = service._find_speaker_at_time(segments, 3.0)
        assert speaker == "SPEAKER_00"

        speaker = service._find_speaker_at_time(segments, 7.0)
        assert speaker == "SPEAKER_01"

        speaker = service._find_speaker_at_time(segments, 15.0)
        assert speaker == "UNKNOWN"

    def test_get_speaker_statistics(self):
        """Test speaker statistics calculation"""
        service = SpeakerDiarization()

        result = DiarizationResult(
            segments=[
                SpeakerSegment("SPEAKER_00", 0.0, 5.0, 5.0),
                SpeakerSegment("SPEAKER_01", 5.0, 8.0, 3.0),
                SpeakerSegment("SPEAKER_00", 8.0, 10.0, 2.0)
            ],
            num_speakers=2,
            speaker_labels=["SPEAKER_00", "SPEAKER_01"],
            duration=10.0,
            method="test"
        )

        stats = service.get_speaker_statistics(result)

        assert "SPEAKER_00" in stats
        assert "SPEAKER_01" in stats
        assert stats["SPEAKER_00"]["total_time"] == 7.0
        assert stats["SPEAKER_01"]["total_time"] == 3.0
        assert stats["SPEAKER_00"]["num_turns"] == 2
        assert stats["SPEAKER_01"]["num_turns"] == 1


class TestTranscriptSegmenter:
    """Tests for TranscriptSegmenter"""

    def test_initialization(self):
        """Test segmenter initialization"""
        segmenter = TranscriptSegmenter()
        assert segmenter is not None

    def test_split_sentences(self):
        """Test sentence splitting"""
        segmenter = TranscriptSegmenter()

        text = "This is the first sentence. This is the second. And the third!"
        sentences = segmenter._split_sentences(text)

        assert len(sentences) >= 3

    def test_segment_by_sentences(self, sample_transcription_segments):
        """Test sentence segmentation"""
        segmenter = TranscriptSegmenter()

        segments = segmenter.segment_by_sentences(
            sample_transcription_segments,
            merge_short=False
        )

        assert len(segments) >= len(sample_transcription_segments)
        assert all(seg.segment_type == 'sentence' for seg in segments)

    def test_segment_by_paragraphs(self, sample_transcription_segments):
        """Test paragraph segmentation"""
        segmenter = TranscriptSegmenter()

        segments = segmenter.segment_by_paragraphs(
            sample_transcription_segments,
            pause_threshold=2.0
        )

        assert len(segments) > 0
        assert all(seg.segment_type == 'paragraph' for seg in segments)

    def test_extract_keywords(self):
        """Test keyword extraction"""
        segmenter = TranscriptSegmenter()

        from src.services.transcript_segmenter import TranscriptSegment

        segment = TranscriptSegment(
            id=0,
            start=0.0,
            end=10.0,
            text="Machine learning and artificial intelligence are transforming technology",
            segment_type="sentence"
        )

        keywords = segmenter.extract_keywords(segment, num_keywords=3)

        assert len(keywords) <= 3
        assert all(isinstance(kw, str) for kw in keywords)

    def test_merge_short_segments(self):
        """Test merging short segments"""
        segmenter = TranscriptSegmenter()

        from src.services.transcript_segmenter import TranscriptSegment

        segments = [
            TranscriptSegment(0, 0.0, 1.0, "Hi.", "sentence"),
            TranscriptSegment(1, 1.0, 2.0, "Hello.", "sentence"),
            TranscriptSegment(2, 2.0, 5.0, "This is a longer sentence with more words.", "sentence")
        ]

        merged = segmenter._merge_short_segments(segments, min_words=5)

        assert len(merged) < len(segments)


class TestAudioFeatureExtractor:
    """Tests for AudioFeatureExtractor"""

    def test_initialization(self):
        """Test extractor initialization"""
        extractor = AudioFeatureExtractor()
        assert extractor is not None

    def test_extract_features_invalid_path(self):
        """Test feature extraction with invalid path"""
        extractor = AudioFeatureExtractor()
        invalid_path = Path("/nonexistent/audio.wav")

        with pytest.raises(ValueError, match="Audio file not found"):
            extractor.extract_features(invalid_path)

    def test_classify_audio_type(self):
        """Test audio type classification"""
        extractor = AudioFeatureExtractor()

        # Test silence detection
        silence_features = AudioFeatures(
            duration=10.0,
            rms_energy=0.005,
            zero_crossing_rate=0.1,
            spectral_centroid_mean=1000.0,
            spectral_centroid_std=100.0,
            spectral_rolloff_mean=2000.0,
            spectral_rolloff_std=200.0,
            spectral_bandwidth_mean=500.0,
            spectral_bandwidth_std=50.0,
            tempo=0.0
        )

        audio_type = extractor.classify_audio_type(silence_features)
        assert audio_type == "silence"

        # Test speech-like features
        speech_features = AudioFeatures(
            duration=10.0,
            rms_energy=0.05,
            zero_crossing_rate=0.16,
            spectral_centroid_mean=1000.0,
            spectral_centroid_std=100.0,
            spectral_rolloff_mean=2000.0,
            spectral_rolloff_std=200.0,
            spectral_bandwidth_mean=500.0,
            spectral_bandwidth_std=50.0,
            tempo=0.0
        )

        audio_type = extractor.classify_audio_type(speech_features)
        assert audio_type in ["speech", "noise"]


class TestLanguageDetector:
    """Tests for LanguageDetector"""

    def test_initialization(self):
        """Test detector initialization"""
        detector = LanguageDetector()
        assert detector is not None

    def test_language_names(self):
        """Test language name mapping"""
        assert LanguageDetector.LANGUAGE_NAMES['en'] == 'English'
        assert LanguageDetector.LANGUAGE_NAMES['es'] == 'Spanish'
        assert LanguageDetector.LANGUAGE_NAMES['fr'] == 'French'

    def test_get_language_name(self):
        """Test getting language name from code"""
        detector = LanguageDetector()

        assert detector.get_language_name('en') == 'English'
        assert detector.get_language_name('es') == 'Spanish'
        assert detector.get_language_name('unknown') == 'unknown'

    def test_is_supported_language(self):
        """Test checking if language is supported"""
        detector = LanguageDetector()

        assert detector.is_supported_language('en') is True
        assert detector.is_supported_language('es') is True
        assert detector.is_supported_language('xyz') is False

    def test_detect_from_text_fallback_chinese(self):
        """Test Chinese character detection"""
        detector = LanguageDetector()

        text = "这是中文文本"
        result = detector._detect_from_text_fallback(text)

        assert result.language == 'zh'
        assert result.language_name == 'Chinese'

    def test_detect_from_text_fallback_japanese(self):
        """Test Japanese character detection"""
        detector = LanguageDetector()

        text = "これは日本語です"
        result = detector._detect_from_text_fallback(text)

        assert result.language == 'ja'

    def test_detect_from_text_fallback_korean(self):
        """Test Korean character detection"""
        detector = LanguageDetector()

        text = "이것은 한국어입니다"
        result = detector._detect_from_text_fallback(text)

        assert result.language == 'ko'

    def test_detect_from_text_fallback_default(self):
        """Test default language detection"""
        detector = LanguageDetector()

        text = "This is English text"
        result = detector._detect_from_text_fallback(text)

        assert result.language == 'en'
        assert result.confidence <= 1.0


class TestAudioProcessingPipeline:
    """Tests for AudioProcessingPipeline"""

    def test_initialization_default(self):
        """Test pipeline initialization with defaults"""
        pipeline = AudioProcessingPipeline()

        assert pipeline.config is not None
        assert isinstance(pipeline.audio_processor, AudioProcessor)
        assert isinstance(pipeline.transcription_service, TranscriptionService)

    def test_initialization_custom_config(self):
        """Test pipeline initialization with custom config"""
        config = AudioPipelineConfig(
            extract_audio=False,
            transcribe=False,
            diarize_speakers=False,
            sample_rate=22050
        )

        pipeline = AudioProcessingPipeline(config)

        assert pipeline.config.extract_audio is False
        assert pipeline.config.transcribe is False
        assert pipeline.config.sample_rate == 22050

    def test_get_pipeline_info(self):
        """Test getting pipeline info"""
        pipeline = AudioProcessingPipeline()
        info = pipeline.get_pipeline_info()

        assert 'extract_audio' in info
        assert 'transcribe' in info
        assert 'sample_rate' in info
        assert 'whisper_model' in info


class TestAudioPipelineConfig:
    """Tests for AudioPipelineConfig"""

    def test_default_config(self):
        """Test default configuration values"""
        config = AudioPipelineConfig()

        assert config.extract_audio is True
        assert config.sample_rate == 16000
        assert config.transcribe is True
        assert config.diarize_speakers is False
        assert config.detect_language is True
        assert config.segment_transcript is True

    def test_custom_config(self):
        """Test custom configuration"""
        config = AudioPipelineConfig(
            sample_rate=22050,
            whisper_model="small",
            diarize_speakers=True,
            segmentation_method="sentence"
        )

        assert config.sample_rate == 22050
        assert config.whisper_model == "small"
        assert config.diarize_speakers is True
        assert config.segmentation_method == "sentence"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
