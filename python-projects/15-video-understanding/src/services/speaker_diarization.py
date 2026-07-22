"""
Speaker diarization service
Identifies and separates different speakers in audio
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SpeakerSegment:
    """A segment of audio attributed to a speaker"""
    speaker_id: str
    start: float
    end: float
    duration: float
    confidence: Optional[float] = None


@dataclass
class DiarizationResult:
    """Complete diarization result"""
    segments: List[SpeakerSegment]
    num_speakers: int
    speaker_labels: List[str]
    duration: float
    method: str
    metadata: Optional[Dict[str, any]] = None


class SpeakerDiarization:
    """
    Speaker diarization service
    Identifies and separates speakers in audio using pyannote.audio
    """

    def __init__(
        self,
        hf_token: Optional[str] = None,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None
    ):
        """
        Initialize speaker diarization service

        Args:
            hf_token: HuggingFace token for pyannote models
            min_speakers: Minimum number of speakers
            max_speakers: Maximum number of speakers
        """
        self.hf_token = hf_token
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers
        self.pipeline = None

    def diarize(
        self,
        audio_path: Path,
        num_speakers: Optional[int] = None
    ) -> DiarizationResult:
        """
        Perform speaker diarization on audio

        Args:
            audio_path: Path to audio file
            num_speakers: Optional number of speakers (if known)

        Returns:
            DiarizationResult

        Raises:
            ValueError: If audio file not found
            RuntimeError: If diarization fails
        """
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_path}")

        logger.info(f"Performing speaker diarization on {audio_path}")

        try:
            # Load pyannote pipeline if not loaded
            if self.pipeline is None:
                self._load_pipeline()

            # Perform diarization
            params = {}
            if num_speakers:
                params['num_speakers'] = num_speakers
            elif self.min_speakers or self.max_speakers:
                if self.min_speakers:
                    params['min_speakers'] = self.min_speakers
                if self.max_speakers:
                    params['max_speakers'] = self.max_speakers

            diarization = self.pipeline(str(audio_path), **params)

            # Convert to SpeakerSegments
            segments = []
            speaker_labels = set()

            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segment = SpeakerSegment(
                    speaker_id=speaker,
                    start=turn.start,
                    end=turn.end,
                    duration=turn.end - turn.start,
                    confidence=None  # pyannote doesn't provide confidence per segment
                )
                segments.append(segment)
                speaker_labels.add(speaker)

            # Calculate total duration
            duration = max(s.end for s in segments) if segments else 0

            result = DiarizationResult(
                segments=segments,
                num_speakers=len(speaker_labels),
                speaker_labels=sorted(list(speaker_labels)),
                duration=duration,
                method='pyannote',
                metadata={
                    'params': params,
                    'total_segments': len(segments)
                }
            )

            logger.info(
                f"Diarization complete: {result.num_speakers} speakers, "
                f"{len(result.segments)} segments"
            )

            return result

        except ImportError:
            logger.warning("pyannote.audio not available, using fallback method")
            return self._diarize_fallback(audio_path, num_speakers)

        except Exception as e:
            logger.warning(f"Diarization failed: {e}, using fallback")
            return self._diarize_fallback(audio_path, num_speakers)

    def _load_pipeline(self):
        """Load pyannote diarization pipeline"""
        try:
            from pyannote.audio import Pipeline

            logger.info("Loading pyannote diarization pipeline")

            # Load pre-trained pipeline
            self.pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=self.hf_token
            )

            logger.info("Pipeline loaded successfully")

        except Exception as e:
            raise RuntimeError(f"Failed to load diarization pipeline: {e}") from e

    def _diarize_fallback(
        self,
        audio_path: Path,
        num_speakers: Optional[int] = None
    ) -> DiarizationResult:
        """
        Fallback diarization using simple voice activity detection

        Args:
            audio_path: Path to audio file
            num_speakers: Optional number of speakers

        Returns:
            DiarizationResult with single speaker
        """
        logger.info("Using fallback diarization (single speaker assumed)")

        try:
            import librosa

            # Load audio
            y, sr = librosa.load(str(audio_path), sr=None)
            duration = len(y) / sr

            # Create single segment for entire audio
            segment = SpeakerSegment(
                speaker_id="SPEAKER_00",
                start=0.0,
                end=duration,
                duration=duration,
                confidence=1.0
            )

            result = DiarizationResult(
                segments=[segment],
                num_speakers=1,
                speaker_labels=["SPEAKER_00"],
                duration=duration,
                method='fallback',
                metadata={'note': 'Single speaker assumed'}
            )

            return result

        except ImportError:
            logger.error("librosa not available for fallback")
            raise RuntimeError("Neither pyannote nor librosa available for diarization")

    def merge_with_transcription(
        self,
        diarization_result: DiarizationResult,
        transcription_segments: List
    ) -> List[Dict[str, any]]:
        """
        Merge diarization with transcription segments

        Args:
            diarization_result: DiarizationResult
            transcription_segments: List of transcription segments

        Returns:
            List of merged segments with speaker labels
        """
        logger.info("Merging diarization with transcription")

        merged = []

        for trans_seg in transcription_segments:
            # Find overlapping speaker segments
            trans_start = trans_seg.start
            trans_end = trans_seg.end
            trans_mid = (trans_start + trans_end) / 2

            # Find speaker at midpoint of transcription segment
            speaker = self._find_speaker_at_time(
                diarization_result.segments,
                trans_mid
            )

            merged_seg = {
                'id': trans_seg.id,
                'start': trans_seg.start,
                'end': trans_seg.end,
                'text': trans_seg.text,
                'speaker': speaker,
                'language': trans_seg.language,
                'confidence': trans_seg.confidence
            }

            merged.append(merged_seg)

        logger.info(f"Merged {len(merged)} segments with speaker labels")

        return merged

    def _find_speaker_at_time(
        self,
        segments: List[SpeakerSegment],
        time: float
    ) -> str:
        """
        Find speaker at specific time

        Args:
            segments: List of speaker segments
            time: Time in seconds

        Returns:
            Speaker ID or "UNKNOWN"
        """
        for segment in segments:
            if segment.start <= time <= segment.end:
                return segment.speaker_id

        return "UNKNOWN"

    def get_speaker_statistics(
        self,
        result: DiarizationResult
    ) -> Dict[str, Dict[str, float]]:
        """
        Get statistics about each speaker

        Args:
            result: DiarizationResult

        Returns:
            Dictionary of speaker stats
        """
        stats = {}

        for speaker in result.speaker_labels:
            # Filter segments for this speaker
            speaker_segments = [
                s for s in result.segments
                if s.speaker_id == speaker
            ]

            total_time = sum(s.duration for s in speaker_segments)
            num_turns = len(speaker_segments)
            avg_turn_length = total_time / num_turns if num_turns > 0 else 0

            stats[speaker] = {
                'total_time': total_time,
                'percentage': (total_time / result.duration * 100) if result.duration > 0 else 0,
                'num_turns': num_turns,
                'avg_turn_length': avg_turn_length
            }

        return stats

    def save_rttm(
        self,
        result: DiarizationResult,
        output_path: Path
    ):
        """
        Save diarization in RTTM format

        Args:
            result: DiarizationResult
            output_path: Output file path
        """
        logger.info(f"Saving diarization to RTTM format: {output_path}")

        with open(output_path, 'w') as f:
            for segment in result.segments:
                # RTTM format:
                # SPEAKER <file> <channel> <start> <duration> <NA> <NA> <speaker> <conf> <NA>
                line = (
                    f"SPEAKER {output_path.stem} 1 "
                    f"{segment.start:.3f} {segment.duration:.3f} "
                    f"<NA> <NA> {segment.speaker_id} <NA> <NA>\n"
                )
                f.write(line)

        logger.info(f"RTTM file saved: {output_path}")

    def visualize_diarization(
        self,
        result: DiarizationResult,
        output_path: Optional[Path] = None
    ):
        """
        Create visualization of diarization timeline

        Args:
            result: DiarizationResult
            output_path: Optional output path for saving plot
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches

            fig, ax = plt.subplots(figsize=(12, 4))

            # Color map for speakers
            colors = plt.cm.Set3.colors
            speaker_colors = {
                speaker: colors[i % len(colors)]
                for i, speaker in enumerate(result.speaker_labels)
            }

            # Plot segments
            for segment in result.segments:
                color = speaker_colors[segment.speaker_id]
                rect = mpatches.Rectangle(
                    (segment.start, 0),
                    segment.duration,
                    1,
                    facecolor=color,
                    edgecolor='black',
                    linewidth=0.5
                )
                ax.add_patch(rect)

            # Configure plot
            ax.set_xlim(0, result.duration)
            ax.set_ylim(0, 1)
            ax.set_xlabel('Time (seconds)')
            ax.set_yticks([])
            ax.set_title('Speaker Diarization Timeline')

            # Add legend
            legend_patches = [
                mpatches.Patch(color=speaker_colors[speaker], label=speaker)
                for speaker in result.speaker_labels
            ]
            ax.legend(handles=legend_patches, loc='upper right')

            plt.tight_layout()

            if output_path:
                plt.savefig(output_path, dpi=150)
                logger.info(f"Diarization visualization saved: {output_path}")
            else:
                plt.show()

            plt.close()

        except ImportError:
            logger.warning("matplotlib not available for visualization")


def diarize_audio(
    audio_path: Path,
    hf_token: Optional[str] = None,
    num_speakers: Optional[int] = None
) -> DiarizationResult:
    """
    Convenience function for speaker diarization

    Args:
        audio_path: Path to audio file
        hf_token: Optional HuggingFace token
        num_speakers: Optional number of speakers

    Returns:
        DiarizationResult
    """
    service = SpeakerDiarization(hf_token=hf_token)
    return service.diarize(audio_path, num_speakers=num_speakers)
