"""Tests for Performance Optimizations"""
import pytest
from src.core.database import (
    DatabaseManager,
    Issue,
    PullRequest,
    AnalysisJob,
    Base
)
from src.services.cache_service import CacheService


def test_issue_has_composite_indexes():
    """Test that Issue model has composite indexes defined"""
    assert hasattr(Issue, '__table_args__')
    assert Issue.__table_args__ is not None

    # Check that indexes are defined
    indexes = [item for item in Issue.__table_args__ if hasattr(item, 'name')]
    index_names = [idx.name for idx in indexes]

    assert 'idx_issue_category_severity' in index_names
    assert 'idx_issue_file_severity' in index_names
    assert 'idx_issue_created_severity' in index_names


def test_pullrequest_has_composite_indexes():
    """Test that PullRequest model has composite indexes defined"""
    assert hasattr(PullRequest, '__table_args__')
    assert PullRequest.__table_args__ is not None

    indexes = [item for item in PullRequest.__table_args__ if hasattr(item, 'name')]
    index_names = [idx.name for idx in indexes]

    assert 'idx_pr_repo_status' in index_names
    assert 'idx_pr_repo_created' in index_names
    assert 'idx_pr_status_created' in index_names


def test_analysisjob_has_composite_indexes():
    """Test that AnalysisJob model has composite indexes defined"""
    assert hasattr(AnalysisJob, '__table_args__')
    assert AnalysisJob.__table_args__ is not None

    indexes = [item for item in AnalysisJob.__table_args__ if hasattr(item, 'name')]
    index_names = [idx.name for idx in indexes]

    assert 'idx_job_pr_status' in index_names
    assert 'idx_job_status_started' in index_names


def test_issue_has_timestamp_indexes():
    """Test that Issue model has timestamp index"""
    # Check that created_at has index=True
    assert Issue.created_at.index == True


def test_pullrequest_has_timestamp_indexes():
    """Test that PullRequest model has timestamp indexes"""
    assert PullRequest.created_at.index == True
    assert PullRequest.updated_at.index == True


def test_cache_integration_with_database():
    """Test that cache can be used with database queries"""
    cache = CacheService()
    cache.clear()

    # Simulate caching database query results
    mock_issues = [
        {'id': '1', 'severity': 'critical'},
        {'id': '2', 'severity': 'error'}
    ]

    # Cache the results
    cache.set('issues:critical', mock_issues, ttl=60)

    # Retrieve from cache
    cached_issues = cache.get('issues:critical')

    assert cached_issues == mock_issues
    assert len(cached_issues) == 2


def test_cache_decorator_for_query_results():
    """Test using cache decorator for expensive queries"""
    cache = CacheService()
    cache.clear()

    query_count = 0

    @cache.cached(ttl=60, key_prefix='expensive_query')
    def expensive_database_query(param):
        nonlocal query_count
        query_count += 1
        return {'result': f'data-{param}'}

    # First call - executes query
    result1 = expensive_database_query('test')
    assert result1 == {'result': 'data-test'}
    assert query_count == 1

    # Second call - uses cache
    result2 = expensive_database_query('test')
    assert result2 == {'result': 'data-test'}
    assert query_count == 1  # Not incremented


def test_cache_statistics_tracking():
    """Test that cache statistics are tracked"""
    cache = CacheService()
    cache.reset_statistics()

    cache.set('key1', 'value1')
    cache.get('key1')  # Hit
    cache.get('key1')  # Hit
    cache.get('nonexistent')  # Miss

    stats = cache.get_statistics()

    assert stats['cache_hits'] == 2
    assert stats['cache_misses'] == 1
    assert stats['hit_rate_percent'] > 0
