"""Rate limiter for API calls."""
import time
from typing import Dict, Optional
from collections import deque
from threading import Lock


class RateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: Optional[int] = None
    ):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute
            requests_per_hour: Maximum requests per hour (optional)
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour

        # Track request timestamps
        self.minute_window = deque()
        self.hour_window = deque() if requests_per_hour else None

        # Thread-safe lock
        self.lock = Lock()

    def _clean_window(self, window: deque, duration_seconds: int):
        """Remove timestamps outside the time window.

        Args:
            window: Deque of timestamps
            duration_seconds: Window duration in seconds
        """
        current_time = time.time()
        cutoff = current_time - duration_seconds

        while window and window[0] < cutoff:
            window.popleft()

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """Acquire permission to make an API call.

        Args:
            timeout: Maximum time to wait in seconds (None = wait forever)

        Returns:
            True if permission granted, False if timeout

        Raises:
            TimeoutError: If timeout is reached
        """
        start_time = time.time()

        while True:
            with self.lock:
                # Clean old timestamps
                self._clean_window(self.minute_window, 60)
                if self.hour_window:
                    self._clean_window(self.hour_window, 3600)

                # Check if we can proceed
                minute_ok = len(self.minute_window) < self.requests_per_minute
                hour_ok = (
                    self.hour_window is None or
                    len(self.hour_window) < self.requests_per_hour
                )

                if minute_ok and hour_ok:
                    # Grant permission
                    current_time = time.time()
                    self.minute_window.append(current_time)
                    if self.hour_window is not None:
                        self.hour_window.append(current_time)
                    return True

            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise TimeoutError("Rate limit acquisition timeout")

            # Wait before retrying
            time.sleep(0.1)

    def get_stats(self) -> Dict[str, int]:
        """Get current rate limiter statistics.

        Returns:
            Dictionary with current usage
        """
        with self.lock:
            self._clean_window(self.minute_window, 60)
            if self.hour_window:
                self._clean_window(self.hour_window, 3600)

            return {
                'requests_last_minute': len(self.minute_window),
                'requests_per_minute_limit': self.requests_per_minute,
                'requests_last_hour': len(self.hour_window) if self.hour_window else 0,
                'requests_per_hour_limit': self.requests_per_hour or 0
            }


# Default rate limiters for different providers
PROVIDER_RATE_LIMITERS = {
    'anthropic': RateLimiter(
        requests_per_minute=50,  # Conservative limit
        requests_per_hour=1000
    ),
    'openai': RateLimiter(
        requests_per_minute=60,
        requests_per_hour=3000
    ),
    'ollama': RateLimiter(
        requests_per_minute=100,  # Local, higher limit
        requests_per_hour=None
    )
}


def get_rate_limiter(provider: str) -> RateLimiter:
    """Get rate limiter for provider.

    Args:
        provider: Provider name

    Returns:
        RateLimiter instance
    """
    if provider not in PROVIDER_RATE_LIMITERS:
        # Default conservative rate limiter
        return RateLimiter(requests_per_minute=60)

    return PROVIDER_RATE_LIMITERS[provider]
