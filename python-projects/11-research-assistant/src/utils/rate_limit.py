"""Small in-memory limiter for repeated failures (failed logins)"""

import threading
import time
from collections import deque
from typing import Deque, Dict


class FailureThrottle:
    """
    Blocks a key after `max_failures` failures within `window_seconds`.

    Kept in memory: a restart forgets it, which is fine for slowing down password guessing.
    """

    def __init__(self, max_failures: int = 10, window_seconds: int = 300, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window_seconds
        self.clock = clock
        self._failures: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> Deque[float]:
        failures = self._failures.get(key)
        if failures is None:
            return deque()
        while failures and now - failures[0] >= self.window:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return deque()
        return failures

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again (0 if it may try now)"""
        with self._lock:
            now = self.clock()
            failures = self._recent(key, now)
            if len(failures) < self.max_failures:
                return 0
            return max(1, int(self.window - (now - failures[0])) + 1)

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            self._recent(key, now)
            self._failures.setdefault(key, deque()).append(now)
            if len(self._failures) > 10000:  # bound memory under a username-spraying flood
                self._failures.pop(next(iter(self._failures)))

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
