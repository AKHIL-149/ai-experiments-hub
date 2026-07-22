"""
Transcription service
Handles audio transcription using Whisper (API and local)
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List, Literal
from dataclasses import dataclass
import os

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    """A segment of transcribed audio"""
    id: int
    start: float
    end: float
    text: str
    confidence: Optional[float] = None
    language: Optional[str] = None
    speaker: Optional[str] = None
    words: Optional[List[Dict[str, any]]] = None


@dataclass
class TranscriptionResult:
    """Complete transcription result"""
    text: str
    segments: List[TranscriptionSegment]
    language: str
    duration: float
    source: str  # 'api' or 'local'
    model: str
    metadata: Optional[Dict[str, any]] = None


class TranscriptionService:
    """
    Audio transcription service using OpenAI Whisper
    Supports both API and local model
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        prefer_local: bool = False,
        model_name: str = "base"
    ):
        """
        Initialize transcription service

        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env if None)
            prefer_local: Prefer local model over API
            model_name: Whisper model name (tiny, base, small, medium, large)
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.prefer_local = prefer_local
        self.model_name = model_name
        self.local_model = None

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        task: Literal["transcribe", "translate"] = "transcribe",
        use_local: Optional[bool] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio file

        Args:
            audio_path: Path to audio file
            language: Optional language code (e.g., 'en', 'es')
            task: Task type (transcribe or translate to English)
            use_local: Force use of local/API (overrides prefer_local)

        Returns:
            TranscriptionResult

        Raises:
            ValueError: If audio file not found
            RuntimeError: If transcription fails
        """
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_path}")

        logger.info(f"Transcribing {audio_path} (language={language}, task={task})")

        # Determine which method to use
        use_local_model = use_local if use_local is not None else self.prefer_local

        try:
            if use_local_model:
                result = self._transcribe_local(audio_path, language, task)
            else:
                result = self._transcribe_api(audio_path, language, task)

            logger.info(
                f"Transcription complete: {len(result.segments)} segments, "
                f"{result.duration:.2f}s, language={result.language}"
            )

            return result

        except Exception as e:
            # Fallback to alternative method if available
            if use_local_model and self.api_key:
                logger.warning(f"Local transcription failed, trying API: {e}")
                return self._transcribe_api(audio_path, language, task)
            elif not use_local_model:
                logger.warning(f"API transcription failed, trying local: {e}")
                return self._transcribe_local(audio_path, language, task)
            else:
                raise RuntimeError(f"Transcription failed: {e}") from e

    def _transcribe_api(
        self,
        audio_path: Path,
        language: Optional[str],
        task: str
    ) -> TranscriptionResult:
        """Transcribe using OpenAI Whisper API"""
        if not self.api_key:
            raise RuntimeError("No OpenAI API key provided")

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)

            logger.debug(f"Using Whisper API for transcription")

            with open(audio_path, 'rb') as audio_file:
                # Call Whisper API with timestamp granularities
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )

            # Convert API response to TranscriptionResult
            segments = []
            for idx, segment in enumerate(response.segments or []):
                seg = TranscriptionSegment(
                    id=idx,
                    start=segment.get('start', 0),
                    end=segment.get('end', 0),
                    text=segment.get('text', ''),
                    confidence=None,  # API doesn't provide confidence
                    language=response.language
                )
                segments.append(seg)

            result = TranscriptionResult(
                text=response.text,
                segments=segments,
                language=response.language,
                duration=response.duration if hasattr(response, 'duration') else 0,
                source='api',
                model='whisper-1',
                metadata={'task': task}
            )

            return result

        except ImportError:
            raise RuntimeError(
                "openai package not installed. Install with: pip install openai"
            )
        except Exception as e:
            raise RuntimeError(f"API transcription failed: {e}") from e

    def _transcribe_local(
        self,
        audio_path: Path,
        language: Optional[str],
        task: str
    ) -> TranscriptionResult:
        """Transcribe using local Whisper model"""
        try:
            import whisper

            # Load model if not already loaded
            if self.local_model is None:
                logger.info(f"Loading Whisper model: {self.model_name}")
                self.local_model = whisper.load_model(self.model_name)

            logger.debug(f"Using local Whisper model for transcription")

            # Transcribe
            options = {
                'task': task,
                'verbose': False
            }

            if language:
                options['language'] = language

            result = self.local_model.transcribe(str(audio_path), **options)

            # Convert to TranscriptionResult
            segments = []
            for idx, segment in enumerate(result.get('segments', [])):
                # Extract word-level timestamps if available
                words = None
                if 'words' in segment:
                    words = segment['words']

                seg = TranscriptionSegment(
                    id=idx,
                    start=segment.get('start', 0),
                    end=segment.get('end', 0),
                    text=segment.get('text', '').strip(),
                    confidence=segment.get('confidence'),
                    language=result.get('language'),
                    words=words
                )
                segments.append(seg)

            # Calculate duration from segments
            duration = segments[-1].end if segments else 0

            transcription_result = TranscriptionResult(
                text=result.get('text', ''),
                segments=segments,
                language=result.get('language', language or 'unknown'),
                duration=duration,
                source='local',
                model=self.model_name,
                metadata={'task': task}
            )

            return transcription_result

        except ImportError:
            raise RuntimeError(
                "whisper package not installed. Install with: pip install openai-whisper"
            )
        except Exception as e:
            raise RuntimeError(f"Local transcription failed: {e}") from e

    def transcribe_batch(
        self,
        audio_paths: List[Path],
        language: Optional[str] = None
    ) -> List[TranscriptionResult]:
        """
        Transcribe multiple audio files

        Args:
            audio_paths: List of audio file paths
            language: Optional language code

        Returns:
            List of TranscriptionResult
        """
        logger.info(f"Batch transcribing {len(audio_paths)} audio files")

        results = []
        for idx, audio_path in enumerate(audio_paths):
            try:
                logger.info(f"Transcribing {idx + 1}/{len(audio_paths)}: {audio_path.name}")
                result = self.transcribe(audio_path, language=language)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to transcribe {audio_path}: {e}")
                # Add empty result
                results.append(TranscriptionResult(
                    text="",
                    segments=[],
                    language=language or "unknown",
                    duration=0,
                    source="error",
                    model="none",
                    metadata={'error': str(e)}
                ))

        logger.info(f"Batch transcription complete: {len(results)} results")
        return results

    def get_transcript_text(self, result: TranscriptionResult) -> str:
        """
        Get full transcript text

        Args:
            result: TranscriptionResult

        Returns:
            Full transcript text
        """
        return result.text

    def get_transcript_with_timestamps(
        self,
        result: TranscriptionResult,
        format: Literal["srt", "vtt", "txt"] = "txt"
    ) -> str:
        """
        Get transcript with timestamps in specified format

        Args:
            result: TranscriptionResult
            format: Output format (srt, vtt, txt)

        Returns:
            Formatted transcript string
        """
        if format == "srt":
            return self._format_srt(result.segments)
        elif format == "vtt":
            return self._format_vtt(result.segments)
        else:
            return self._format_txt(result.segments)

    def _format_srt(self, segments: List[TranscriptionSegment]) -> str:
        """Format as SRT subtitle format"""
        lines = []

        for segment in segments:
            start = self._format_timestamp(segment.start, srt=True)
            end = self._format_timestamp(segment.end, srt=True)

            lines.append(f"{segment.id + 1}")
            lines.append(f"{start} --> {end}")
            lines.append(segment.text)
            lines.append("")  # Blank line

        return "\n".join(lines)

    def _format_vtt(self, segments: List[TranscriptionSegment]) -> str:
        """Format as WebVTT subtitle format"""
        lines = ["WEBVTT", ""]

        for segment in segments:
            start = self._format_timestamp(segment.start)
            end = self._format_timestamp(segment.end)

            lines.append(f"{start} --> {end}")
            lines.append(segment.text)
            lines.append("")

        return "\n".join(lines)

    def _format_txt(self, segments: List[TranscriptionSegment]) -> str:
        """Format as plain text with timestamps"""
        lines = []

        for segment in segments:
            timestamp = self._format_timestamp(segment.start)
            lines.append(f"[{timestamp}] {segment.text}")

        return "\n".join(lines)

    def _format_timestamp(self, seconds: float, srt: bool = False) -> str:
        """
        Format timestamp

        Args:
            seconds: Time in seconds
            srt: Use SRT format (comma) instead of VTT (period)

        Returns:
            Formatted timestamp
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        separator = "," if srt else "."

        return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"

    def save_transcript(
        self,
        result: TranscriptionResult,
        output_path: Path,
        format: Literal["json", "srt", "vtt", "txt"] = "txt"
    ):
        """
        Save transcript to file

        Args:
            result: TranscriptionResult
            output_path: Output file path
            format: Output format
        """
        logger.info(f"Saving transcript to {output_path} (format={format})")

        if format == "json":
            import json

            data = {
                'text': result.text,
                'language': result.language,
                'duration': result.duration,
                'segments': [
                    {
                        'id': s.id,
                        'start': s.start,
                        'end': s.end,
                        'text': s.text,
                        'confidence': s.confidence,
                        'speaker': s.speaker
                    }
                    for s in result.segments
                ]
            }

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        else:
            content = self.get_transcript_with_timestamps(result, format=format)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)

        logger.info(f"Transcript saved to {output_path}")


def transcribe_audio(
    audio_path: Path,
    api_key: Optional[str] = None,
    language: Optional[str] = None,
    use_local: bool = False
) -> TranscriptionResult:
    """
    Convenience function to transcribe audio

    Args:
        audio_path: Path to audio file
        api_key: Optional OpenAI API key
        language: Optional language code
        use_local: Use local model instead of API

    Returns:
        TranscriptionResult
    """
    service = TranscriptionService(api_key=api_key, prefer_local=use_local)
    return service.transcribe(audio_path, language=language)
