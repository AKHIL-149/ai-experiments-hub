"""
Rate Limiting Middleware
Protects API endpoints from abuse with configurable rate limits per user/IP

Ported from project 13's src/middleware/rate_limiter.py - same implementation,
adapted RATE_LIMITS for this project's actual endpoints. That version already
had its own bug fixed (a narrow except clause on Redis init that let anything
other than a plain connection/timeout error crash the app instead of
degrading to the in-memory fallback - see the comment on __init__ below), so
porting it rather than writing a new one from scratch avoids reintroducing
that.

Found and fixed a second, more serious bug while verifying this port live
(project 13's copy has the same one, unfixed): _check_redis used
{str(now): now} as the ZADD mapping, where `now = int(time.time())` -
member AND score both derived from the same whole-second timestamp. ZADD
treats the member as a unique key, so two requests landing in the same
second collapse into ONE sorted-set entry instead of two, silently
undercounting. Confirmed live: 6 rapid /api/auth/guest calls (a plain
curl loop, nothing exotic) only produced 3 entries in Redis and all 6
were allowed through a limit of 5 - exactly the "script hammering an
endpoint" pattern this is supposed to stop, defeated by its own
sub-second imprecision. Fixed by giving every request a unique member
(timestamp + a random suffix) while keeping the timestamp as the score,
so ZREMRANGEBYSCORE/ZRANGE windowing (which operates on scores, not
members) is unaffected.
"""

import time
import uuid
from typing import Optional, Dict
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import redis
import os


class RateLimiter:
    """Redis-based rate limiter"""

    def __init__(self):
        """Initialize rate limiter with Redis"""
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

        try:
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5
            )
            self.redis_client.ping()
            self.enabled = True
        except Exception as e:
            # Broad except (not just ConnectionError/TimeoutError): DNS
            # failures, auth errors, and other redis-py exceptions
            # shouldn't crash RateLimiter.__init__ and take the whole
            # app down with it - fall back to in-memory instead.
            print(f"Warning: Redis connection failed for rate limiter: {e}")
            print("Rate limiting will use in-memory fallback (not recommended for production)")
            self.redis_client = None
            self.enabled = False
            # In-memory fallback (not suitable for multi-process deployments)
            self._memory_store: Dict[str, list] = defaultdict(list)

    def _get_key(self, identifier: str, endpoint: str) -> str:
        """Generate Redis key for rate limiting"""
        return f"ratelimit:{identifier}:{endpoint}"

    def is_allowed(
        self,
        identifier: str,
        endpoint: str,
        limit: int,
        window: int
    ) -> tuple[bool, int]:
        """
        Check if request is allowed under rate limit

        Args:
            identifier: User ID or IP address
            endpoint: API endpoint
            limit: Maximum requests allowed
            window: Time window in seconds

        Returns:
            Tuple of (allowed: bool, retry_after: int)
        """
        if self.enabled:
            return self._check_redis(identifier, endpoint, limit, window)
        else:
            return self._check_memory(identifier, endpoint, limit, window)

    def _check_redis(
        self,
        identifier: str,
        endpoint: str,
        limit: int,
        window: int
    ) -> tuple[bool, int]:
        """Check rate limit using Redis"""
        key = self._get_key(identifier, endpoint)
        now = int(time.time())
        window_start = now - window

        try:
            # Remove old entries
            self.redis_client.zremrangebyscore(key, 0, window_start)

            # Count requests in current window
            count = self.redis_client.zcard(key)

            if count >= limit:
                # Get oldest entry to calculate retry_after
                oldest = self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_time = int(oldest[0][1])
                    retry_after = window - (now - oldest_time)
                    return False, max(1, retry_after)
                return False, window

            # Add current request - member must be unique per request, not
            # just per-second, or concurrent/rapid requests within the same
            # whole second collapse into one ZADD entry and get undercounted.
            member = f"{now}-{uuid.uuid4().hex}"
            self.redis_client.zadd(key, {member: now})
            self.redis_client.expire(key, window)

            return True, 0

        except Exception as e:
            print(f"Rate limiter error: {e}")
            # Fail open - allow request on error
            return True, 0

    def _check_memory(
        self,
        identifier: str,
        endpoint: str,
        limit: int,
        window: int
    ) -> tuple[bool, int]:
        """Check rate limit using in-memory storage (fallback)"""
        key = f"{identifier}:{endpoint}"
        now = time.time()
        window_start = now - window

        # Clean old entries
        self._memory_store[key] = [
            timestamp for timestamp in self._memory_store[key]
            if timestamp > window_start
        ]

        if len(self._memory_store[key]) >= limit:
            oldest = min(self._memory_store[key])
            retry_after = int(window - (now - oldest))
            return False, max(1, retry_after)

        # Add current request
        self._memory_store[key].append(now)

        return True, 0

    def reset(self, identifier: str, endpoint: str):
        """Reset rate limit for identifier/endpoint"""
        if self.enabled:
            key = self._get_key(identifier, endpoint)
            try:
                self.redis_client.delete(key)
            except Exception as e:
                print(f"Rate limiter reset error: {e}")
        else:
            key = f"{identifier}:{endpoint}"
            if key in self._memory_store:
                del self._memory_store[key]


# Rate limit configurations for different endpoints
RATE_LIMITS = {
    # Authentication endpoints - strict limits. /api/auth/guest gets the
    # same budget as register since it's the same abuse vector (unlimited
    # account creation from one client), just without a form.
    '/api/auth/register': {'limit': 5, 'window': 300},  # 5 per 5 minutes
    '/api/auth/guest': {'limit': 5, 'window': 300},      # 5 per 5 minutes
    '/api/auth/login': {'limit': 5, 'window': 60},       # 5 per minute
    '/api/auth/logout': {'limit': 10, 'window': 60},     # 10 per minute

    # Content submission - moderate limits
    '/api/content': {'limit': 30, 'window': 60},         # 30 per minute
    '/api/appeals': {'limit': 10, 'window': 60},         # 10 per minute

    # General API - relaxed limits
    'default': {'limit': 100, 'window': 60}              # 100 per minute
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting"""

    def __init__(self, app):
        super().__init__(app)
        self.rate_limiter = RateLimiter()

    def _get_identifier(self, request: Request) -> str:
        """Get identifier for rate limiting (user ID or IP)"""
        # Try to get user ID from request state (set by auth middleware)
        if hasattr(request.state, 'user') and request.state.user:
            return f"user:{request.state.user.id}"

        # Fall back to IP address
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            # Get first IP from X-Forwarded-For
            ip = forwarded_for.split(',')[0].strip()
        else:
            ip = request.client.host if request.client else 'unknown'

        return f"ip:{ip}"

    def _get_rate_limit_config(self, path: str) -> dict:
        """Get rate limit configuration for endpoint"""
        # Check for exact match
        if path in RATE_LIMITS:
            return RATE_LIMITS[path]

        # Check for prefix match
        for pattern, config in RATE_LIMITS.items():
            if pattern != 'default' and path.startswith(pattern):
                return config

        # Default rate limit
        return RATE_LIMITS['default']

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting"""
        # Skip rate limiting for health checks and static files
        if request.url.path in ['/health', '/api/health', '/favicon.ico'] or \
           request.url.path.startswith('/static/'):
            return await call_next(request)

        # Get identifier and rate limit config
        identifier = self._get_identifier(request)
        config = self._get_rate_limit_config(request.url.path)

        # Check rate limit
        allowed, retry_after = self.rate_limiter.is_allowed(
            identifier=identifier,
            endpoint=request.url.path,
            limit=config['limit'],
            window=config['window']
        )

        if not allowed:
            # Rate limit exceeded
            return JSONResponse(
                status_code=429,
                content={
                    'error': 'Rate limit exceeded',
                    'detail': f"Too many requests. Retry after {retry_after} seconds.",
                    'retry_after': retry_after
                },
                headers={
                    'Retry-After': str(retry_after),
                    'X-RateLimit-Limit': str(config['limit']),
                    'X-RateLimit-Window': str(config['window'])
                }
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers['X-RateLimit-Limit'] = str(config['limit'])
        response.headers['X-RateLimit-Window'] = str(config['window'])

        return response
