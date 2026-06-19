"""
Cache Service
Provides Redis caching with fallback to in-memory cache
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, Callable
from functools import wraps
import time


class CacheService:
    """
    Caching service with Redis support and in-memory fallback
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_client = None
        self.memory_cache: Dict[str, Dict] = {}
        self.cache_hits = 0
        self.cache_misses = 0
        self.use_redis = False

        # Try to initialize Redis if URL provided
        if redis_url:
            try:
                import redis
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                self.redis_client.ping()
                self.use_redis = True
                print(f"Redis cache initialized: {redis_url}")
            except Exception as e:
                print(f"Redis connection failed, using in-memory cache: {e}")
                self.redis_client = None

    # ============================================================================
    # Core Caching Operations
    # ============================================================================

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if self.use_redis and self.redis_client:
            try:
                value = self.redis_client.get(key)
                if value is not None:
                    self.cache_hits += 1
                    return json.loads(value)
                self.cache_misses += 1
                return None
            except Exception as e:
                print(f"Redis get error: {e}")
                self.use_redis = False

        # Fallback to memory cache
        if key in self.memory_cache:
            entry = self.memory_cache[key]

            # Check expiration
            if entry.get('expires_at'):
                if datetime.fromisoformat(entry['expires_at']) < datetime.now():
                    # Expired
                    del self.memory_cache[key]
                    self.cache_misses += 1
                    return None

            self.cache_hits += 1
            return entry['value']

        self.cache_misses += 1
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
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds (None = no expiration)

        Returns:
            True if successful
        """
        if self.use_redis and self.redis_client:
            try:
                serialized = json.dumps(value)
                if ttl:
                    self.redis_client.setex(key, ttl, serialized)
                else:
                    self.redis_client.set(key, serialized)
                return True
            except Exception as e:
                print(f"Redis set error: {e}")
                self.use_redis = False

        # Fallback to memory cache
        entry = {
            'value': value,
            'created_at': datetime.now().isoformat()
        }

        if ttl:
            entry['expires_at'] = (datetime.now() + timedelta(seconds=ttl)).isoformat()

        self.memory_cache[key] = entry
        return True

    def delete(self, key: str) -> bool:
        """
        Delete key from cache

        Args:
            key: Cache key

        Returns:
            True if key was deleted
        """
        if self.use_redis and self.redis_client:
            try:
                result = self.redis_client.delete(key)
                return result > 0
            except Exception as e:
                print(f"Redis delete error: {e}")
                self.use_redis = False

        # Fallback to memory cache
        if key in self.memory_cache:
            del self.memory_cache[key]
            return True

        return False

    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if self.use_redis and self.redis_client:
            try:
                return self.redis_client.exists(key) > 0
            except Exception as e:
                print(f"Redis exists error: {e}")
                self.use_redis = False

        # Fallback to memory cache
        if key in self.memory_cache:
            entry = self.memory_cache[key]

            # Check expiration
            if entry.get('expires_at'):
                if datetime.fromisoformat(entry['expires_at']) < datetime.now():
                    del self.memory_cache[key]
                    return False

            return True

        return False

    def clear(self) -> int:
        """
        Clear all cache entries

        Returns:
            Number of keys cleared
        """
        count = 0

        if self.use_redis and self.redis_client:
            try:
                # In production, use pattern matching to avoid clearing other apps' data
                # For now, flush the current database
                count = len(self.redis_client.keys('*'))
                self.redis_client.flushdb()
                return count
            except Exception as e:
                print(f"Redis clear error: {e}")
                self.use_redis = False

        # Fallback to memory cache
        count = len(self.memory_cache)
        self.memory_cache.clear()
        return count

    # ============================================================================
    # Pattern-Based Operations
    # ============================================================================

    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern

        Args:
            pattern: Key pattern (e.g., "analysis:*")

        Returns:
            Number of keys deleted
        """
        count = 0

        if self.use_redis and self.redis_client:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    count = self.redis_client.delete(*keys)
                return count
            except Exception as e:
                print(f"Redis delete_pattern error: {e}")
                self.use_redis = False

        # Fallback to memory cache
        import fnmatch
        keys_to_delete = [
            key for key in self.memory_cache.keys()
            if fnmatch.fnmatch(key, pattern)
        ]

        for key in keys_to_delete:
            del self.memory_cache[key]
            count += 1

        return count

    # ============================================================================
    # Decorator for Function Result Caching
    # ============================================================================

    def cached(self, ttl: int = 300, key_prefix: str = ''):
        """
        Decorator to cache function results

        Args:
            ttl: Time to live in seconds
            key_prefix: Prefix for cache key

        Usage:
            @cache_service.cached(ttl=300, key_prefix='user')
            def get_user(user_id):
                return fetch_user_from_db(user_id)
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key from function name and arguments
                key_parts = [key_prefix or func.__name__]

                # Add args
                for arg in args:
                    key_parts.append(str(arg))

                # Add kwargs (sorted for consistency)
                for k, v in sorted(kwargs.items()):
                    key_parts.append(f"{k}={v}")

                cache_key = self._generate_cache_key(':'.join(key_parts))

                # Try to get from cache
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # Execute function
                result = func(*args, **kwargs)

                # Cache result
                self.set(cache_key, result, ttl=ttl)

                return result

            return wrapper
        return decorator

    def _generate_cache_key(self, key: str) -> str:
        """
        Generate consistent cache key (hash long keys)

        Args:
            key: Input key

        Returns:
            Normalized cache key
        """
        # Hash very long keys
        if len(key) > 200:
            return 'hash:' + hashlib.md5(key.encode()).hexdigest()

        return key

    # ============================================================================
    # Statistics and Monitoring
    # ============================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0

        stats = {
            'backend': 'redis' if self.use_redis else 'memory',
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'total_requests': total_requests,
            'hit_rate_percent': round(hit_rate, 2),
            'memory_keys': len(self.memory_cache)
        }

        if self.use_redis and self.redis_client:
            try:
                info = self.redis_client.info('stats')
                stats['redis_keys'] = self.redis_client.dbsize()
                stats['redis_memory'] = info.get('used_memory_human', 'N/A')
            except Exception as e:
                print(f"Redis stats error: {e}")

        return stats

    def reset_statistics(self) -> None:
        """Reset cache statistics"""
        self.cache_hits = 0
        self.cache_misses = 0

    # ============================================================================
    # Bulk Operations
    # ============================================================================

    def get_many(self, keys: list) -> Dict[str, Any]:
        """
        Get multiple values from cache

        Args:
            keys: List of cache keys

        Returns:
            Dictionary of key-value pairs
        """
        result = {}

        if self.use_redis and self.redis_client:
            try:
                values = self.redis_client.mget(keys)
                for key, value in zip(keys, values):
                    if value is not None:
                        result[key] = json.loads(value)
                        self.cache_hits += 1
                    else:
                        self.cache_misses += 1
                return result
            except Exception as e:
                print(f"Redis mget error: {e}")
                self.use_redis = False

        # Fallback to memory cache
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value

        return result

    def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        Set multiple values in cache

        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        if self.use_redis and self.redis_client:
            try:
                pipeline = self.redis_client.pipeline()
                for key, value in mapping.items():
                    serialized = json.dumps(value)
                    if ttl:
                        pipeline.setex(key, ttl, serialized)
                    else:
                        pipeline.set(key, serialized)
                pipeline.execute()
                return True
            except Exception as e:
                print(f"Redis set_many error: {e}")
                self.use_redis = False

        # Fallback to memory cache
        for key, value in mapping.items():
            self.set(key, value, ttl=ttl)

        return True


# Global instance (initialized without Redis by default)
cache_service = CacheService()


def init_cache_from_env():
    """Initialize cache from environment variables"""
    import os
    redis_url = os.getenv('REDIS_URL') or os.getenv('CELERY_BROKER_URL')

    if redis_url:
        global cache_service
        cache_service = CacheService(redis_url=redis_url)
