"""
Unit tests for RateLimiter (src/middleware/rate_limiter.py).

These test RateLimiter.is_allowed() directly against a mocked Redis
client - not the middleware, and not through TestClient(app). conftest.py
patches RateLimitMiddleware.dispatch to a passthrough for the whole test
session (real Redis, real client IP would otherwise share one budget
across every test file), so these are the only tests in the suite that
actually exercise the enforcement logic itself.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.middleware.rate_limiter import RateLimiter, RATE_LIMITS


@pytest.fixture
def mock_redis():
    redis_mock = MagicMock()
    redis_mock.ping.return_value = True
    redis_mock.zremrangebyscore.return_value = 0
    redis_mock.zcard.return_value = 0
    redis_mock.zadd.return_value = 1
    redis_mock.expire.return_value = True
    redis_mock.zrange.return_value = []
    return redis_mock


@pytest.fixture
def rate_limiter(mock_redis):
    with patch('redis.from_url', return_value=mock_redis):
        return RateLimiter()


def test_rate_limiter_initialization_success(mock_redis):
    with patch('redis.from_url', return_value=mock_redis):
        limiter = RateLimiter()
        assert limiter.enabled is True


def test_rate_limiter_initialization_failure():
    """A Redis outage (or any redis-py exception, not just a plain
    connection/timeout error) must degrade to the in-memory fallback,
    not crash the app."""
    with patch('redis.from_url', side_effect=Exception("No Redis")):
        limiter = RateLimiter()
        assert limiter.enabled is False


def test_rate_limit_allowed_under_limit(rate_limiter, mock_redis):
    mock_redis.zcard.return_value = 2  # under the limit

    allowed, retry_after = rate_limiter.is_allowed(
        identifier="ip:1.2.3.4",
        endpoint="/api/auth/guest",
        limit=5,
        window=300
    )

    assert allowed is True
    assert retry_after == 0


def test_rate_limit_blocked_at_limit(rate_limiter, mock_redis):
    mock_redis.zcard.return_value = 5  # at the limit
    mock_redis.zrange.return_value = [(str(time.time() - 30), time.time() - 30)]

    allowed, retry_after = rate_limiter.is_allowed(
        identifier="ip:1.2.3.4",
        endpoint="/api/auth/guest",
        limit=5,
        window=300
    )

    assert allowed is False
    assert retry_after > 0


def test_rate_limiter_fails_open_on_redis_error(rate_limiter, mock_redis):
    """A Redis error mid-request should allow the request through rather
    than blocking all auth traffic on an infra hiccup."""
    mock_redis.zcard.side_effect = Exception("connection lost")

    allowed, retry_after = rate_limiter.is_allowed(
        identifier="ip:1.2.3.4",
        endpoint="/api/auth/guest",
        limit=5,
        window=300
    )

    assert allowed is True


def test_rate_limit_memory_fallback_enforces_limit():
    with patch('redis.from_url', side_effect=Exception("No Redis")):
        limiter = RateLimiter()

        allowed1, _ = limiter.is_allowed("ip:5.5.5.5", "/api/auth/guest", limit=2, window=60)
        assert allowed1 is True

        allowed2, _ = limiter.is_allowed("ip:5.5.5.5", "/api/auth/guest", limit=2, window=60)
        assert allowed2 is True

        allowed3, retry = limiter.is_allowed("ip:5.5.5.5", "/api/auth/guest", limit=2, window=60)
        assert allowed3 is False
        assert retry > 0


def test_rate_limit_configs_cover_auth_endpoints():
    assert '/api/auth/register' in RATE_LIMITS
    assert '/api/auth/login' in RATE_LIMITS
    assert '/api/auth/guest' in RATE_LIMITS
    assert 'default' in RATE_LIMITS

    # Account-creation endpoints should have strict limits - this is
    # what actually stops unlimited guest/register account creation.
    assert RATE_LIMITS['/api/auth/register']['limit'] <= 10
    assert RATE_LIMITS['/api/auth/guest']['limit'] <= 10
    assert RATE_LIMITS['/api/auth/login']['limit'] <= 10
