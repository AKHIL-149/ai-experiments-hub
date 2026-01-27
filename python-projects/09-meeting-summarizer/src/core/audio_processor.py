"""Audio Processor - Handle audio file loading, validation, and processing"""

import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from pydub import AudioSegment
from pydub.utils import mediainfo
import logging

logger = logging.getLogger(__name__)


class AudioProcessor:
    """
    Handles audio file operations including loading, validation,
    metadata extraction, format conversion, and chunking.
    """

    SUPPORTED_FORMATS = ['mp3', 'wav', 'webm', 'm4a', 'ogg', 'flac']

    def __init__(self, max_size_mb: int = 500):
        """
        Initialize Audio Processor

        Args:
            max_size_mb: Maximum audio file size in MB
        """
        self.max_size_mb = max_size_mb
        self.max_size_bytes = max_size_mb * 1024 * 1024

    def load_audio(self, file_path: str) -> AudioSegment:
        """
        Load audio file from disk

        Args:
            file_path: Path to audio file

        Returns:
            AudioSegment object

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is unsupported
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        # Get file format from extension
        file_format = path.suffix.lstrip('.').lower()

        if file_format not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported audio format: {file_format}. "
                f"Supported: {', '.join(self.SUPPORTED_FORMATS)}"
            )

        logger.info(f"Loading audio file: {file_path} (format: {file_format})")

        try:
            # Load audio using pydub
            audio = AudioSegment.from_file(file_path, format=file_format)
            logger.info(f"Successfully loaded audio: {self.get_duration(audio)}s duration")
            return audio

        except Exception as e:
            raise ValueError(f"Failed to load audio file: {str(e)}")

    def validate_audio(self, audio_path: str) -> Dict:
        """
        Validate audio file before processing

        Args:
            audio_path: Path to audio file

        Returns:
            dict with validation results:
                {
                    "valid": bool,
                    "errors": List[str],
                    "warnings": List[str],
                    "file_size_mb": float,
                    "format": str
                }
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "file_size_mb": 0,
            "format": ""
        }

        path = Path(audio_path)

        # Check if file exists
        if not path.exists():
            result["valid"] = False
            result["errors"].append(f"File not found: {audio_path}")
            return result

        # Check file size
        file_size = path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        result["file_size_mb"] = round(file_size_mb, 2)

        if file_size > self.max_size_bytes:
            result["valid"] = False
            result["errors"].append(
                f"File size ({file_size_mb:.2f} MB) exceeds maximum ({self.max_size_mb} MB)"
            )

        # Check format
        file_format = path.suffix.lstrip('.').lower()
        result["format"] = file_format

        if file_format not in self.SUPPORTED_FORMATS:
            result["valid"] = False
            result["errors"].append(
                f"Unsupported format: {file_format}. "
                f"Supported: {', '.join(self.SUPPORTED_FORMATS)}"
            )

        # Try to load and get basic info
        try:
            audio = self.load_audio(audio_path)
            duration = self.get_duration(audio)

            # Warning for very short audio
            if duration < 1:
                result["warnings"].append(
                    f"Audio is very short ({duration:.2f}s). May not transcribe well."
                )

            # Warning for very long audio
            if duration > 7200:  # 2 hours
                result["warnings"].append(
                    f"Audio is very long ({duration/60:.1f}min). Processing will be slow."
                )

        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Failed to load audio: {str(e)}")

        return result

    def get_metadata(self, audio_path: str) -> Dict:
        """
        Extract audio metadata

        Args:
            audio_path: Path to audio file

        Returns:
            dict with metadata:
                {
                    "duration_seconds": float,
                    "format": str,
                    "bitrate": str,
                    "sample_rate": int,
                    "channels": int,
                    "file_size_mb": float
                }
        """
        try:
            # Get file info
            path = Path(audio_path)
            file_size_mb = path.stat().st_size / (1024 * 1024)

            # Load audio
            audio = self.load_audio(audio_path)

            # Get detailed info
            info = mediainfo(audio_path)

            metadata = {
                "duration_seconds": round(self.get_duration(audio), 2),
                "format": path.suffix.lstrip('.').lower(),
                "bitrate": info.get('bit_rate', 'unknown'),
                "sample_rate": audio.frame_rate,
                "channels": audio.channels,
                "file_size_mb": round(file_size_mb, 2)
            }

            return metadata

        except Exception as e:
            logger.error(f"Failed to extract metadata: {str(e)}")
            return {
                "duration_seconds": 0,
                "format": "",
                "bitrate": "unknown",
                "sample_rate": 0,
                "channels": 0,
                "file_size_mb": 0,
                "error": str(e)
            }

    def split_audio(
        self,
        audio: AudioSegment,
        chunk_duration_minutes: int = 10,
        overlap_seconds: int = 5
    ) -> List[AudioSegment]:
        """
        Split long audio into smaller chunks for API processing

        Args:
            audio: AudioSegment to split
            chunk_duration_minutes: Duration of each chunk in minutes
            overlap_seconds: Overlap between chunks in seconds

        Returns:
            List of AudioSegment chunks
        """
        chunk_duration_ms = chunk_duration_minutes * 60 * 1000
        overlap_ms = overlap_seconds * 1000

        total_duration_ms = len(audio)

        # If audio is shorter than chunk size, return as single chunk
        if total_duration_ms <= chunk_duration_ms:
            logger.info("Audio is shorter than chunk duration, returning single chunk")
            return [audio]

        chunks = []
        start_ms = 0

        while start_ms < total_duration_ms:
            end_ms = min(start_ms + chunk_duration_ms, total_duration_ms)

            # Extract chunk
            chunk = audio[start_ms:end_ms]
            chunks.append(chunk)

            logger.info(
                f"Created chunk {len(chunks)}: "
                f"{start_ms/1000:.1f}s - {end_ms/1000:.1f}s "
                f"({len(chunk)/1000:.1f}s duration)"
            )

            # Move to next chunk with overlap
            start_ms = end_ms - overlap_ms

            # Prevent infinite loop if overlap is too large
            if start_ms >= end_ms:
                break

        logger.info(f"Split audio into {len(chunks)} chunks")
        return chunks

    def convert_to_wav(self, audio: AudioSegment) -> bytes:
        """
        Convert audio to WAV format

        Args:
            audio: AudioSegment to convert

        Returns:
            WAV audio bytes
        """
        from io import BytesIO

        buffer = BytesIO()
        audio.export(buffer, format="wav")
        return buffer.getvalue()

    def export_audio(
        self,
        audio: AudioSegment,
        output_path: str,
        format: str = "mp3"
    ) -> str:
        """
        Export audio to file

        Args:
            audio: AudioSegment to export
            output_path: Path to save file
            format: Output format (mp3, wav, etc.)

        Returns:
            Path to exported file
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Exporting audio to: {output_path} (format: {format})")
        audio.export(output_path, format=format)

        return str(path)

    @staticmethod
    def get_duration(audio: AudioSegment) -> float:
        """Get audio duration in seconds"""
        return len(audio) / 1000.0

    @staticmethod
    def get_file_hash(file_path: str) -> str:
        """
        Calculate SHA256 hash of file for caching

        Args:
            file_path: Path to file

        Returns:
            Hex string of file hash
        """
        import hashlib

        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()
