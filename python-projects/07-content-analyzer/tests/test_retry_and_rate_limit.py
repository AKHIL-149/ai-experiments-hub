"""Retry with backoff and the request-rate limiter."""
import threading
import time

import pytest

from src.core.rate_limiter import RateLimiter, get_rate_limiter
from src.core.retry_handler import RetryHandler


def flaky(failures, error=ValueError):
    state = {'calls': 0}

    def func(x=0):
        state['calls'] += 1
        if state['calls'] <= failures:
            raise error(f'fail {state["calls"]}')
        return 'ok'
    return func, state


def test_success_after_retries():
    func, state = flaky(2)
    assert RetryHandler(max_retries=3, base_delay=0).retry(func) == 'ok'
    assert state['calls'] == 3


def test_gives_up_with_the_last_error():
    func, state = flaky(10)
    with pytest.raises(ValueError, match='fail 3'):
        RetryHandler(max_retries=2, base_delay=0).retry(func)
    assert state['calls'] == 3


def test_only_listed_exceptions_are_retried():
    func, state = flaky(5, error=KeyError)
    with pytest.raises(KeyError):
        RetryHandler(max_retries=3, base_delay=0).retry(func, retryable_exceptions=(ValueError,))
    assert state['calls'] == 1


def test_should_retry_can_veto_a_retry():
    func, state = flaky(5)
    with pytest.raises(ValueError, match='fail 1'):
        RetryHandler(max_retries=3, base_delay=0).retry(func, should_retry=lambda e: False)
    assert state['calls'] == 1


def test_on_retry_callback_and_arguments_are_passed_through():
    seen = []
    func, _ = flaky(1)
    assert RetryHandler(max_retries=2, base_delay=0).retry(func, x=5, on_retry=lambda n, e: seen.append((n, str(e)))) == 'ok'
    assert seen == [(1, 'fail 1')]


def test_delays_grow_exponentially_up_to_the_maximum():
    h = RetryHandler(base_delay=1, exponential_base=2, max_delay=5, jitter=False)
    assert [h._calculate_delay(i) for i in range(5)] == [1, 2, 4, 5, 5]


def test_jitter_stays_between_half_and_full_delay():
    h = RetryHandler(base_delay=4, jitter=True)
    assert all(2 <= h._calculate_delay(0) <= 4 for _ in range(50))


def test_zero_retries_means_one_attempt():
    func, state = flaky(1)
    with pytest.raises(ValueError):
        RetryHandler(max_retries=0).retry(func)
    assert state['calls'] == 1


def test_decorator_form():
    func, state = flaky(1)
    wrapped = RetryHandler(max_retries=2, base_delay=0)(retryable_exceptions=(ValueError,))(func)
    assert wrapped() == 'ok' and state['calls'] == 2


# ------------------------------------------------------------------ rate limiter

def test_requests_over_the_minute_limit_wait():
    limiter = RateLimiter(requests_per_minute=2)
    assert limiter.acquire() and limiter.acquire()
    with pytest.raises(TimeoutError):
        limiter.acquire(timeout=0.3)
    assert limiter.get_stats()['requests_last_minute'] == 2


def test_old_requests_leave_the_window(monkeypatch):
    limiter = RateLimiter(requests_per_minute=1)
    limiter.acquire()
    limiter.minute_window[0] -= 61
    assert limiter.acquire(timeout=0.5)


def test_hour_limit_applies_too():
    limiter = RateLimiter(requests_per_minute=100, requests_per_hour=1)
    limiter.acquire()
    with pytest.raises(TimeoutError):
        limiter.acquire(timeout=0.3)
    assert limiter.get_stats()['requests_per_hour_limit'] == 1


def test_many_threads_never_exceed_the_limit():
    limiter = RateLimiter(requests_per_minute=10)
    granted = []

    def worker():
        try:
            limiter.acquire(timeout=0.5)
            granted.append(1)
        except TimeoutError:
            pass
    threads = [threading.Thread(target=worker) for _ in range(30)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(granted) == 10


def test_provider_limiters():
    assert get_rate_limiter('anthropic') is get_rate_limiter('anthropic')
    assert get_rate_limiter('anthropic').requests_per_minute == 50
    assert get_rate_limiter('unknown-provider').requests_per_minute == 60
