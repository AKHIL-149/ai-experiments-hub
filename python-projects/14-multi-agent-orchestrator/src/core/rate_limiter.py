"""
Rate Limiting Implementation

Provides rate limiting functionality using Redis for distributed systems.
Uses sliding window algorithm for accurate rate limiting.
"""

import time
from typing import Optional, Tuple
from datetime import datetime, timedelta
import redis
from redis import Redis

from src.core.config import settings
from src.core.logging import logger


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded"""

    def __init__(self, message: str, retry_after: int):
        self.message = message
        self.retry_after = retry_after
        super().__init__(self.message)


class RateLimiter:
    """
    Rate limiter using sliding window algorithm with Redis backend

    Features:
    - Per-user rate limiting
    - Per-endpoint rate limiting
    - Global rate limiting
    - Distributed support via Redis
    - Sliding window algorithm for accuracy
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Initialize rate limiter

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

        logger.info("Rate limiter initialized with Redis backend")

    def _get_key(self, identifier: str, endpoint: Optional[str] = None) -> str:
        """
        Generate Redis key for rate limit tracking

        Args:
            identifier: User ID or IP address
            endpoint: API endpoint path (optional)

        Returns:
            str: Redis key
        """
        if endpoint:
            return f"rate_limit:{identifier}:{endpoint}"
        return f"rate_limit:{identifier}"

    def check_rate_limit(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int,
        endpoint: Optional[str] = None
    ) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit using sliding window

        Args:
            identifier: User ID or IP address
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds
            endpoint: API endpoint path (optional)

        Returns:
            tuple: (is_allowed, remaining_requests, reset_time)

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        key = self._get_key(identifier, endpoint)
        now = time.time()
        window_start = now - window_seconds

        try:
            # Use Redis sorted set with timestamps as scores
            pipe = self.redis.pipeline()

            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)

            # Count requests in current window
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {str(now): now})

            # Set expiry on the key
            pipe.expire(key, window_seconds)

            results = pipe.execute()
            current_count = results[1]

            # Check if limit exceeded
            if current_count >= max_requests:
                # Calculate when the oldest request will expire
                oldest = self.redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_timestamp = oldest[0][1]
                    retry_after = int((oldest_timestamp + window_seconds) - now)
                else:
                    retry_after = window_seconds

                # Remove the request we just added since it's not allowed
                self.redis.zrem(key, str(now))

                raise RateLimitExceeded(
                    f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds} seconds.",
                    retry_after=max(1, retry_after)
                )

            remaining = max_requests - current_count - 1
            reset_time = int(now + window_seconds)

            return True, remaining, reset_time

        except RateLimitExceeded:
            raise
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # On error, allow request (fail open)
            return True, max_requests, int(now + window_seconds)

    def get_rate_limit_info(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int,
        endpoint: Optional[str] = None
    ) -> dict:
        """
        Get current rate limit status without incrementing

        Args:
            identifier: User ID or IP address
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds
            endpoint: API endpoint path (optional)

        Returns:
            dict: Rate limit information
        """
        key = self._get_key(identifier, endpoint)
        now = time.time()
        window_start = now - window_seconds

        try:
            # Remove old entries
            self.redis.zremrangebyscore(key, 0, window_start)

            # Count current requests
            current_count = self.redis.zcard(key)

            remaining = max(0, max_requests - current_count)
            reset_time = int(now + window_seconds)

            return {
                "limit": max_requests,
                "remaining": remaining,
                "reset": reset_time,
                "used": current_count
            }

        except Exception as e:
            logger.error(f"Failed to get rate limit info: {e}")
            return {
                "limit": max_requests,
                "remaining": max_requests,
                "reset": int(now + window_seconds),
                "used": 0
            }

    def reset_rate_limit(
        self,
        identifier: str,
        endpoint: Optional[str] = None
    ) -> bool:
        """
        Reset rate limit for a user/endpoint

        Args:
            identifier: User ID or IP address
            endpoint: API endpoint path (optional)

        Returns:
            bool: True if reset successful
        """
        key = self._get_key(identifier, endpoint)

        try:
            self.redis.delete(key)
            logger.info(f"Reset rate limit for {identifier}")
            return True

        except Exception as e:
            logger.error(f"Failed to reset rate limit: {e}")
            return False

    def get_all_rate_limits(self, identifier: str) -> dict:
        """
        Get all rate limits for a user

        Args:
            identifier: User ID or IP address

        Returns:
            dict: All rate limits for the user
        """
        try:
            pattern = f"rate_limit:{identifier}:*"
            keys = self.redis.keys(pattern)

            rate_limits = {}
            for key in keys:
                endpoint = key.split(":")[-1]
                count = self.redis.zcard(key)
                rate_limits[endpoint] = count

            return rate_limits

        except Exception as e:
            logger.error(f"Failed to get all rate limits: {e}")
            return {}


# Rate limit tiers
class RateLimitTier:
    """Predefined rate limit tiers"""

    # Requests per minute
    VIEWER = {"max_requests": 60, "window_seconds": 60}  # 60 req/min
    USER = {"max_requests": 120, "window_seconds": 60}  # 120 req/min
    ADMIN = {"max_requests": 300, "window_seconds": 60}  # 300 req/min

    # Per-endpoint limits (stricter)
    TASK_CREATE = {"max_requests": 30, "window_seconds": 60}  # 30 req/min
    WORKFLOW_EXECUTE = {"max_requests": 10, "window_seconds": 60}  # 10 req/min
    AGENT_CREATE = {"max_requests": 20, "window_seconds": 60}  # 20 req/min

    # Global limits (per IP)
    GLOBAL_IP = {"max_requests": 1000, "window_seconds": 60}  # 1000 req/min
    GLOBAL_IP_STRICT = {"max_requests": 100, "window_seconds": 60}  # 100 req/min


# Global rate limiter instance
rate_limiter = RateLimiter()
