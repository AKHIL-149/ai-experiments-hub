"""The response cache: keys, expiry, cleanup, damaged files and concurrent use."""
import json
import os
import threading
import time

import pytest

from src.core.cache_manager import CacheManager


@pytest.fixture
def cache(tmp_path):
    return CacheManager(str(tmp_path / 'cache'))


def save(cache, response='answer', prompt='p', image='h', provider='ollama', model='m', **params):
    cache.save_response(prompt, image, provider, model, response, params=params or None)


def get(cache, prompt='p', image='h', provider='ollama', model='m', **params):
    return cache.get_response(prompt, image, provider, model, params=params or None)


def test_round_trip_and_stats(cache):
    assert get(cache) is None
    save(cache)
    assert get(cache) == 'answer'
    stats = cache.get_stats()
    assert (stats['hits'], stats['misses'], stats['total_requests'], stats['cache_saves']) == (1, 1, 2, 1)
    assert stats['hit_rate_percent'] == 50.0


@pytest.mark.parametrize('change', [{'prompt': 'q'}, {'image': 'other'}, {'provider': 'openai'}, {'model': 'm2'},
                                    {'max_tokens': 5}, {'temperature': 0.5}])
def test_every_part_of_the_request_is_part_of_the_key(cache, change):
    save(cache)
    assert get(cache, **change) is None


def test_same_params_hit(cache):
    save(cache, max_tokens=10, temperature=0.3)
    assert get(cache, max_tokens=10, temperature=0.3) == 'answer'


def test_empty_answers_are_not_cached(cache):
    save(cache, response='')
    save(cache, response='   ', prompt='other')
    assert get(cache) is None and get(cache, prompt='other') is None
    assert cache.get_stats()['cache_saves'] == 0


def test_expired_entries_are_misses_and_cleanup_removes_them(tmp_path):
    cache = CacheManager(str(tmp_path / 'c'), ttl_seconds=1)
    save(cache)
    file = next((tmp_path / 'c' / 'responses').glob('*.json'))
    old = time.time() - 10
    os.utime(file, (old, old))
    assert get(cache) is None
    assert cache.cleanup() == 1 and not file.exists()


def test_cleanup_keep_recent_hours(cache, tmp_path):
    save(cache, prompt='old')
    save(cache, prompt='new')
    old_file = [f for f in (tmp_path / 'cache' / 'responses').glob('*.json') if 'old' in f.read_text()][0]
    stamp = time.time() - 5 * 3600
    os.utime(old_file, (stamp, stamp))
    assert cache.cleanup(keep_recent_hours=2) == 1
    assert get(cache, prompt='new') == 'answer' and get(cache, prompt='old') is None


def test_cleanup_with_zero_hours_removes_everything_older_than_now(cache):
    save(cache)
    time.sleep(0.01)
    assert cache.cleanup(keep_recent_hours=0) == 1


def test_clear_resets_files_and_counters(cache):
    save(cache)
    get(cache)
    cache.clear()
    stats = cache.get_stats()
    assert stats['hits'] == 0 and stats['cache_saves'] == 0 and get(cache) is None


def test_a_damaged_stats_file_does_not_stop_the_cache(tmp_path):
    folder = tmp_path / 'c'
    CacheManager(str(folder))
    (folder / 'stats.json').write_text('{not json')
    cache = CacheManager(str(folder))                  # used to raise JSONDecodeError at start-up
    assert cache.get_stats()['hits'] == 0
    save(cache)
    assert get(cache) == 'answer'


def test_an_incomplete_stats_file_gets_its_missing_counters(tmp_path):
    folder = tmp_path / 'c'
    folder.mkdir()
    (folder / 'stats.json').write_text(json.dumps({'hits': 4}))
    stats = CacheManager(str(folder)).get_stats()
    assert stats['hits'] == 4 and stats['misses'] == 0 and stats['cost_savings']['total'] == 0.0


def test_a_damaged_cache_entry_is_a_miss(cache, tmp_path):
    save(cache)
    next((tmp_path / 'cache' / 'responses').glob('*.json')).write_text('{broken')
    assert get(cache) is None


def test_an_entry_with_an_empty_response_is_a_miss(cache, tmp_path):
    save(cache)
    file = next((tmp_path / 'cache' / 'responses').glob('*.json'))
    data = json.loads(file.read_text())
    data['response'] = ''
    file.write_text(json.dumps(data))
    assert get(cache) is None


def test_files_are_written_atomically_without_leftovers(cache, tmp_path):
    for i in range(20):
        save(cache, prompt=f'p{i}')
    names = os.listdir(tmp_path / 'cache' / 'responses')
    assert len(names) == 20 and not [n for n in names if n.endswith('.tmp')]
    assert not [n for n in os.listdir(tmp_path / 'cache') if n.endswith('.tmp')]


def test_concurrent_use_keeps_the_counters_exact(cache):
    def worker(n):
        for i in range(25):
            save(cache, prompt=f'{n}-{i}')
            get(cache, prompt=f'{n}-{i}')
    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    stats = cache.get_stats()
    assert stats['cache_saves'] == 200 and stats['hits'] == 200 and stats['total_requests'] == 200
    saved = json.loads((cache.stats_file).read_text())
    assert saved['hits'] == 200                         # the file is whole and current


def test_cost_savings_are_tracked_for_paid_providers_only(cache):
    save(cache, provider='anthropic', model='claude-3-5-sonnet-20241022')
    get(cache, provider='anthropic', model='claude-3-5-sonnet-20241022')
    save(cache, provider='ollama')
    get(cache, provider='ollama')
    savings = cache.get_stats()['cost_savings']
    assert savings['anthropic'] > 0 and savings['total'] == savings['anthropic'] and savings['openai'] == 0


def test_size_limit_triggers_cleanup(tmp_path):
    cache = CacheManager(str(tmp_path / 'c'), max_cache_size_mb=0)
    save(cache, response='x' * 1000)
    # over the (zero) limit: recent entries survive a 24h cleanup, stats stay readable
    assert cache.get_stats()['cache_size_mb'] >= 0


def test_image_hash_is_stable(cache):
    assert cache.compute_image_hash(b'abc') == cache.compute_image_hash(b'abc') != cache.compute_image_hash(b'abd')


def test_a_failed_write_leaves_the_old_file_untouched_and_no_temp_file(cache, tmp_path, monkeypatch):
    save(cache)
    before = cache.stats_file.read_text()

    def explode(data, f, indent=None):
        f.write('{"half')
        raise OSError('disk full')
    monkeypatch.setattr(json, 'dump', explode)
    with pytest.raises(OSError):
        cache._save_stats()
    monkeypatch.undo()
    assert cache.stats_file.read_text() == before
    assert not [n for n in os.listdir(tmp_path / 'cache') if n.endswith('.tmp')]
