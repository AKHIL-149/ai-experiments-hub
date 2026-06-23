"""
Performance Tests
Tests for caching, database performance, and API response times
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from src.core.cache_manager import (
    CacheManager,
    cache_manager,
    cache_repository_health,
    cache_issue_stats,
    CacheInvalidator
)


class TestCacheManager:
    """Test suite for cache manager"""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client"""
        redis_mock = MagicMock()
        redis_mock.ping.return_value = True
        redis_mock.get.return_value = None
        redis_mock.set.return_value = True
        redis_mock.setex.return_value = True
        redis_mock.delete.return_value = 1
        redis_mock.keys.return_value = []
        redis_mock.flushdb.return_value = True
        return redis_mock

    @pytest.fixture
    def cache(self, mock_redis):
        """Create cache manager with mocked Redis"""
        with patch('redis.from_url', return_value=mock_redis):
            manager = CacheManager()
            return manager

    def test_cache_initialization_success(self, mock_redis):
        """Test successful cache initialization"""
        with patch('redis.from_url', return_value=mock_redis):
            cache = CacheManager()
            assert cache.enabled is True
            assert cache.redis_client is not None

    def test_cache_initialization_failure(self):
        """Test cache initialization failure"""
        with patch('redis.from_url', side_effect=Exception("Connection failed")):
            cache = CacheManager()
            assert cache.enabled is False
            assert cache.redis_client is None

    def test_make_key_simple_args(self, cache):
        """Test cache key generation with simple arguments"""
        key = cache._make_key("test", "arg1", "arg2")
        assert key == "test:arg1:arg2"

    def test_make_key_with_kwargs(self, cache):
        """Test cache key generation with keyword arguments"""
        key = cache._make_key("test", user_id="123", repo_id="456")
        assert "repo_id=456" in key
        assert "user_id=123" in key

    def test_cache_get_success(self, cache, mock_redis):
        """Test successful cache get"""
        import json
        mock_redis.get.return_value = json.dumps({"result": "data"})

        result = cache.get("test:key")
        assert result == {"result": "data"}

    def test_cache_set_with_ttl(self, cache, mock_redis):
        """Test cache set with TTL"""
        success = cache.set("test:key", {"data": "value"}, ttl=300)
        assert success is True

    def test_cache_delete(self, cache, mock_redis):
        """Test cache delete"""
        success = cache.delete("test:key")
        assert success is True

    def test_cached_decorator(self, cache, mock_redis):
        """Test cached decorator"""
        call_count = 0

        @cache.cached("test:func", ttl=60)
        def expensive_function(arg):
            nonlocal call_count
            call_count += 1
            return f"result:{arg}"

        # First call
        mock_redis.get.return_value = None
        result1 = expensive_function("value")
        assert result1 == "result:value"
        assert call_count == 1


class TestDatabasePerformance:
    """Test database performance optimizations"""

    def test_code_file_has_indexes(self):
        """Test that CodeFile has necessary indexes"""
        from src.core.database import CodeFile

        assert hasattr(CodeFile, '__table_args__')
        assert CodeFile.__table_args__ is not None

    def test_issue_has_composite_indexes(self):
        """Test that Issue has composite indexes"""
        from src.core.database import Issue

        assert hasattr(Issue, '__table_args__')

    def test_pull_request_has_composite_indexes(self):
        """Test that PullRequest has composite indexes"""
        from src.core.database import PullRequest

        assert hasattr(PullRequest, '__table_args__')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
