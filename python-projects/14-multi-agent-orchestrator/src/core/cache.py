"""
Caching Service

Provides Redis-based caching for improved performance.
Supports query result caching, response caching, and cache invalidation.
"""

import json
import hashlib
from typing import Any, Optional, Callable, Union
from functools import wraps
from datetime import timedelta
import redis
from redis import Redis

from src.core.config import settings
from src.core.logging import logger


class CacheService:
    """
    Redis-based caching service

    Features:
    - Key-value caching with TTL
    - JSON serialization
    - Cache invalidation patterns
    - Cache statistics
    - Distributed caching support
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Initialize cache service

        Args:
            redis_client: Redis client instance (optional)
        """
        if redis_client:
            self.redis = redis_client
        else:
            # Create Redis client from settings
            self.redis = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True
            )

        self.default_ttl = 300  # 5 minutes
        self.key_prefix = "cache:"

        logger.info("Cache service initialized")

    def _make_key(self, key: str, namespace: Optional[str] = None) -> str:
        """
        Generate full cache key with namespace

        Args:
            key: Cache key
            namespace: Optional namespace

        Returns:
            str: Full cache key
        """
        if namespace:
            return f"{self.key_prefix}{namespace}:{key}"
        return f"{self.key_prefix}{key}"

    def get(self, key: str, namespace: Optional[str] = None) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key
            namespace: Optional namespace

        Returns:
            Cached value or None
        """
        full_key = self._make_key(key, namespace)

        try:
            value = self.redis.get(full_key)
            if value:
                # Deserialize JSON
                return json.loads(value)
            return None

        except Exception as e:
            logger.error(f"Cache get failed for {full_key}: {e}")
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        namespace: Optional[str] = None
    ) -> bool:
        """
        Set value in cache with TTL

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (optional)
            namespace: Optional namespace

        Returns:
            bool: True if successful
        """
        full_key = self._make_key(key, namespace)
        ttl = ttl or self.default_ttl

        try:
            # Serialize to JSON
            serialized = json.dumps(value)

            # Set with TTL
            self.redis.setex(full_key, ttl, serialized)
            return True

        except Exception as e:
            logger.error(f"Cache set failed for {full_key}: {e}")
            return False

    def delete(self, key: str, namespace: Optional[str] = None) -> bool:
        """
        Delete value from cache

        Args:
            key: Cache key
            namespace: Optional namespace

        Returns:
            bool: True if successful
        """
        full_key = self._make_key(key, namespace)

        try:
            self.redis.delete(full_key)
            return True

        except Exception as e:
            logger.error(f"Cache delete failed for {full_key}: {e}")
            return False

    def delete_pattern(self, pattern: str, namespace: Optional[str] = None) -> int:
        """
        Delete all keys matching pattern

        Args:
            pattern: Key pattern (supports wildcards)
            namespace: Optional namespace

        Returns:
            int: Number of keys deleted
        """
        full_pattern = self._make_key(pattern, namespace)

        try:
            keys = self.redis.keys(full_pattern)
            if keys:
                deleted = self.redis.delete(*keys)
                logger.info(f"Deleted {deleted} keys matching {full_pattern}")
                return deleted
            return 0

        except Exception as e:
            logger.error(f"Cache delete pattern failed for {full_pattern}: {e}")
            return 0

    def exists(self, key: str, namespace: Optional[str] = None) -> bool:
        """
        Check if key exists in cache

        Args:
            key: Cache key
            namespace: Optional namespace

        Returns:
            bool: True if key exists
        """
        full_key = self._make_key(key, namespace)

        try:
            return self.redis.exists(full_key) > 0

        except Exception as e:
            logger.error(f"Cache exists check failed for {full_key}: {e}")
            return False

    def clear_namespace(self, namespace: str) -> int:
        """
        Clear all keys in a namespace

        Args:
            namespace: Namespace to clear

        Returns:
            int: Number of keys deleted
        """
        return self.delete_pattern("*", namespace)

    def get_stats(self) -> dict:
        """
        Get cache statistics

        Returns:
            dict: Cache statistics
        """
        try:
            info = self.redis.info('stats')
            memory = self.redis.info('memory')

            # Count cache keys
            cache_keys = len(self.redis.keys(f"{self.key_prefix}*"))

            return {
                "cache_keys": cache_keys,
                "total_keys": self.redis.dbsize(),
                "hits": info.get('keyspace_hits', 0),
                "misses": info.get('keyspace_misses', 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get('keyspace_hits', 0),
                    info.get('keyspace_misses', 0)
                ),
                "memory_used_mb": round(memory.get('used_memory', 0) / 1024 / 1024, 2),
                "memory_peak_mb": round(memory.get('used_memory_peak', 0) / 1024 / 1024, 2)
            }

        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {}

    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """
        Calculate cache hit rate percentage

        Args:
            hits: Number of cache hits
            misses: Number of cache misses

        Returns:
            float: Hit rate percentage
        """
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)

    def flush_all(self) -> bool:
        """
        Clear all cache (use with caution)

        Returns:
            bool: True if successful
        """
        try:
            # Only clear cache keys, not other Redis data
            keys = self.redis.keys(f"{self.key_prefix}*")
            if keys:
                self.redis.delete(*keys)
                logger.warning(f"Flushed all cache ({len(keys)} keys)")
            return True

        except Exception as e:
            logger.error(f"Failed to flush cache: {e}")
            return False


def cache_key_builder(*args, **kwargs) -> str:
    """
    Build cache key from function arguments

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        str: Cache key hash
    """
    # Create deterministic key from arguments
    key_parts = [str(arg) for arg in args]
    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
    key_string = ":".join(key_parts)

    # Hash for consistent key length
    return hashlib.md5(key_string.encode()).hexdigest()


def cached(
    ttl: int = 300,
    namespace: str = "default",
    key_builder: Optional[Callable] = None
):
    """
    Decorator for caching function results

    Args:
        ttl: Time to live in seconds
        namespace: Cache namespace
        key_builder: Custom key builder function

    Returns:
        Decorator function

    Example:
        @cached(ttl=600, namespace="tasks")
        def get_task(task_id: int):
            return expensive_database_query(task_id)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{cache_key_builder(*args, **kwargs)}"

            # Try to get from cache
            cached_result = cache_service.get(cache_key, namespace)
            if cached_result is not None:
                logger.debug(f"Cache hit: {namespace}:{cache_key}")
                return cached_result

            # Execute function
            result = func(*args, **kwargs)

            # Cache result
            cache_service.set(cache_key, result, ttl, namespace)
            logger.debug(f"Cache set: {namespace}:{cache_key}")

            return result

        # Add cache control methods
        wrapper.invalidate = lambda *args, **kwargs: cache_service.delete(
            f"{func.__name__}:{cache_key_builder(*args, **kwargs)}",
            namespace
        )
        wrapper.invalidate_all = lambda: cache_service.clear_namespace(namespace)

        return wrapper

    return decorator


# Global cache service instance
cache_service = CacheService()
