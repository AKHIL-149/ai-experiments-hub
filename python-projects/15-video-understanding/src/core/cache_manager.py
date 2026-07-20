"""
Cache Manager for storing and retrieving processed results
Adapted from Project 7 Content Analyzer
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional, Dict

from src.core.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manager for caching processed results to avoid redundant processing

    Supports:
    - Video hash caching
    - Frame analysis results
    - Embedding vectors
    - Transcription results
    - Vision model outputs
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize cache manager

        Args:
            cache_dir: Directory for cache storage (uses settings if not provided)
        """
        self.cache_dir = Path(cache_dir or settings.cache_path)
        self.cache_enabled = settings.cache_enabled
        self.cache_ttl = settings.cache_ttl_seconds
        self.max_cache_size_mb = settings.cache_max_size_mb

        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cache manager initialized - Dir: {self.cache_dir}, TTL: {self.cache_ttl}s")

    def _get_cache_key(self, key: str, namespace: str = "default") -> str:
        """
        Generate cache key hash

        Args:
            key: Original key
            namespace: Cache namespace (e.g., 'frames', 'transcripts', 'embeddings')

        Returns:
            Hashed cache key
        """
        combined = f"{namespace}:{key}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """
        Get file path for cache key

        Args:
            cache_key: Hashed cache key

        Returns:
            Path to cache file
        """
        # Use first 2 chars as subdirectory to avoid too many files in one dir
        subdir = cache_key[:2]
        cache_subdir = self.cache_dir / subdir
        cache_subdir.mkdir(parents=True, exist_ok=True)
        return cache_subdir / f"{cache_key}.json"

    def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key
            namespace: Cache namespace

        Returns:
            Cached value or None if not found/expired
        """
        if not self.cache_enabled:
            return None

        cache_key = self._get_cache_key(key, namespace)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        try:
            # Read cache file
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)

            # Check TTL
            if self.cache_ttl > 0:
                timestamp = cache_data.get('timestamp', 0)
                age = time.time() - timestamp

                if age > self.cache_ttl:
                    logger.debug(f"Cache expired - Key: {key[:50]}..., Age: {age:.1f}s")
                    cache_path.unlink()  # Delete expired cache
                    return None

            logger.debug(f"Cache hit - Key: {key[:50]}...")
            return cache_data.get('value')

        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.warning(f"Cache read error: {e}")
            # Delete corrupted cache file
            if cache_path.exists():
                cache_path.unlink()
            return None

    def set(self, key: str, value: Any, namespace: str = "default") -> bool:
        """
        Store value in cache

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            namespace: Cache namespace

        Returns:
            True if successful, False otherwise
        """
        if not self.cache_enabled:
            return False

        cache_key = self._get_cache_key(key, namespace)
        cache_path = self._get_cache_path(cache_key)

        try:
            cache_data = {
                'key': key,
                'namespace': namespace,
                'value': value,
                'timestamp': time.time(),
            }

            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)

            logger.debug(f"Cache set - Key: {key[:50]}...")
            return True

        except (TypeError, IOError) as e:
            logger.error(f"Cache write error: {e}")
            return False

    def delete(self, key: str, namespace: str = "default") -> bool:
        """
        Delete value from cache

        Args:
            key: Cache key
            namespace: Cache namespace

        Returns:
            True if deleted, False if not found
        """
        if not self.cache_enabled:
            return False

        cache_key = self._get_cache_key(key, namespace)
        cache_path = self._get_cache_path(cache_key)

        if cache_path.exists():
            cache_path.unlink()
            logger.debug(f"Cache deleted - Key: {key[:50]}...")
            return True

        return False

    def clear(self, namespace: Optional[str] = None) -> int:
        """
        Clear cache entries

        Args:
            namespace: Clear specific namespace (or all if None)

        Returns:
            Number of entries cleared
        """
        if not self.cache_enabled:
            return 0

        count = 0

        if namespace is None:
            # Clear all cache
            for cache_file in self.cache_dir.rglob("*.json"):
                cache_file.unlink()
                count += 1
        else:
            # Clear specific namespace
            for cache_file in self.cache_dir.rglob("*.json"):
                try:
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)
                    if cache_data.get('namespace') == namespace:
                        cache_file.unlink()
                        count += 1
                except (json.JSONDecodeError, IOError):
                    pass

        logger.info(f"Cache cleared - Namespace: {namespace or 'all'}, Count: {count}")
        return count

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache stats
        """
        if not self.cache_enabled:
            return {
                'enabled': False,
                'total_entries': 0,
                'total_size_mb': 0,
            }

        total_entries = 0
        total_size = 0
        namespaces = {}

        for cache_file in self.cache_dir.rglob("*.json"):
            total_entries += 1
            total_size += cache_file.stat().st_size

            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                namespace = cache_data.get('namespace', 'unknown')
                namespaces[namespace] = namespaces.get(namespace, 0) + 1
            except (json.JSONDecodeError, IOError):
                pass

        return {
            'enabled': True,
            'total_entries': total_entries,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'max_size_mb': self.max_cache_size_mb,
            'ttl_seconds': self.cache_ttl,
            'namespaces': namespaces,
        }

    def cleanup_expired(self) -> int:
        """
        Remove expired cache entries

        Returns:
            Number of entries removed
        """
        if not self.cache_enabled or self.cache_ttl <= 0:
            return 0

        count = 0
        current_time = time.time()

        for cache_file in self.cache_dir.rglob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)

                timestamp = cache_data.get('timestamp', 0)
                age = current_time - timestamp

                if age > self.cache_ttl:
                    cache_file.unlink()
                    count += 1

            except (json.JSONDecodeError, IOError, KeyError):
                # Delete corrupted files
                cache_file.unlink()
                count += 1

        if count > 0:
            logger.info(f"Cache cleanup - Removed {count} expired entries")

        return count


# Singleton instance
cache_manager = CacheManager()
