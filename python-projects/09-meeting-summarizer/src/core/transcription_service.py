"""Transcription Service - Multi-backend audio transcription"""

import json
import os
import re
import shutil
import tempfile
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional
from openai import OpenAI
import subprocess

from .audio_processor import AudioProcessor
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

# OpenAI's transcription endpoint rejects files over 25 MB; stay under it.
OPENAI_MAX_UPLOAD_BYTES = 24 * 1024 * 1024

# A transcript shorter than this is not a meeting: it is what Whisper invents
# for silence or noise ("you", "Thank you.").
MIN_TRANSCRIPT_WORDS = 3

LANGUAGE_PATTERN = re.compile(r'^(auto|[a-z]{2,3})$')


class NoSpeechError(RuntimeError):
    """The recording contains no (intelligible) speech"""


def clean_transcript_text(text: str) -> str:
    """
    Whisper describes non-speech sounds in brackets - "[BLANK_AUDIO]", "[ Inaudible ]",
    "[ Foreign Language ]", "(airplane engine roaring)", "*music*", "♪ ... ♪". They are
    not something anyone said and they must not reach the summary. Speaker-change marks
    (">>") are kept.
    """
    text = re.sub(r'\[[^\]]*\]', ' ', text or '')
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = re.sub(r'\*[^*]*\*', ' ', text)
    text = re.sub(r'[♪♫]+', ' ', text)
    return re.sub(r'[ \t]+', ' ', text).strip()


class TranscriptionService:
    """
    Handles audio transcription using multiple backends:
    1. OpenAI Whisper API (primary - cloud-based)
    2. Whisper.cpp (fallback - local offline)
    """

    def __init__(
        self,
        backend: str = "openai",
        api_key: Optional[str] = None,
        model: str = "whisper-1",
        cache_manager: Optional[CacheManager] = None,
        audio_processor: Optional[AudioProcessor] = None,
        whisper_cpp_path: Optional[str] = None,
        whisper_model_path: Optional[str] = None,
        temp_dir: str = "./data/temp"
    ):
        """
        Initialize Transcription Service

        Args:
            backend: "openai" or "whisper-cpp"
            api_key: OpenAI API key (required for openai backend)
            model: Model name (whisper-1 for OpenAI)
            cache_manager: CacheManager instance for caching
            audio_processor: AudioProcessor instance for audio operations
            whisper_cpp_path: Path to whisper.cpp binary (for local backend)
            whisper_model_path: Path to whisper model file (for local backend)
            temp_dir: Where per-request working directories are created
        """
        self.backend = backend
        self.model = model
        self.cache_manager = cache_manager
        self.audio_processor = audio_processor or AudioProcessor()
        self.temp_dir = Path(temp_dir)

        # Initialize backend
        if backend == "openai":
            if not api_key:
                raise ValueError("OpenAI API key is required for openai backend")
            self.client = OpenAI(api_key=api_key)
            logger.info("Initialized OpenAI Whisper backend")

        elif backend == "whisper-cpp":
            self.whisper_cpp_path = whisper_cpp_path
            self.whisper_model_path = whisper_model_path
            self._validate_whisper_cpp()
            logger.info("Initialized Whisper.cpp backend")

        else:
            raise ValueError(f"Unsupported backend: {backend}. Use 'openai' or 'whisper-cpp'")

    def _validate_whisper_cpp(self):
        """Validate that whisper.cpp binary and model exist"""
        if not self.whisper_cpp_path or not Path(self.whisper_cpp_path).exists():
            raise FileNotFoundError(
                f"Whisper.cpp binary not found: {self.whisper_cpp_path}"
            )

        if not self.whisper_model_path or not Path(self.whisper_model_path).exists():
            raise FileNotFoundError(
                f"Whisper model file not found: {self.whisper_model_path}"
            )

        logger.info(f"Whisper.cpp validated: {self.whisper_cpp_path}")
        logger.info(f"Whisper model: {self.whisper_model_path}")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def validate_language(language: Optional[str]) -> Optional[str]:
        """A language code ("en", "es", "auto") or None; anything else is a ValueError"""
        if language is None or language == '':
            return None
        if not isinstance(language, str) or not LANGUAGE_PATTERN.match(language):
            raise ValueError(f"Invalid language '{language}'. Use a short code such as 'en' or 'es', or 'auto'.")
        return language

    def _model_id(self) -> str:
        """Identifies the model for cache keys: a different model is a different transcript"""
        if self.backend == "whisper-cpp":
            return Path(self.whisper_model_path).stem
        return self.model

    def _cache_variant(self, language: Optional[str]) -> str:
        return f"{self.backend}_{self._model_id()}_{language or 'default'}"

    def _english_only_model(self) -> bool:
        return self.backend == "whisper-cpp" and Path(self.whisper_model_path).stem.endswith('.en')

    def _finalize(self, result: Dict) -> Dict:
        """
        Clean the text of non-speech annotations and refuse a transcript with no speech.
        Segments (when the backend gave them) are cleaned the same way and empty ones dropped.
        """
        segments = []
        for segment in result.get("segments") or []:
            text = clean_transcript_text(segment.get("text", ""))
            if text:
                segments.append({"start": segment["start"], "end": segment["end"], "text": text})

        if segments:
            text = "\n".join(segment["text"] for segment in segments)
            result["segments"] = segments
        else:
            result.pop("segments", None)
            text = "\n".join(
                line for line in (clean_transcript_text(l) for l in (result.get("text") or "").split("\n")) if line
            )

        if len(text.split()) < MIN_TRANSCRIPT_WORDS:
            raise NoSpeechError("No speech was detected in this recording.")

        result["text"] = text
        return result

    # ------------------------------------------------------------------ main entry

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict:
        """
        Transcribe audio file with caching support

        Args:
            audio_path: Path to audio file
            language: Language code (e.g., "en", "es") - optional
            use_cache: Whether to use cache

        Returns:
            dict with transcription result:
                {
                    "text": str,
                    "language": str,
                    "duration": float,
                    "segments": List[dict] ({"start", "end", "text"}, seconds),
                    "cached": bool,
                    "backend": str
                }

        Raises:
            NoSpeechError: the recording is silent or has no intelligible speech
            ValueError: invalid language, or a language the local model cannot do
        """
        language = self.validate_language(language)
        if language and language not in ('en', 'auto') and self._english_only_model():
            raise ValueError(
                f"The local Whisper model ({self._model_id()}) only understands English. "
                f"Use a multilingual model (for example ggml-base.bin) for language '{language}'."
            )

        variant = self._cache_variant(language)

        # Check cache first
        if use_cache and self.cache_manager:
            audio_hash = self.audio_processor.get_file_hash(audio_path)
            cached_result = self.cache_manager.get_transcription(audio_hash, variant)

            if cached_result:
                logger.info(f"Using cached transcription for {audio_path}")
                cached_result["cached"] = True
                return cached_result

        # Load once: duration for the result, and the silence check before any model runs
        audio = self.audio_processor.load_audio(audio_path)
        duration = self.audio_processor.get_duration(audio)

        if self.audio_processor.is_silent(audio):
            # Whisper invents words ("you", "Thank you.") for silence - do not even ask it
            raise NoSpeechError("No speech was detected in this recording.")

        logger.info(f"Transcribing: {audio_path} ({duration:.1f}s)")

        # Transcribe based on backend
        if self.backend == "openai":
            if Path(audio_path).stat().st_size > OPENAI_MAX_UPLOAD_BYTES:
                logger.info("File is over the API upload limit - transcribing in chunks")
                result = self._transcribe_openai_chunked(audio, language)
            else:
                result = self._transcribe_openai(audio_path, language)
        elif self.backend == "whisper-cpp":
            result = self._transcribe_whisper_cpp(audio, duration, language)
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

        result = self._finalize(result)

        # Add metadata
        result["duration"] = duration
        result["cached"] = False
        result["backend"] = self.backend

        # Cache the result
        if use_cache and self.cache_manager:
            audio_hash = self.audio_processor.get_file_hash(audio_path)
            self.cache_manager.set_transcription(audio_hash, result, variant)

        return result

    # ------------------------------------------------------------------ OpenAI

    def _transcribe_openai(self, audio_path: str, language: Optional[str]) -> Dict:
        """
        Transcribe using OpenAI Whisper API

        Args:
            audio_path: Path to audio file
            language: Language code (optional)

        Returns:
            dict with transcription result
        """
        try:
            with open(audio_path, "rb") as audio_file:
                # Call OpenAI Whisper API
                params = {
                    "model": self.model,
                    "file": audio_file,
                    "response_format": "verbose_json"
                }

                if language and language != 'auto':
                    params["language"] = language

                logger.info(f"Calling OpenAI Whisper API (model: {self.model})")
                start_time = time.time()

                response = self.client.audio.transcriptions.create(**params)

                elapsed = time.time() - start_time
                logger.info(f"Transcription completed in {elapsed:.2f}s")

                # Parse response
                result = {
                    "text": response.text,
                    "language": response.language if hasattr(response, 'language') else language or "unknown",
                }

                # Add segments if available
                if hasattr(response, 'segments') and response.segments:
                    result["segments"] = [
                        {
                            "start": seg.start,
                            "end": seg.end,
                            "text": seg.text
                        }
                        for seg in response.segments
                    ]

                return result

        except Exception as e:
            logger.error(f"OpenAI transcription failed: {str(e)}")
            raise RuntimeError(f"OpenAI transcription failed: {str(e)}")

    def _transcribe_openai_chunked(self, audio, language: Optional[str], chunk_minutes: int = 10, overlap_seconds: int = 5) -> Dict:
        """
        Transcribe audio too big for one API call: cut it into overlapping chunks
        (16 kHz mono, about 19 MB per 10 minutes), transcribe each and merge.
        """
        chunks = self.audio_processor.split_audio(audio, chunk_minutes, overlap_seconds)
        work_dir = Path(tempfile.mkdtemp(prefix="chunks_", dir=self._ensure_temp_dir()))
        try:
            transcripts = []
            for i, chunk in enumerate(chunks):
                chunk_path = work_dir / f"chunk_{i}.wav"
                self.audio_processor.export_audio(
                    chunk.set_frame_rate(16000).set_channels(1), str(chunk_path), format="wav"
                )
                logger.info(f"Transcribing chunk {i + 1}/{len(chunks)}")
                transcripts.append(self._transcribe_openai(str(chunk_path), language))
            return self._merge_transcripts(transcripts, chunk_minutes, overlap_seconds)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ------------------------------------------------------------------ whisper.cpp

    def _ensure_temp_dir(self) -> Path:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        return self.temp_dir

    def _transcribe_whisper_cpp(self, audio, duration: float, language: Optional[str]) -> Dict:
        """
        Transcribe using local Whisper.cpp

        Works in a private temporary directory (so two jobs can never share or delete each
        other's files, and nothing is left behind after a failure) and asks for JSON output,
        which carries a start and end time for every segment.

        Args:
            audio: Loaded AudioSegment
            duration: Length in seconds (scales the timeout)
            language: Language code (optional)

        Returns:
            dict with transcription result
        """
        work_dir = Path(tempfile.mkdtemp(prefix="whisper_", dir=self._ensure_temp_dir()))
        try:
            wav_path = work_dir / "audio.wav"
            # whisper.cpp wants 16 kHz mono; converting here also keeps the temp file small
            self.audio_processor.export_audio(
                audio.set_frame_rate(16000).set_channels(1), str(wav_path), format="wav"
            )

            output_prefix = work_dir / "result"
            cmd = [
                self.whisper_cpp_path,
                "-m", self.whisper_model_path,
                "-f", str(wav_path),
                "--output-json",
                "--output-file", str(output_prefix),
                "--max-len", "100",          # short segments: finer timing for speaker labels
                "--split-on-word",
                "--no-prints",
            ]

            if language:
                cmd.extend(["-l", language])
            elif not self._english_only_model():
                cmd.extend(["-l", "auto"])   # multilingual model: detect, instead of assuming English

            logger.info(f"Running whisper.cpp: {' '.join(cmd)}")
            start_time = time.time()

            # Run whisper.cpp. The timeout grows with the recording: a fixed 10 minutes is
            # fine for an hour of audio on a fast machine, not for a slow one.
            timeout = max(600, int(duration * 1.5))
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            elapsed = time.time() - start_time

            if process.returncode != 0:
                logger.error(f"Whisper.cpp exited with code {process.returncode}: {process.stderr[-500:]}")
                raise RuntimeError(f"Whisper.cpp failed (exit code {process.returncode})")

            logger.info(f"Transcription completed in {elapsed:.2f}s")

            json_file = Path(f"{output_prefix}.json")
            if not json_file.exists():
                raise RuntimeError("Whisper.cpp produced no output")

            data = json.loads(json_file.read_text(encoding='utf-8'))

            segments = [
                {
                    "start": item["offsets"]["from"] / 1000.0,
                    "end": item["offsets"]["to"] / 1000.0,
                    "text": item.get("text", "")
                }
                for item in data.get("transcription", [])
            ]

            return {
                "text": "\n".join(seg["text"].strip() for seg in segments),
                "segments": segments,
                "language": (data.get("result") or {}).get("language") or language or "unknown"
            }

        except subprocess.TimeoutExpired:
            logger.error("Whisper.cpp timeout")
            raise RuntimeError("Whisper.cpp transcription timed out")

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ------------------------------------------------------------------ chunked (public)

    def transcribe_chunked(
        self,
        audio_path: str,
        chunk_duration_minutes: int = 10,
        overlap_seconds: int = 5,
        language: Optional[str] = None
    ) -> Dict:
        """
        Transcribe long audio by splitting into chunks

        Args:
            audio_path: Path to audio file
            chunk_duration_minutes: Duration of each chunk
            overlap_seconds: Overlap between chunks
            language: Language code (optional)

        Returns:
            dict with merged transcription result
        """
        logger.info(f"Starting chunked transcription: {audio_path}")
        language = self.validate_language(language)

        # Load and split audio
        audio = self.audio_processor.load_audio(audio_path)
        chunks = self.audio_processor.split_audio(
            audio,
            chunk_duration_minutes=chunk_duration_minutes,
            overlap_seconds=overlap_seconds
        )

        if len(chunks) == 1:
            # Audio is short enough, transcribe directly
            logger.info("Audio is short, using single transcription")
            return self.transcribe(audio_path, language=language)

        logger.info(f"Processing {len(chunks)} chunks")

        work_dir = Path(tempfile.mkdtemp(prefix="chunks_", dir=self._ensure_temp_dir()))
        try:
            transcripts = []
            for i, chunk in enumerate(chunks):
                chunk_path = work_dir / f"chunk_{i}.wav"
                self.audio_processor.export_audio(
                    chunk.set_frame_rate(16000).set_channels(1), str(chunk_path), format="wav"
                )
                logger.info(f"Transcribing chunk {i+1}/{len(chunks)}")
                try:
                    transcripts.append(self.transcribe(str(chunk_path), language=language, use_cache=False))
                except NoSpeechError:
                    # A long pause in the middle of a meeting is not a failure; keep the
                    # chunk's place in the timeline with an empty transcript.
                    logger.info(f"Chunk {i+1} has no speech - skipping it")
                    transcripts.append({"text": "", "segments": [], "language": language or "unknown"})

            merged = self._finalize(self._merge_transcripts(transcripts, chunk_duration_minutes, overlap_seconds))

            # Add metadata
            merged["duration"] = self.audio_processor.get_duration(audio)
            merged["cached"] = False
            merged["backend"] = self.backend
            merged["chunks_processed"] = len(chunks)

            return merged

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _merge_transcripts(
        self,
        transcripts: List[Dict],
        chunk_duration_minutes: int,
        overlap_seconds: int
    ) -> Dict:
        """
        Merge multiple transcript chunks into single transcript

        Chunks overlap, so the start of each later chunk repeats the end of the one before.
        When segment times are available, segments that begin inside the overlap are dropped;
        otherwise the first few words of the chunk are skipped as an approximation.

        Args:
            transcripts: List of transcript dicts
            chunk_duration_minutes: Duration of each chunk
            overlap_seconds: Overlap between chunks

        Returns:
            Merged transcript dict
        """
        if not transcripts:
            return {"text": "", "language": "unknown", "segments": []}

        language = transcripts[0].get("language", "unknown")
        chunk_seconds = chunk_duration_minutes * 60
        step = chunk_seconds - overlap_seconds

        texts = []
        merged_segments = []

        for i, transcript in enumerate(transcripts):
            offset = i * step
            segments = transcript.get("segments")

            if segments:
                for seg in segments:
                    if i > 0 and seg["start"] < overlap_seconds:
                        continue          # repeated from the end of the previous chunk
                    merged_segments.append({
                        "start": seg["start"] + offset,
                        "end": seg["end"] + offset,
                        "text": seg["text"]
                    })
                continue

            text = transcript.get("text", "").strip()
            if i > 0 and overlap_seconds > 0:
                words = text.split()
                skip_words = max(1, int(len(words) * (overlap_seconds / chunk_seconds)))
                text = " ".join(words[skip_words:])
            texts.append(text)

        if merged_segments:
            result = {
                "text": "\n".join(seg["text"].strip() for seg in merged_segments),
                "language": language,
                "segments": merged_segments
            }
        else:
            result = {"text": " ".join(texts).strip(), "language": language}

        logger.info(f"Merged {len(transcripts)} transcripts into {len(result['text'])} characters")

        return result

    def get_supported_formats(self) -> List[str]:
        """Get list of supported audio formats"""
        return self.audio_processor.SUPPORTED_FORMATS

    def estimate_cost(self, audio_path: str) -> Dict:
        """
        Estimate transcription cost

        Args:
            audio_path: Path to audio file

        Returns:
            dict with cost estimate:
                {
                    "duration_minutes": float,
                    "estimated_cost_usd": float,
                    "backend": str
                }
        """
        metadata = self.audio_processor.get_metadata(audio_path)
        duration_minutes = metadata.get("duration_seconds", 0) / 60

        if self.backend == "openai":
            # OpenAI Whisper API: $0.006 per minute
            cost = duration_minutes * 0.006
        else:
            # Local whisper.cpp is free
            cost = 0.0

        return {
            "duration_minutes": round(duration_minutes, 2),
            "estimated_cost_usd": round(cost, 4),
            "backend": self.backend
        }
