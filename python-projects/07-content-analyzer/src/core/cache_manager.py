"""Cache manager for API responses and images."""
import os
import json
import hashlib
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timedelta


class CacheManager:
    """Manages caching of API responses and processed images."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        ttl_seconds: int = 86400,  # 24 hours default
        max_cache_size_mb: int = 500
    ):
        """Initialize cache manager.

        Args:
            cache_dir: Directory for cache storage (defaults to ./data/cache)
            ttl_seconds: Time-to-live for cached items in seconds
            max_cache_size_mb: Maximum cache size in megabytes
        """
        self.cache_dir = Path(cache_dir) if cache_dir else Path("data/cache")
        self.ttl_seconds = ttl_seconds
        self.max_cache_size_mb = max_cache_size_mb

        # Create cache directories
        # Batch workers share one manager: counters and files are changed under this lock
        self._lock = threading.RLock()

        self.response_cache_dir = self.cache_dir / "responses"
        self.image_cache_dir = self.cache_dir / "images"
        self.stats_file = self.cache_dir / "stats.json"

        self._ensure_cache_dirs()
        self._load_stats()

    def _ensure_cache_dirs(self):
        """Create cache directories if they don't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.response_cache_dir.mkdir(exist_ok=True)
        self.image_cache_dir.mkdir(exist_ok=True)

    @staticmethod
    def _fresh_stats() -> Dict[str, Any]:
        return {
            'hits': 0,
            'misses': 0,
            'total_requests': 0,
            'cache_saves': 0,
            'last_cleanup': None,
            'cost_savings': {
                'anthropic': 0.0,
                'openai': 0.0,
                'total': 0.0
            }
        }

    def _load_stats(self):
        """Load cache statistics (a missing, damaged or incomplete file starts the counters afresh)."""
        self.stats = self._fresh_stats()
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    for key, value in saved.items():
                        if key == 'cost_savings' and isinstance(value, dict):
                            self.stats['cost_savings'].update(value)
                        elif key in self.stats:
                            self.stats[key] = value
            except (OSError, ValueError):
                pass        # damaged file: counters restart, the cached answers are still good

    def _write_json(self, path: Path, data: Any, indent: Optional[int] = 2) -> None:
        """Write JSON so that a reader never sees half a file (temp file, then rename)."""
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + '.', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=indent)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _save_stats(self):
        """Save cache statistics."""
        with self._lock:
            self._write_json(self.stats_file, self.stats)

    def _compute_hash(self, data: Any) -> str:
        """Compute SHA256 hash of data.

        Args:
            data: Data to hash (string, bytes, or dict)

        Returns:
            Hex digest of hash
        """
        if isinstance(data, dict):
            data = json.dumps(data, sort_keys=True)
        if isinstance(data, str):
            data = data.encode('utf-8')

        return hashlib.sha256(data).hexdigest()

    def _is_expired(self, cache_file: Path) -> bool:
        """Check if cache file is expired.

        Args:
            cache_file: Path to cache file

        Returns:
            True if expired, False otherwise
        """
        if not cache_file.exists():
            return True

        file_mtime = cache_file.stat().st_mtime
        age_seconds = time.time() - file_mtime

        return age_seconds > self.ttl_seconds

    @staticmethod
    def _cache_key(prompt, image_hash, provider, model, params) -> Dict[str, Any]:
        """What identifies a response: everything that can change the answer.

        params (max_tokens, temperature) are part of the key; without them a short, cut-off answer
        would be served for a later request that allowed a longer one.
        """
        key = {
            'prompt': prompt,
            'image_hash': image_hash,
            'provider': provider,
            'model': model
        }
        if params:
            key['params'] = params
        return key

    def get_response(
        self,
        prompt: str,
        image_hash: str,
        provider: str,
        model: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Get cached response.

        Args:
            prompt: Text prompt
            image_hash: Hash of image(s)
            provider: Provider name
            model: Model name

        Returns:
            Cached response or None if not found/expired
        """
        # Create cache key
        cache_key = self._cache_key(prompt, image_hash, provider, model, params)
        cache_hash = self._compute_hash(cache_key)
        cache_file = self.response_cache_dir / f"{cache_hash}.json"

        with self._lock:
            self.stats['total_requests'] += 1

            # Check if cache exists and is valid
            if cache_file.exists() and not self._is_expired(cache_file):
                try:
                    with open(cache_file, 'r') as f:
                        cached_data = json.load(f)
                    response = cached_data['response']
                    if not response:
                        raise ValueError("empty cached response")

                    self.stats['hits'] += 1

                    # Track cost savings
                    if provider in ['anthropic', 'openai']:
                        estimated_cost = self._estimate_cost(provider, model, prompt)
                        self.stats['cost_savings'][provider] += estimated_cost
                        self.stats['cost_savings']['total'] += estimated_cost

                    self._save_stats()

                    return response
                except Exception:
                    # Cache corrupted, treat as miss
                    pass

            self.stats['misses'] += 1
            self._save_stats()
            return None

    def save_response(
        self,
        prompt: str,
        image_hash: str,
        provider: str,
        model: str,
        response: str,
        params: Optional[Dict[str, Any]] = None
    ):
        """Save response to cache.

        Args:
            prompt: Text prompt
            image_hash: Hash of image(s)
            provider: Provider name
            model: Model name
            response: Response to cache
        """
        # Create cache key
        cache_key = self._cache_key(prompt, image_hash, provider, model, params)
        cache_hash = self._compute_hash(cache_key)
        cache_file = self.response_cache_dir / f"{cache_hash}.json"

        # Save to cache
        cache_data = {
            'prompt': prompt,
            'image_hash': image_hash,
            'provider': provider,
            'model': model,
            'response': response,
            'cached_at': datetime.now().isoformat(),
            'ttl_seconds': self.ttl_seconds
        }

        if not response or not response.strip():
            return                                   # an empty answer is not worth remembering

        with self._lock:
            self._write_json(cache_file, cache_data)

            self.stats['cache_saves'] += 1
            self._save_stats()

            # Check cache size and cleanup if needed
            self._cleanup_if_needed()

    def compute_image_hash(self, image_data: bytes) -> str:
        """Compute hash of image data.

        Args:
            image_data: Raw image bytes

        Returns:
            Hex digest of hash
        """
        return self._compute_hash(image_data)

    def _estimate_cost(self, provider: str, model: str, prompt: str) -> float:
        """Estimate API cost for a request.

        Args:
            provider: Provider name
            model: Model name
            prompt: Text prompt

        Returns:
            Estimated cost in USD
        """
        # Rough token estimation (4 chars per token)
        prompt_tokens = len(prompt) // 4
        # Assume average response is 500 tokens
        total_tokens = prompt_tokens + 500

        # Cost per 1M tokens (as of 2024)
        costs = {
            'anthropic': {
                'claude-3-5-sonnet-20241022': 0.003,  # $3 per 1M tokens
            },
            'openai': {
                'gpt-4-vision-preview': 0.01,  # $10 per 1M tokens
            }
        }

        if provider in costs and model in costs[provider]:
            cost_per_token = costs[provider][model] / 1_000_000
            return total_tokens * cost_per_token

        return 0.0

    def _size_bytes(self) -> int:
        """Total size of the cache folder (files that vanish while counting are ignored)"""
        total = 0
        for f in self.cache_dir.rglob('*'):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                continue
        return total

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        hit_rate = 0.0
        if self.stats['total_requests'] > 0:
            hit_rate = (self.stats['hits'] / self.stats['total_requests']) * 100

        # Calculate cache size
        cache_size_mb = self._size_bytes() / (1024 * 1024)

        return {
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'total_requests': self.stats['total_requests'],
            'hit_rate_percent': round(hit_rate, 2),
            'cache_saves': self.stats['cache_saves'],
            'cache_size_mb': round(cache_size_mb, 2),
            'cost_savings': self.stats['cost_savings'],
            'last_cleanup': self.stats['last_cleanup']
        }

    def _cleanup_if_needed(self):
        """Cleanup cache if it exceeds size limit."""
        cache_size_mb = self._size_bytes() / (1024 * 1024)

        if cache_size_mb > self.max_cache_size_mb:
            self.cleanup(keep_recent_hours=24)

    def cleanup(self, keep_recent_hours: Optional[int] = None):
        """Clean up expired or old cache entries.

        Args:
            keep_recent_hours: Keep entries newer than this many hours
        """
        # 0 hours means "keep nothing newer than now", not "no age limit"
        cutoff_time = None
        if keep_recent_hours is not None:
            cutoff_time = time.time() - (keep_recent_hours * 3600)

        removed_count = 0

        with self._lock:
            return self._cleanup_locked(cutoff_time, keep_recent_hours)

    def _cleanup_locked(self, cutoff_time, keep_recent_hours) -> int:
        removed_count = 0

        # Clean response cache
        for cache_file in self.response_cache_dir.glob('*.json'):
            should_remove = False

            try:
                if keep_recent_hours is not None:
                    if cache_file.stat().st_mtime < cutoff_time:
                        should_remove = True
                else:
                    if self._is_expired(cache_file):
                        should_remove = True
            except OSError:
                continue

            if should_remove:
                cache_file.unlink(missing_ok=True)
                removed_count += 1

        # Clean image cache
        for cache_file in self.image_cache_dir.glob('*'):
            should_remove = False

            try:
                if keep_recent_hours is not None:
                    if cache_file.stat().st_mtime < cutoff_time:
                        should_remove = True
                else:
                    if self._is_expired(cache_file):
                        should_remove = True
            except OSError:
                continue

            if should_remove:
                cache_file.unlink(missing_ok=True)
                removed_count += 1

        self.stats['last_cleanup'] = datetime.now().isoformat()
        self._save_stats()

        return removed_count

    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._clear_locked()

    def _clear_locked(self):
        for cache_file in self.response_cache_dir.glob('*.json'):
            cache_file.unlink(missing_ok=True)

        for cache_file in self.image_cache_dir.glob('*'):
            cache_file.unlink(missing_ok=True)

        # Reset stats
        self.stats = self._fresh_stats()
        self.stats['last_cleanup'] = datetime.now().isoformat()
        self._save_stats()
