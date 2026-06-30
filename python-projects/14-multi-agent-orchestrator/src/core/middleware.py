"""
FastAPI middleware for logging and monitoring
"""

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.logging import log_api_request
from src.core.metrics import metrics_collector


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging all HTTP requests
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Start timer
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Extract request info
        method = request.method
        path = request.url.path
        status_code = response.status_code
        user_agent = request.headers.get('user-agent', 'unknown')

        # Log request
        log_api_request(
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=duration_ms,
            user_agent=user_agent
        )

        # Record metrics
        metrics_collector.record_http_request(
            method=method,
            endpoint=path,
            status_code=status_code,
            duration=duration_ms / 1000  # Convert to seconds
        )

        # Add response headers
        response.headers['X-Response-Time'] = f"{duration_ms:.2f}ms"

        return response


class ErrorTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for tracking and logging errors
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)

            # Track errors (4xx and 5xx)
            if response.status_code >= 400:
                error_type = "client_error" if response.status_code < 500 else "server_error"
                metrics_collector.record_error(
                    error_type=error_type,
                    component="api"
                )

            return response

        except Exception as e:
            # Log unhandled exceptions
            metrics_collector.record_error(
                error_type=type(e).__name__,
                component="api"
            )
            raise
