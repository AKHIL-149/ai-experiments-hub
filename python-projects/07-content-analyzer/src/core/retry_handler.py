"""Retry handler with exponential backoff for API calls."""
import time
import random
from typing import Callable, Any, Optional, Type, Tuple
from functools import wraps


class RetryHandler:
    """Handles retries with exponential backoff for API calls."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """Initialize retry handler.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            exponential_base: Base for exponential backoff calculation
            jitter: Add random jitter to delays to avoid thundering herd
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff: base_delay * (exponential_base ^ attempt)
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )

        # Add jitter to prevent thundering herd
        if self.jitter:
            # Random jitter between 0 and delay
            delay = delay * (0.5 + random.random() * 0.5)

        return delay

    def retry(
        self,
        func: Callable,
        *args,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        on_retry: Optional[Callable[[int, Exception], None]] = None,
        **kwargs
    ) -> Any:
        """Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments for function
            retryable_exceptions: Tuple of exception types to retry on
            on_retry: Optional callback called on each retry (attempt, exception)
            **kwargs: Keyword arguments for function

        Returns:
            Function return value

        Raises:
            Last exception if all retries fail
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)

            except retryable_exceptions as e:
                last_exception = e

                # Don't retry on last attempt
                if attempt >= self.max_retries:
                    break

                # Calculate delay
                delay = self._calculate_delay(attempt)

                # Call retry callback if provided
                if on_retry:
                    on_retry(attempt + 1, e)

                # Wait before retrying
                time.sleep(delay)

        # All retries exhausted, raise last exception
        raise last_exception

    def __call__(
        self,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        on_retry: Optional[Callable[[int, Exception], None]] = None
    ):
        """Decorator for retry logic.

        Args:
            retryable_exceptions: Tuple of exception types to retry on
            on_retry: Optional callback called on each retry

        Returns:
            Decorator function

        Example:
            @RetryHandler(max_retries=3)(
                retryable_exceptions=(ConnectionError, TimeoutError)
            )
            def make_api_call():
                ...
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                return self.retry(
                    func,
                    *args,
                    retryable_exceptions=retryable_exceptions,
                    on_retry=on_retry,
                    **kwargs
                )
            return wrapper
        return decorator


# Default retry handler instance
default_retry_handler = RetryHandler(
    max_retries=3,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    jitter=True
)


def retry_on_api_error(
    func: Optional[Callable] = None,
    max_retries: int = 3,
    on_retry: Optional[Callable[[int, Exception], None]] = None
):
    """Convenience decorator for API calls with retry logic.

    Args:
        func: Function to decorate
        max_retries: Maximum number of retries
        on_retry: Optional callback called on each retry

    Returns:
        Decorated function or decorator

    Example:
        @retry_on_api_error(max_retries=5)
        def make_api_call():
            ...
    """
    # Common API errors to retry
    retryable_exceptions = (
        ConnectionError,
        TimeoutError,
        # Add more as needed
    )

    def decorator(f: Callable) -> Callable:
        handler = RetryHandler(max_retries=max_retries)
        return handler(
            retryable_exceptions=retryable_exceptions,
            on_retry=on_retry
        )(f)

    # Support both @retry_on_api_error and @retry_on_api_error()
    if func is None:
        return decorator
    else:
        return decorator(func)
