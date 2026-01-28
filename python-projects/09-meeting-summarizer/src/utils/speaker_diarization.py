"""Speaker Diarization - Identify individual speakers - Phase 5

Note: This module requires pyannote.audio and a Hugging Face token.
It is optional and will gracefully degrade if not available.
"""

import logging
from typing import Optional, List, Dict, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class SpeakerDiarization:
    """
    Speaker diarization using pyannote.audio

    Identifies different speakers in audio and assigns segments to speakers.
    """

    def __init__(self, hf_token: Optional[str] = None):
        """
        Initialize Speaker Diarization

        Args:
            hf_token: Hugging Face authentication token (required for pyannote.audio)
        """
        self.hf_token = hf_token
        self.pipeline = None
        self.is_available = False

        self._initialize_pipeline()

    def _initialize_pipeline(self):
        """Initialize the diarization pipeline"""
        try:
            from pyannote.audio import Pipeline

            if not self.hf_token:
                logger.warning("Speaker diarization requires HF_AUTH_TOKEN environment variable")
                return

            # Load pretrained pipeline
            self.pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=self.hf_token
            )

            self.is_available = True
            logger.info("Speaker diarization initialized successfully")

        except ImportError:
            logger.warning(
                "pyannote.audio not installed. Speaker diarization unavailable. "
                "Install with: pip install pyannote.audio"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize speaker diarization: {str(e)}")

    def diarize(
        self,
        audio_path: str,
        num_speakers: Optional[int] = None,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None
    ) -> Optional[List[Dict]]:
        """
        Perform speaker diarization on audio file

        Args:
            audio_path: Path to audio file
            num_speakers: Exact number of speakers (if known)
            min_speakers: Minimum number of speakers
            max_speakers: Maximum number of speakers

        Returns:
            List of speaker segments:
            [
                {
                    "start": 0.0,
                    "end": 5.2,
                    "speaker": "SPEAKER_00",
                    "duration": 5.2
                },
                ...
            ]
            Returns None if diarization is not available
        """
        if not self.is_available:
            logger.warning("Speaker diarization not available")
            return None

        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            logger.info(f"Starting speaker diarization for {Path(audio_path).name}...")

            # Prepare parameters
            params = {}
            if num_speakers:
                params['num_speakers'] = num_speakers
            if min_speakers:
                params['min_speakers'] = min_speakers
            if max_speakers:
                params['max_speakers'] = max_speakers

            # Run diarization
            diarization = self.pipeline(audio_path, **params)

            # Convert to list of segments
            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segments.append({
                    'start': turn.start,
                    'end': turn.end,
                    'speaker': speaker,
                    'duration': turn.end - turn.start
                })

            logger.info(f"Diarization complete: found {len(set(s['speaker'] for s in segments))} speakers")

            return segments

        except Exception as e:
            logger.error(f"Speaker diarization failed: {str(e)}")
            return None

    def assign_transcript_to_speakers(
        self,
        transcript: str,
        segments: List[Dict],
        timestamps: Optional[List[Tuple[float, float]]] = None
    ) -> List[Dict]:
        """
        Assign transcript segments to speakers

        Args:
            transcript: Full transcript text
            segments: Diarization segments from diarize()
            timestamps: Optional list of (start, end) timestamps for transcript segments

        Returns:
            List of speaker-annotated transcript segments:
            [
                {
                    "speaker": "SPEAKER_00",
                    "text": "Hello everyone...",
                    "start": 0.0,
                    "end": 5.2
                },
                ...
            ]
        """
        if not segments:
            return [{"speaker": "SPEAKER_00", "text": transcript, "start": 0, "end": 0}]

        # If no timestamps, split transcript by sentences
        if not timestamps:
            sentences = self._split_into_sentences(transcript)
            # Estimate timestamps based on segment distribution
            total_duration = segments[-1]['end'] if segments else 0
            estimated_timestamps = []
            segment_duration = total_duration / len(sentences) if sentences else 0

            for i in range(len(sentences)):
                start = i * segment_duration
                end = (i + 1) * segment_duration
                estimated_timestamps.append((start, end))

            timestamps = estimated_timestamps

        # Assign each transcript segment to a speaker
        speaker_transcript = []
        for (start, end), text in zip(timestamps, self._split_into_sentences(transcript)):
            # Find overlapping speaker segment
            speaker = self._find_speaker_at_time(segments, (start + end) / 2)
            speaker_transcript.append({
                'speaker': speaker,
                'text': text.strip(),
                'start': start,
                'end': end
            })

        return speaker_transcript

    def format_speaker_transcript(self, speaker_segments: List[Dict]) -> str:
        """
        Format speaker-annotated transcript for display

        Args:
            speaker_segments: Output from assign_transcript_to_speakers()

        Returns:
            Formatted transcript with speaker labels
        """
        formatted = []
        current_speaker = None

        for segment in speaker_segments:
            if segment['speaker'] != current_speaker:
                formatted.append(f"\n{segment['speaker']}:")
                current_speaker = segment['speaker']

            formatted.append(f"  {segment['text']}")

        return "\n".join(formatted)

    def get_speaker_statistics(self, segments: List[Dict]) -> Dict:
        """
        Calculate speaker statistics

        Args:
            segments: Diarization segments

        Returns:
            Dictionary with speaker statistics
        """
        if not segments:
            return {}

        speaker_times = {}
        for segment in segments:
            speaker = segment['speaker']
            duration = segment['duration']

            if speaker not in speaker_times:
                speaker_times[speaker] = {
                    'total_time': 0,
                    'num_segments': 0
                }

            speaker_times[speaker]['total_time'] += duration
            speaker_times[speaker]['num_segments'] += 1

        # Calculate percentages
        total_time = sum(s['total_time'] for s in speaker_times.values())

        for speaker in speaker_times:
            speaker_times[speaker]['percentage'] = (
                speaker_times[speaker]['total_time'] / total_time * 100
                if total_time > 0 else 0
            )

        return {
            'speakers': speaker_times,
            'total_speakers': len(speaker_times),
            'total_duration': total_time
        }

    def _find_speaker_at_time(self, segments: List[Dict], timestamp: float) -> str:
        """Find which speaker is speaking at a given timestamp"""
        for segment in segments:
            if segment['start'] <= timestamp <= segment['end']:
                return segment['speaker']

        # If no exact match, find closest segment
        if segments:
            closest = min(segments, key=lambda s: abs((s['start'] + s['end'])/2 - timestamp))
            return closest['speaker']

        return "SPEAKER_00"

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences (simple implementation)"""
        import re

        # Split on sentence boundaries
        sentences = re.split(r'[.!?]+\s+', text)

        # Filter out empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]

        return sentences


# Convenience function for when diarization is not available
def create_speaker_diarization(hf_token: Optional[str] = None) -> Optional[SpeakerDiarization]:
    """
    Create speaker diarization instance if available

    Args:
        hf_token: Hugging Face token

    Returns:
        SpeakerDiarization instance or None if not available
    """
    try:
        diarizer = SpeakerDiarization(hf_token=hf_token)
        if diarizer.is_available:
            return diarizer
        return None
    except Exception as e:
        logger.warning(f"Failed to create speaker diarization: {e}")
        return None
