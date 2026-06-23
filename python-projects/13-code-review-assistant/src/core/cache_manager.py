"""
Cache Manager
Redis-based caching service for performance optimization
"""

import json
import redis
from typing import Any, Optional, Callable
from datetime import timedelta
from functools import wraps
import os
import hashlib


class CacheManager:
    """Redis cache manager for expensive operations"""

    def __init__(self):
        """Initialize Redis connection"""
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

        try:
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            self.enabled = True
        except (redis.ConnectionError, redis.TimeoutError) as e:
            print(f"Warning: Redis connection failed: {e}")
            print("Cache will be disabled. Install and start Redis for better performance.")
            self.redis_client = None
            self.enabled = False

    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generate cache key from prefix and arguments

        Args:
            prefix: Cache key prefix
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Cache key string
        """
        # Create deterministic key from arguments
        key_parts = [prefix]

        # Add positional args
        for arg in args:
            if isinstance(arg, (str, int, float, bool)):
                key_parts.append(str(arg))
            else:
                # Hash complex objects
                key_parts.append(hashlib.md5(str(arg).encode()).hexdigest()[:8])

        # Add keyword args (sorted for consistency)
        for k, v in sorted(kwargs.items()):
            if isinstance(v, (str, int, float, bool)):
                key_parts.append(f"{k}={v}")
            else:
                key_parts.append(f"{k}={hashlib.md5(str(v).encode()).hexdigest()[:8]}")

        return ":".join(key_parts)

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if not self.enabled:
            return None

        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            print(f"Cache get error: {e}")

        return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            serialized = json.dumps(value)
            if ttl:
                self.redis_client.setex(key, ttl, serialized)
            else:
                self.redis_client.set(key, serialized)
            return True
        except Exception as e:
            print(f"Cache set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete key from cache

        Args:
            key: Cache key

        Returns:
            True if successful
        """
        if not self.enabled:
            return False

        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            print(f"Cache delete error: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern

        Args:
            pattern: Key pattern (e.g., "user:*")

        Returns:
            Number of keys deleted
        """
        if not self.enabled:
            return 0

        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            print(f"Cache delete pattern error: {e}")
            return 0

    def clear(self) -> bool:
        """
        Clear all cache

        Returns:
            True if successful
        """
        if not self.enabled:
            return False

        try:
            self.redis_client.flushdb()
            return True
        except Exception as e:
            print(f"Cache clear error: {e}")
            return False

    def cached(
        self,
        prefix: str,
        ttl: int = 3600
    ) -> Callable:
        """
        Decorator for caching function results

        Args:
            prefix: Cache key prefix
            ttl: Time to live in seconds (default 1 hour)

        Returns:
            Decorated function

        Example:
            @cache_manager.cached("user:profile", ttl=900)
            def get_user_profile(user_id: str):
                return expensive_database_query(user_id)
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key = self._make_key(prefix, *args, **kwargs)

                # Try to get from cache
                cached_result = self.get(cache_key)
                if cached_result is not None:
                    return cached_result

                # Execute function
                result = func(*args, **kwargs)

                # Cache result
                self.set(cache_key, result, ttl)

                return result

            # Add cache control methods to wrapper
            wrapper.invalidate = lambda *args, **kwargs: self.delete(
                self._make_key(prefix, *args, **kwargs)
            )
            wrapper.invalidate_all = lambda: self.delete_pattern(f"{prefix}:*")

            return wrapper
        return decorator


# Global cache manager instance
cache_manager = CacheManager()


# Cache presets for common use cases
class CachePresets:
    """Predefined cache TTLs for different use cases"""

    # Short-lived cache (5 minutes)
    SHORT = 300

    # Medium cache (15 minutes)
    MEDIUM = 900

    # Standard cache (1 hour)
    STANDARD = 3600

    # Long cache (24 hours)
    LONG = 86400

    # Very long cache (7 days)
    VERY_LONG = 604800


# Specific cache decorators for common operations
def cache_repository_health(ttl: int = CachePresets.STANDARD):
    """Cache repository health scores"""
    return cache_manager.cached("repo:health", ttl=ttl)


def cache_issue_stats(ttl: int = CachePresets.MEDIUM):
    """Cache issue statistics"""
    return cache_manager.cached("issue:stats", ttl=ttl)


def cache_user_permissions(ttl: int = CachePresets.MEDIUM):
    """Cache user permissions"""
    return cache_manager.cached("user:permissions", ttl=ttl)


def cache_analysis_results(ttl: int = CachePresets.LONG):
    """Cache analysis results"""
    return cache_manager.cached("analysis:results", ttl=ttl)


def cache_quality_trends(ttl: int = CachePresets.STANDARD):
    """Cache quality trend data"""
    return cache_manager.cached("quality:trends", ttl=ttl)


def cache_developer_stats(ttl: int = CachePresets.STANDARD):
    """Cache developer statistics"""
    return cache_manager.cached("developer:stats", ttl=ttl)


# Cache invalidation helpers
class CacheInvalidator:
    """Helper class for cache invalidation"""

    @staticmethod
    def invalidate_repository(repository_id: str):
        """Invalidate all cache for a repository"""
        patterns = [
            f"repo:health:{repository_id}:*",
            f"quality:trends:{repository_id}:*",
            f"analysis:results:{repository_id}:*"
        ]

        total = 0
        for pattern in patterns:
            total += cache_manager.delete_pattern(pattern)

        return total

    @staticmethod
    def invalidate_user(user_id: str):
        """Invalidate all cache for a user"""
        patterns = [
            f"user:permissions:{user_id}:*",
            f"developer:stats:{user_id}:*"
        ]

        total = 0
        for pattern in patterns:
            total += cache_manager.delete_pattern(pattern)

        return total

    @staticmethod
    def invalidate_pr(pr_id: str):
        """Invalidate all cache for a PR"""
        patterns = [
            f"analysis:results:*:{pr_id}:*",
            f"issue:stats:*:{pr_id}:*"
        ]

        total = 0
        for pattern in patterns:
            total += cache_manager.delete_pattern(pattern)

        return total
