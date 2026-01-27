"""Cache Manager - Two-level caching for transcriptions and summaries"""

import json
import hashlib
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages two-level caching:
    1. Transcription cache (Level 1 - most expensive)
    2. Summary cache (Level 2 - moderate cost)
    """

    def __init__(
        self,
        cache_dir: str = "./data/cache",
        transcription_ttl_days: int = 30,
        summary_ttl_days: int = 7
    ):
        """
        Initialize Cache Manager

        Args:
            cache_dir: Base directory for cache storage
            transcription_ttl_days: How long to keep transcriptions (days)
            summary_ttl_days: How long to keep summaries (days)
        """
        self.cache_dir = Path(cache_dir)
        self.transcription_cache_dir = self.cache_dir / "transcriptions"
        self.summary_cache_dir = self.cache_dir / "summaries"

        # Create cache directories
        self.transcription_cache_dir.mkdir(parents=True, exist_ok=True)
        self.summary_cache_dir.mkdir(parents=True, exist_ok=True)

        self.transcription_ttl = timedelta(days=transcription_ttl_days)
        self.summary_ttl = timedelta(days=summary_ttl_days)

        # Track cache statistics
        self.stats = {
            "transcription_hits": 0,
            "transcription_misses": 0,
            "summary_hits": 0,
            "summary_misses": 0,
            "estimated_cost_saved": 0.0
        }

        logger.info(f"Cache initialized: {cache_dir}")
        logger.info(f"Transcription TTL: {transcription_ttl_days} days")
        logger.info(f"Summary TTL: {summary_ttl_days} days")

    def get_transcription(self, audio_hash: str) -> Optional[Dict]:
        """
        Get cached transcription for audio file

        Args:
            audio_hash: SHA256 hash of audio file

        Returns:
            Cached transcription dict or None if not found/expired
        """
        cache_file = self.transcription_cache_dir / f"{audio_hash}.json"

        if not cache_file.exists():
            self.stats["transcription_misses"] += 1
            logger.debug(f"Transcription cache miss: {audio_hash}")
            return None

        # Check if cache is fresh
        if not self._is_fresh(cache_file, self.transcription_ttl):
            logger.info(f"Transcription cache expired: {audio_hash}")
            cache_file.unlink()  # Delete expired cache
            self.stats["transcription_misses"] += 1
            return None

        # Load cache
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.stats["transcription_hits"] += 1
            self.stats["estimated_cost_saved"] += self._estimate_transcription_cost(data)

            logger.info(f"Transcription cache HIT: {audio_hash}")
            return data

        except Exception as e:
            logger.error(f"Failed to load transcription cache: {str(e)}")
            self.stats["transcription_misses"] += 1
            return None

    def set_transcription(self, audio_hash: str, transcription: Dict) -> None:
        """
        Cache transcription result

        Args:
            audio_hash: SHA256 hash of audio file
            transcription: Transcription result to cache
        """
        cache_file = self.transcription_cache_dir / f"{audio_hash}.json"

        # Add metadata
        cache_data = {
            **transcription,
            "_cached_at": datetime.now().isoformat(),
            "_audio_hash": audio_hash
        }

        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Cached transcription: {audio_hash}")

        except Exception as e:
            logger.error(f"Failed to cache transcription: {str(e)}")

    def get_summary(self, transcript_hash: str, model: str) -> Optional[Dict]:
        """
        Get cached summary for transcript

        Args:
            transcript_hash: SHA256 hash of transcript text
            model: LLM model name used for summarization

        Returns:
            Cached summary dict or None if not found/expired
        """
        cache_key = f"{transcript_hash}_{self._sanitize_model_name(model)}"
        cache_file = self.summary_cache_dir / f"{cache_key}.json"

        if not cache_file.exists():
            self.stats["summary_misses"] += 1
            logger.debug(f"Summary cache miss: {cache_key}")
            return None

        # Check if cache is fresh
        if not self._is_fresh(cache_file, self.summary_ttl):
            logger.info(f"Summary cache expired: {cache_key}")
            cache_file.unlink()
            self.stats["summary_misses"] += 1
            return None

        # Load cache
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.stats["summary_hits"] += 1
            self.stats["estimated_cost_saved"] += self._estimate_summary_cost(data)

            logger.info(f"Summary cache HIT: {cache_key}")
            return data

        except Exception as e:
            logger.error(f"Failed to load summary cache: {str(e)}")
            self.stats["summary_misses"] += 1
            return None

    def set_summary(self, transcript_hash: str, model: str, summary: Dict) -> None:
        """
        Cache summary result

        Args:
            transcript_hash: SHA256 hash of transcript text
            model: LLM model name used
            summary: Summary result to cache
        """
        cache_key = f"{transcript_hash}_{self._sanitize_model_name(model)}"
        cache_file = self.summary_cache_dir / f"{cache_key}.json"

        # Add metadata
        cache_data = {
            **summary,
            "_cached_at": datetime.now().isoformat(),
            "_transcript_hash": transcript_hash,
            "_model": model
        }

        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Cached summary: {cache_key}")

        except Exception as e:
            logger.error(f"Failed to cache summary: {str(e)}")

    def get_stats(self) -> Dict:
        """
        Get cache statistics

        Returns:
            dict with cache performance metrics
        """
        transcription_total = (
            self.stats["transcription_hits"] + self.stats["transcription_misses"]
        )
        summary_total = (
            self.stats["summary_hits"] + self.stats["summary_misses"]
        )

        transcription_hit_rate = (
            self.stats["transcription_hits"] / transcription_total * 100
            if transcription_total > 0 else 0
        )
        summary_hit_rate = (
            self.stats["summary_hits"] / summary_total * 100
            if summary_total > 0 else 0
        )

        return {
            "transcription": {
                "hits": self.stats["transcription_hits"],
                "misses": self.stats["transcription_misses"],
                "hit_rate_percent": round(transcription_hit_rate, 2),
                "total_requests": transcription_total
            },
            "summary": {
                "hits": self.stats["summary_hits"],
                "misses": self.stats["summary_misses"],
                "hit_rate_percent": round(summary_hit_rate, 2),
                "total_requests": summary_total
            },
            "estimated_cost_saved_usd": round(self.stats["estimated_cost_saved"], 2),
            "cache_dir": str(self.cache_dir),
            "cache_sizes": {
                "transcriptions": self._get_cache_size(self.transcription_cache_dir),
                "summaries": self._get_cache_size(self.summary_cache_dir)
            }
        }

    def cleanup_expired(self) -> Dict:
        """
        Remove expired cache entries

        Returns:
            dict with cleanup statistics
        """
        removed_transcriptions = 0
        removed_summaries = 0

        # Cleanup transcription cache
        for cache_file in self.transcription_cache_dir.glob("*.json"):
            if not self._is_fresh(cache_file, self.transcription_ttl):
                cache_file.unlink()
                removed_transcriptions += 1

        # Cleanup summary cache
        for cache_file in self.summary_cache_dir.glob("*.json"):
            if not self._is_fresh(cache_file, self.summary_ttl):
                cache_file.unlink()
                removed_summaries += 1

        logger.info(
            f"Cleanup: removed {removed_transcriptions} transcriptions, "
            f"{removed_summaries} summaries"
        )

        return {
            "removed_transcriptions": removed_transcriptions,
            "removed_summaries": removed_summaries,
            "total_removed": removed_transcriptions + removed_summaries
        }

    def clear_all(self) -> None:
        """Clear all cache (use with caution!)"""
        # Remove all transcription cache files
        for cache_file in self.transcription_cache_dir.glob("*.json"):
            cache_file.unlink()

        # Remove all summary cache files
        for cache_file in self.summary_cache_dir.glob("*.json"):
            cache_file.unlink()

        # Reset stats
        self.stats = {
            "transcription_hits": 0,
            "transcription_misses": 0,
            "summary_hits": 0,
            "summary_misses": 0,
            "estimated_cost_saved": 0.0
        }

        logger.warning("All cache cleared!")

    @staticmethod
    def _is_fresh(cache_file: Path, ttl: timedelta) -> bool:
        """Check if cache file is still fresh (within TTL)"""
        file_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        return file_age < ttl

    @staticmethod
    def _sanitize_model_name(model: str) -> str:
        """Sanitize model name for use in filename"""
        return model.replace('/', '_').replace(':', '_')

    @staticmethod
    def _estimate_transcription_cost(transcription: Dict) -> float:
        """Estimate cost saved by cache hit (Whisper API: $0.006/min)"""
        duration_seconds = transcription.get('duration', 0)
        duration_minutes = duration_seconds / 60
        return duration_minutes * 0.006

    @staticmethod
    def _estimate_summary_cost(summary: Dict) -> float:
        """Estimate cost saved by cache hit (rough estimate)"""
        # Rough estimate: ~$0.03 per summary
        return 0.03

    @staticmethod
    def _get_cache_size(cache_dir: Path) -> Dict:
        """Get cache directory size statistics"""
        files = list(cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)

        return {
            "num_files": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2)
        }

    @staticmethod
    def hash_text(text: str) -> str:
        """Calculate SHA256 hash of text"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
