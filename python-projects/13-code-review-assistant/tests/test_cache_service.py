"""Tests for Cache Service"""
import pytest
import time
from src.services.cache_service import CacheService, cache_service


@pytest.fixture
def service():
    """Create fresh cache service with in-memory backend"""
    svc = CacheService()  # No Redis URL = memory backend
    svc.clear()
    svc.reset_statistics()
    return svc


def test_set_and_get(service):
    """Test basic set and get operations"""
    service.set('test_key', 'test_value')
    value = service.get('test_key')

    assert value == 'test_value'


def test_set_with_ttl(service):
    """Test setting value with TTL"""
    service.set('expire_key', 'value', ttl=1)

    # Should exist immediately
    assert service.get('expire_key') == 'value'

    # Wait for expiration
    time.sleep(1.1)

    # Should be None after TTL
    assert service.get('expire_key') is None


def test_get_nonexistent_key(service):
    """Test getting non-existent key"""
    value = service.get('nonexistent')

    assert value is None


def test_delete_key(service):
    """Test deleting a key"""
    service.set('delete_me', 'value')
    assert service.exists('delete_me')

    result = service.delete('delete_me')

    assert result == True
    assert not service.exists('delete_me')


def test_exists(service):
    """Test checking key existence"""
    assert not service.exists('test')

    service.set('test', 'value')

    assert service.exists('test')


def test_clear_cache(service):
    """Test clearing all cache entries"""
    service.set('key1', 'value1')
    service.set('key2', 'value2')
    service.set('key3', 'value3')

    count = service.clear()

    assert count == 3
    assert not service.exists('key1')
    assert not service.exists('key2')


def test_delete_pattern(service):
    """Test deleting keys by pattern"""
    service.set('user:1', 'data1')
    service.set('user:2', 'data2')
    service.set('post:1', 'post_data')

    # Delete all user keys
    count = service.delete_pattern('user:*')

    assert count == 2
    assert not service.exists('user:1')
    assert not service.exists('user:2')
    assert service.exists('post:1')


def test_cache_statistics(service):
    """Test cache statistics tracking"""
    # Generate some hits and misses
    service.set('key1', 'value1')

    service.get('key1')  # Hit
    service.get('key1')  # Hit
    service.get('nonexistent')  # Miss

    stats = service.get_statistics()

    assert stats['cache_hits'] == 2
    assert stats['cache_misses'] == 1
    assert stats['total_requests'] == 3
    assert stats['hit_rate_percent'] > 0
    assert stats['backend'] == 'memory'


def test_reset_statistics(service):
    """Test resetting cache statistics"""
    service.get('nonexistent')  # Create a miss

    service.reset_statistics()

    stats = service.get_statistics()

    assert stats['cache_hits'] == 0
    assert stats['cache_misses'] == 0


def test_cached_decorator(service):
    """Test the @cached decorator"""
    call_count = 0

    @service.cached(ttl=60, key_prefix='test_func')
    def expensive_function(arg1, arg2='default'):
        nonlocal call_count
        call_count += 1
        return f"{arg1}-{arg2}"

    # First call - should execute function
    result1 = expensive_function('value1', arg2='value2')
    assert result1 == 'value1-value2'
    assert call_count == 1

    # Second call with same args - should use cache
    result2 = expensive_function('value1', arg2='value2')
    assert result2 == 'value1-value2'
    assert call_count == 1  # Not incremented

    # Call with different args - should execute function
    result3 = expensive_function('value3')
    assert result3 == 'value3-default'
    assert call_count == 2


def test_cache_complex_types(service):
    """Test caching complex data types"""
    data = {
        'user': {
            'id': 123,
            'name': 'John',
            'tags': ['admin', 'user']
        },
        'metadata': {
            'created_at': '2024-01-01',
            'count': 42
        }
    }

    service.set('complex_data', data)
    retrieved = service.get('complex_data')

    assert retrieved == data
    assert retrieved['user']['name'] == 'John'
    assert 'admin' in retrieved['user']['tags']


def test_get_many(service):
    """Test getting multiple keys at once"""
    service.set('key1', 'value1')
    service.set('key2', 'value2')
    service.set('key3', 'value3')

    result = service.get_many(['key1', 'key2', 'nonexistent'])

    assert result['key1'] == 'value1'
    assert result['key2'] == 'value2'
    assert 'nonexistent' not in result


def test_set_many(service):
    """Test setting multiple keys at once"""
    mapping = {
        'key1': 'value1',
        'key2': 'value2',
        'key3': 'value3'
    }

    result = service.set_many(mapping)

    assert result == True
    assert service.get('key1') == 'value1'
    assert service.get('key2') == 'value2'
    assert service.get('key3') == 'value3'


def test_set_many_with_ttl(service):
    """Test setting multiple keys with TTL"""
    mapping = {
        'expire1': 'value1',
        'expire2': 'value2'
    }

    service.set_many(mapping, ttl=1)

    # Should exist immediately
    assert service.get('expire1') == 'value1'

    # Wait for expiration
    time.sleep(1.1)

    # Should be None after TTL
    assert service.get('expire1') is None


def test_generate_cache_key_long(service):
    """Test cache key generation for very long keys"""
    long_key = 'x' * 300  # Very long key

    normalized = service._generate_cache_key(long_key)

    # Should be hashed
    assert normalized.startswith('hash:')
    assert len(normalized) < len(long_key)


def test_generate_cache_key_short(service):
    """Test cache key generation for short keys"""
    short_key = 'short_key'

    normalized = service._generate_cache_key(short_key)

    # Should be unchanged
    assert normalized == short_key


def test_global_cache_service_instance():
    """Test that global instance exists"""
    assert cache_service is not None
    assert isinstance(cache_service, CacheService)

    # Can use cache
    cache_service.set('global_test', 'value')
    assert cache_service.get('global_test') == 'value'


def test_cache_list_values(service):
    """Test caching list values"""
    data = [1, 2, 3, 4, 5]

    service.set('list_data', data)
    retrieved = service.get('list_data')

    assert retrieved == data
    assert len(retrieved) == 5


def test_cache_null_values(service):
    """Test caching None/null values"""
    # Note: None is treated as "not found", so we wrap it
    service.set('null_value', {'value': None})
    retrieved = service.get('null_value')

    assert retrieved == {'value': None}
    assert retrieved['value'] is None
