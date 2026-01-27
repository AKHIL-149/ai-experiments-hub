"""Transcription Service - Multi-backend audio transcription"""

import os
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional
from openai import OpenAI
import subprocess

from .audio_processor import AudioProcessor
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)


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
        whisper_model_path: Optional[str] = None
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
        """
        self.backend = backend
        self.model = model
        self.cache_manager = cache_manager
        self.audio_processor = audio_processor or AudioProcessor()

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
                    "segments": List[dict] (optional),
                    "cached": bool,
                    "backend": str
                }
        """
        # Check cache first
        if use_cache and self.cache_manager:
            audio_hash = self.audio_processor.get_file_hash(audio_path)
            cached_result = self.cache_manager.get_transcription(audio_hash)

            if cached_result:
                logger.info(f"Using cached transcription for {audio_path}")
                cached_result["cached"] = True
                return cached_result

        # Get audio metadata
        metadata = self.audio_processor.get_metadata(audio_path)
        duration = metadata.get("duration_seconds", 0)

        logger.info(f"Transcribing: {audio_path} ({duration:.1f}s)")

        # Transcribe based on backend
        if self.backend == "openai":
            result = self._transcribe_openai(audio_path, language)
        elif self.backend == "whisper-cpp":
            result = self._transcribe_whisper_cpp(audio_path, language)
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

        # Add metadata
        result["duration"] = duration
        result["cached"] = False
        result["backend"] = self.backend

        # Cache the result
        if use_cache and self.cache_manager:
            audio_hash = self.audio_processor.get_file_hash(audio_path)
            self.cache_manager.set_transcription(audio_hash, result)

        return result

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

                if language:
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

    def _transcribe_whisper_cpp(self, audio_path: str, language: Optional[str]) -> Dict:
        """
        Transcribe using local Whisper.cpp

        Args:
            audio_path: Path to audio file
            language: Language code (optional)

        Returns:
            dict with transcription result
        """
        try:
            # Convert audio to WAV format (required by whisper.cpp)
            audio = self.audio_processor.load_audio(audio_path)
            wav_path = audio_path + ".wav"
            self.audio_processor.export_audio(audio, wav_path, format="wav")

            # Build whisper.cpp command
            cmd = [
                self.whisper_cpp_path,
                "-m", self.whisper_model_path,
                "-f", wav_path,
                "--output-txt",  # Output as text
                "--output-file", wav_path.replace('.wav', '')
            ]

            if language:
                cmd.extend(["-l", language])

            logger.info(f"Running whisper.cpp: {' '.join(cmd)}")
            start_time = time.time()

            # Run whisper.cpp
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            elapsed = time.time() - start_time

            if process.returncode != 0:
                raise RuntimeError(
                    f"Whisper.cpp failed with code {process.returncode}: {process.stderr}"
                )

            logger.info(f"Transcription completed in {elapsed:.2f}s")

            # Read output text file
            output_file = wav_path.replace('.wav', '.txt')
            with open(output_file, 'r', encoding='utf-8') as f:
                text = f.read().strip()

            # Clean up temporary files
            Path(wav_path).unlink(missing_ok=True)
            Path(output_file).unlink(missing_ok=True)

            return {
                "text": text,
                "language": language or "unknown"
            }

        except subprocess.TimeoutExpired:
            logger.error("Whisper.cpp timeout (>10 minutes)")
            raise RuntimeError("Whisper.cpp transcription timeout")

        except Exception as e:
            logger.error(f"Whisper.cpp transcription failed: {str(e)}")
            raise RuntimeError(f"Whisper.cpp transcription failed: {str(e)}")

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

        # Create temp directory for chunks
        temp_dir = Path(audio_path).parent / "temp_chunks"
        temp_dir.mkdir(exist_ok=True)

        try:
            # Export chunks to temporary files
            chunk_files = []
            for i, chunk in enumerate(chunks):
                chunk_path = temp_dir / f"chunk_{i}.wav"
                self.audio_processor.export_audio(chunk, str(chunk_path), format="wav")
                chunk_files.append(str(chunk_path))

            # Transcribe each chunk
            transcripts = []
            for i, chunk_file in enumerate(chunk_files):
                logger.info(f"Transcribing chunk {i+1}/{len(chunk_files)}")

                result = self.transcribe(chunk_file, language=language, use_cache=False)
                transcripts.append(result)

            # Merge transcripts
            merged = self._merge_transcripts(transcripts, chunk_duration_minutes, overlap_seconds)

            # Add metadata
            merged["duration"] = self.audio_processor.get_duration(audio)
            merged["cached"] = False
            merged["backend"] = self.backend
            merged["chunks_processed"] = len(chunks)

            return merged

        finally:
            # Clean up temporary files
            for chunk_file in chunk_files:
                Path(chunk_file).unlink(missing_ok=True)
            temp_dir.rmdir()

    def _merge_transcripts(
        self,
        transcripts: List[Dict],
        chunk_duration_minutes: int,
        overlap_seconds: int
    ) -> Dict:
        """
        Merge multiple transcript chunks into single transcript

        Args:
            transcripts: List of transcript dicts
            chunk_duration_minutes: Duration of each chunk
            overlap_seconds: Overlap between chunks

        Returns:
            Merged transcript dict
        """
        if not transcripts:
            return {"text": "", "language": "unknown", "segments": []}

        # Simple merge: concatenate text
        merged_text = ""
        language = transcripts[0].get("language", "unknown")
        merged_segments = []

        chunk_duration_seconds = chunk_duration_minutes * 60
        time_offset = 0

        for i, transcript in enumerate(transcripts):
            text = transcript.get("text", "").strip()

            # For chunks after the first, remove overlap region text
            # (This is a simple heuristic - more advanced would use word-level timing)
            if i > 0 and overlap_seconds > 0:
                # Skip first few words that might be in overlap
                words = text.split()
                skip_words = max(1, int(len(words) * (overlap_seconds / chunk_duration_seconds)))
                text = " ".join(words[skip_words:])

            merged_text += text + " "

            # Merge segments if available
            if "segments" in transcript:
                for seg in transcript["segments"]:
                    merged_segments.append({
                        "start": seg["start"] + time_offset,
                        "end": seg["end"] + time_offset,
                        "text": seg["text"]
                    })

            # Update time offset for next chunk
            time_offset += chunk_duration_seconds - overlap_seconds

        result = {
            "text": merged_text.strip(),
            "language": language
        }

        if merged_segments:
            result["segments"] = merged_segments

        logger.info(f"Merged {len(transcripts)} transcripts into {len(merged_text)} characters")

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
