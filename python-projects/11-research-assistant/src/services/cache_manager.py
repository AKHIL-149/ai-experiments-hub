"""
Cache Manager for Research Assistant.

Implements 3-level caching strategy:
- Level 1: Search results (7-day TTL)
- Level 2: Content extraction (30-day TTL)
- Level 3: Synthesis results (14-day TTL)
"""

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
import pickle


class CacheManager:
    """Manages multi-level caching for research operations."""

    def __init__(
        self,
        cache_dir: str = './data/cache',
        enable_cache: bool = True
    ):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory for cache storage
            enable_cache: Whether caching is enabled
        """
        self.cache_dir = Path(cache_dir)
        self.enable_cache = enable_cache

        if self.enable_cache:
            # Create cache subdirectories
            self.search_cache_dir = self.cache_dir / 'search'
            self.content_cache_dir = self.cache_dir / 'content'
            self.synthesis_cache_dir = self.cache_dir / 'synthesis'

            for cache_path in [self.search_cache_dir, self.content_cache_dir, self.synthesis_cache_dir]:
                cache_path.mkdir(parents=True, exist_ok=True)

            logging.info(f"CacheManager initialized with cache dir: {self.cache_dir}")

        # Statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0
        }

    def get(
        self,
        key: str,
        category: str = 'search'
    ) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key
            category: Cache category ('search', 'content', 'synthesis')

        Returns:
            Cached value or None if not found/expired
        """
        if not self.enable_cache:
            return None

        cache_file = self._get_cache_path(key, category)

        if not cache_file.exists():
            self.stats['misses'] += 1
            return None

        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)

            # Check expiration
            if cache_data['expires_at'] < datetime.utcnow():
                # Expired - delete
                cache_file.unlink()
                self.stats['misses'] += 1
                logging.debug(f"Cache expired: {key[:16]}... ({category})")
                return None

            self.stats['hits'] += 1
            logging.debug(f"Cache hit: {key[:16]}... ({category})")
            return cache_data['value']

        except Exception as e:
            logging.warning(f"Failed to read cache {key[:16]}...: {e}")
            self.stats['misses'] += 1
            return None

    def set(
        self,
        key: str,
        value: Any,
        category: str = 'search',
        ttl_days: Optional[int] = None
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            category: Cache category ('search', 'content', 'synthesis')
            ttl_days: Time to live in days (uses defaults if not specified)

        Returns:
            True if successful, False otherwise
        """
        if not self.enable_cache:
            return False

        # Get default TTL based on category
        if ttl_days is None:
            ttl_days = self._get_default_ttl(category)

        expires_at = datetime.utcnow() + timedelta(days=ttl_days)

        cache_data = {
            'key': key,
            'value': value,
            'category': category,
            'created_at': datetime.utcnow(),
            'expires_at': expires_at
        }

        cache_file = self._get_cache_path(key, category)

        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)

            self.stats['sets'] += 1
            logging.debug(f"Cache set: {key[:16]}... ({category}, TTL: {ttl_days}d)")
            return True

        except Exception as e:
            logging.warning(f"Failed to set cache {key[:16]}...: {e}")
            return False

    def delete(
        self,
        key: str,
        category: str = 'search'
    ) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key
            category: Cache category

        Returns:
            True if deleted, False if not found
        """
        if not self.enable_cache:
            return False

        cache_file = self._get_cache_path(key, category)

        if cache_file.exists():
            cache_file.unlink()
            self.stats['deletes'] += 1
            logging.debug(f"Cache deleted: {key[:16]}... ({category})")
            return True

        return False

    def clear(self, category: Optional[str] = None) -> int:
        """
        Clear cache.

        Args:
            category: Specific category to clear, or None for all

        Returns:
            Number of files deleted
        """
        if not self.enable_cache:
            return 0

        count = 0

        if category:
            cache_dir = self._get_cache_dir(category)
            if cache_dir.exists():
                for cache_file in cache_dir.glob('*.pkl'):
                    cache_file.unlink()
                    count += 1
        else:
            # Clear all categories
            for cat in ['search', 'content', 'synthesis']:
                count += self.clear(category=cat)

        logging.info(f"Cleared {count} cache files" + (f" ({category})" if category else ""))
        return count

    def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of expired entries deleted
        """
        if not self.enable_cache:
            return 0

        count = 0
        now = datetime.utcnow()

        for category in ['search', 'content', 'synthesis']:
            cache_dir = self._get_cache_dir(category)
            if not cache_dir.exists():
                continue

            for cache_file in cache_dir.glob('*.pkl'):
                try:
                    with open(cache_file, 'rb') as f:
                        cache_data = pickle.load(f)

                    if cache_data['expires_at'] < now:
                        cache_file.unlink()
                        count += 1

                except Exception as e:
                    logging.warning(f"Failed to check expiration for {cache_file}: {e}")

        if count > 0:
            logging.info(f"Cleaned up {count} expired cache entries")

        return count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        stats = self.stats.copy()

        if self.enable_cache:
            # Calculate hit rate
            total_requests = stats['hits'] + stats['misses']
            stats['hit_rate'] = stats['hits'] / total_requests if total_requests > 0 else 0.0

            # Count cached files
            stats['cached_files'] = {
                'search': len(list(self.search_cache_dir.glob('*.pkl'))) if self.search_cache_dir.exists() else 0,
                'content': len(list(self.content_cache_dir.glob('*.pkl'))) if self.content_cache_dir.exists() else 0,
                'synthesis': len(list(self.synthesis_cache_dir.glob('*.pkl'))) if self.synthesis_cache_dir.exists() else 0
            }
            stats['total_files'] = sum(stats['cached_files'].values())

            # Calculate total cache size
            stats['cache_size_mb'] = self._get_cache_size() / (1024 * 1024)

        stats['enabled'] = self.enable_cache

        return stats

    def _get_cache_path(self, key: str, category: str) -> Path:
        """Get cache file path for key and category."""
        cache_dir = self._get_cache_dir(category)
        # Hash the key to create a filesystem-safe filename
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        return cache_dir / f"{key_hash}.pkl"

    def _get_cache_dir(self, category: str) -> Path:
        """Get cache directory for category."""
        if category == 'search':
            return self.search_cache_dir
        elif category == 'content':
            return self.content_cache_dir
        elif category == 'synthesis':
            return self.synthesis_cache_dir
        else:
            raise ValueError(f"Unknown cache category: {category}")

    def _get_default_ttl(self, category: str) -> int:
        """Get default TTL in days for category."""
        if category == 'search':
            return 7  # Search results: 7 days
        elif category == 'content':
            return 30  # Content extraction: 30 days
        elif category == 'synthesis':
            return 14  # Synthesis results: 14 days
        else:
            return 7  # Default

    def _get_cache_size(self) -> int:
        """Get total cache size in bytes."""
        total_size = 0

        for category in ['search', 'content', 'synthesis']:
            cache_dir = self._get_cache_dir(category)
            if cache_dir.exists():
                for cache_file in cache_dir.glob('*.pkl'):
                    total_size += cache_file.stat().st_size

        return total_size

    def get_info(self) -> Dict[str, Any]:
        """Get information about the cache manager."""
        info = {
            'enabled': self.enable_cache,
            'cache_dir': str(self.cache_dir) if self.enable_cache else None,
            'categories': {
                'search': {'ttl_days': 7, 'description': 'Search results'},
                'content': {'ttl_days': 30, 'description': 'Content extraction'},
                'synthesis': {'ttl_days': 14, 'description': 'Synthesis results'}
            }
        }

        if self.enable_cache:
            info.update(self.get_stats())

        return info
