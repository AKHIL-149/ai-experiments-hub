"""
Audio processing pipeline
Orchestrates complete audio processing workflow
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
import tempfile

from src.services.audio_processor import AudioProcessor
from src.services.transcription_service import (
    TranscriptionService,
    TranscriptionResult
)
from src.services.speaker_diarization import (
    SpeakerDiarization,
    DiarizationResult
)
from src.services.transcript_segmenter import TranscriptSegmenter
from src.services.audio_features import AudioFeatureExtractor, AudioFeatures
from src.services.language_detector import LanguageDetector, LanguageDetection

logger = logging.getLogger(__name__)


@dataclass
class AudioPipelineConfig:
    """Configuration for audio processing pipeline"""
    # Extraction
    extract_audio: bool = True
    sample_rate: int = 16000
    normalize_audio: bool = False
    reduce_noise: bool = False

    # Transcription
    transcribe: bool = True
    transcription_api_key: Optional[str] = None
    use_local_whisper: bool = False
    whisper_model: str = "base"

    # Speaker diarization
    diarize_speakers: bool = False
    hf_token: Optional[str] = None
    min_speakers: Optional[int] = None
    max_speakers: Optional[int] = None

    # Language detection
    detect_language: bool = True

    # Segmentation
    segment_transcript: bool = True
    segmentation_method: str = "paragraph"  # sentence, paragraph, topic

    # Feature extraction
    extract_features: bool = False
    include_mfcc: bool = True

    # Output
    save_transcript: bool = True
    transcript_format: str = "json"  # json, srt, vtt, txt


@dataclass
class AudioPipelineResult:
    """Complete audio processing result"""
    audio_path: Path
    duration: float

    # Processing results
    transcription: Optional[TranscriptionResult] = None
    diarization: Optional[DiarizationResult] = None
    language: Optional[LanguageDetection] = None
    segments: Optional[List] = None
    features: Optional[AudioFeatures] = None

    # Metadata
    processing_time: float = 0.0
    metadata: Optional[Dict[str, any]] = None


class AudioProcessingPipeline:
    """
    Complete audio processing pipeline
    Extracts audio, transcribes, diarizes speakers, segments, and analyzes
    """

    def __init__(self, config: Optional[AudioPipelineConfig] = None):
        """
        Initialize audio processing pipeline

        Args:
            config: Pipeline configuration
        """
        self.config = config or AudioPipelineConfig()

        # Initialize services
        self.audio_processor = AudioProcessor()
        self.transcription_service = TranscriptionService(
            api_key=self.config.transcription_api_key,
            prefer_local=self.config.use_local_whisper,
            model_name=self.config.whisper_model
        )
        self.speaker_diarization = SpeakerDiarization(
            hf_token=self.config.hf_token,
            min_speakers=self.config.min_speakers,
            max_speakers=self.config.max_speakers
        )
        self.transcript_segmenter = TranscriptSegmenter()
        self.feature_extractor = AudioFeatureExtractor()
        self.language_detector = LanguageDetector()

    def process(
        self,
        video_path: Path,
        output_dir: Optional[Path] = None
    ) -> AudioPipelineResult:
        """
        Process video audio through complete pipeline

        Args:
            video_path: Path to video file
            output_dir: Optional output directory for results

        Returns:
            AudioPipelineResult

        Raises:
            ValueError: If video not found
            RuntimeError: If processing fails
        """
        if not video_path.exists():
            raise ValueError(f"Video not found: {video_path}")

        import time
        start_time = time.time()

        logger.info(f"Starting audio processing pipeline for {video_path}")

        # Create output directory if needed
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir()) / "audio_processing"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Extract audio
        audio_path = None
        if self.config.extract_audio:
            audio_path = self._extract_audio(video_path, output_dir)
        else:
            # Assume video_path is actually audio_path
            audio_path = video_path

        # Get audio duration
        audio_info = self.audio_processor.get_audio_info(audio_path)
        duration = audio_info['duration']

        # 2. Transcribe audio
        transcription = None
        if self.config.transcribe:
            transcription = self._transcribe_audio(audio_path)

        # 3. Detect language
        language = None
        if self.config.detect_language:
            language = self._detect_language(audio_path, transcription)

        # 4. Speaker diarization
        diarization = None
        if self.config.diarize_speakers:
            diarization = self._diarize_audio(audio_path)

        # 5. Merge diarization with transcription
        if transcription and diarization:
            transcription.segments = self._merge_speakers(
                transcription.segments,
                diarization
            )

        # 6. Segment transcript
        segments = None
        if self.config.segment_transcript and transcription:
            segments = self._segment_transcript(transcription)

        # 7. Extract audio features
        features = None
        if self.config.extract_features:
            features = self._extract_features(audio_path)

        # 8. Save outputs
        if self.config.save_transcript and transcription:
            self._save_transcript(transcription, output_dir, video_path)

        # Calculate processing time
        processing_time = time.time() - start_time

        result = AudioPipelineResult(
            audio_path=audio_path,
            duration=duration,
            transcription=transcription,
            diarization=diarization,
            language=language,
            segments=segments,
            features=features,
            processing_time=processing_time,
            metadata={
                'video_path': str(video_path),
                'output_dir': str(output_dir),
                'config': {
                    'sample_rate': self.config.sample_rate,
                    'whisper_model': self.config.whisper_model,
                    'segmentation_method': self.config.segmentation_method
                }
            }
        )

        logger.info(
            f"Audio processing complete: {duration:.2f}s audio, "
            f"{processing_time:.2f}s processing time"
        )

        return result

    def _extract_audio(
        self,
        video_path: Path,
        output_dir: Path
    ) -> Path:
        """Extract audio from video"""
        logger.info("Extracting audio from video")

        output_path = output_dir / f"{video_path.stem}_audio.wav"

        audio_path = self.audio_processor.extract_audio(
            video_path,
            output_path=output_path,
            sample_rate=self.config.sample_rate
        )

        # Post-process audio if requested
        if self.config.normalize_audio:
            normalized_path = output_dir / f"{video_path.stem}_normalized.wav"
            audio_path = self.audio_processor.normalize_audio(
                audio_path,
                normalized_path
            )

        if self.config.reduce_noise:
            denoised_path = output_dir / f"{video_path.stem}_denoised.wav"
            audio_path = self.audio_processor.reduce_noise(
                audio_path,
                denoised_path
            )

        return audio_path

    def _transcribe_audio(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe audio"""
        logger.info("Transcribing audio")

        return self.transcription_service.transcribe(audio_path)

    def _detect_language(
        self,
        audio_path: Path,
        transcription: Optional[TranscriptionResult]
    ) -> LanguageDetection:
        """Detect language"""
        logger.info("Detecting language")

        if transcription:
            return self.language_detector.detect_from_transcript(transcription)
        else:
            return self.language_detector.detect_from_audio(audio_path)

    def _diarize_audio(self, audio_path: Path) -> DiarizationResult:
        """Perform speaker diarization"""
        logger.info("Performing speaker diarization")

        return self.speaker_diarization.diarize(audio_path)

    def _merge_speakers(
        self,
        transcription_segments: List,
        diarization: DiarizationResult
    ) -> List:
        """Merge speaker labels with transcription"""
        logger.info("Merging speaker labels with transcription")

        merged = self.speaker_diarization.merge_with_transcription(
            diarization,
            transcription_segments
        )

        # Convert back to TranscriptionSegment objects
        # Update original segments with speaker info
        for i, trans_seg in enumerate(transcription_segments):
            if i < len(merged):
                trans_seg.speaker = merged[i]['speaker']

        return transcription_segments

    def _segment_transcript(
        self,
        transcription: TranscriptionResult
    ) -> List:
        """Segment transcript"""
        logger.info(f"Segmenting transcript by {self.config.segmentation_method}")

        if self.config.segmentation_method == 'sentence':
            return self.transcript_segmenter.segment_by_sentences(
                transcription.segments
            )
        elif self.config.segmentation_method == 'paragraph':
            return self.transcript_segmenter.segment_by_paragraphs(
                transcription.segments
            )
        elif self.config.segmentation_method == 'topic':
            return self.transcript_segmenter.segment_by_topics(
                transcription.segments
            )
        else:
            return transcription.segments

    def _extract_features(self, audio_path: Path) -> AudioFeatures:
        """Extract audio features"""
        logger.info("Extracting audio features")

        return self.feature_extractor.extract_features(
            audio_path,
            include_mfcc=self.config.include_mfcc
        )

    def _save_transcript(
        self,
        transcription: TranscriptionResult,
        output_dir: Path,
        video_path: Path
    ):
        """Save transcript to file"""
        output_path = output_dir / f"{video_path.stem}_transcript.{self.config.transcript_format}"

        self.transcription_service.save_transcript(
            transcription,
            output_path,
            format=self.config.transcript_format
        )

        logger.info(f"Transcript saved to {output_path}")

    def get_pipeline_info(self) -> Dict[str, any]:
        """Get pipeline configuration info"""
        return {
            'extract_audio': self.config.extract_audio,
            'transcribe': self.config.transcribe,
            'diarize_speakers': self.config.diarize_speakers,
            'detect_language': self.config.detect_language,
            'segment_transcript': self.config.segment_transcript,
            'extract_features': self.config.extract_features,
            'sample_rate': self.config.sample_rate,
            'whisper_model': self.config.whisper_model,
            'segmentation_method': self.config.segmentation_method
        }


def process_video_audio(
    video_path: Path,
    config: Optional[AudioPipelineConfig] = None,
    output_dir: Optional[Path] = None
) -> AudioPipelineResult:
    """
    Convenience function to process video audio

    Args:
        video_path: Path to video file
        config: Optional pipeline configuration
        output_dir: Optional output directory

    Returns:
        AudioPipelineResult
    """
    pipeline = AudioProcessingPipeline(config)
    return pipeline.process(video_path, output_dir)
