"""
Custom middleware for FastAPI application
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import settings

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging all HTTP requests and responses"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Log request and response details

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response
        """
        # Start timer
        start_time = time.time()

        # Log request
        logger.info(f"➡️  {request.method} {request.url.path}")
        if request.query_params:
            logger.debug(f"Query params: {dict(request.query_params)}")

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log response
        logger.info(
            f"⬅️  {request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Duration: {duration:.3f}s"
        )

        # Add custom headers
        response.headers["X-Process-Time"] = str(duration)

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware"""

    def __init__(self, app, max_requests: int = None, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests or settings.rate_limit_per_minute
        self.window_seconds = window_seconds
        self.request_counts: Dict[str, list] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Apply rate limiting per client IP

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response or 429 Too Many Requests
        """
        # Skip rate limiting for health check endpoints
        if request.url.path in ["/", "/health", "/version"]:
            return await call_next(request)

        # Get client IP
        client_ip = request.client.host

        # Get current time
        now = datetime.now()

        # Clean old requests
        cutoff_time = now - timedelta(seconds=self.window_seconds)
        self.request_counts[client_ip] = [
            req_time for req_time in self.request_counts[client_ip]
            if req_time > cutoff_time
        ]

        # Check rate limit
        if len(self.request_counts[client_ip]) >= self.max_requests:
            logger.warning(
                f"Rate limit exceeded for {client_ip} - "
                f"{len(self.request_counts[client_ip])} requests in {self.window_seconds}s"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate Limit Exceeded",
                    "message": f"Too many requests. Please try again in {self.window_seconds} seconds.",
                    "retry_after": self.window_seconds,
                }
            )

        # Record this request
        self.request_counts[client_ip].append(now)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        remaining = self.max_requests - len(self.request_counts[client_ip])
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(self.window_seconds)

        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for catching and formatting errors"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Catch and format errors

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response
        """
        try:
            response = await call_next(request)
            return response

        except ValueError as e:
            logger.error(f"ValueError: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "Bad Request",
                    "message": str(e),
                }
            )

        except PermissionError as e:
            logger.error(f"PermissionError: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "Forbidden",
                    "message": str(e),
                }
            )

        except FileNotFoundError as e:
            logger.error(f"FileNotFoundError: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "error": "Not Found",
                    "message": str(e),
                }
            )

        except Exception as e:
            logger.exception(f"Unhandled exception: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal Server Error",
                    "message": "An unexpected error occurred. Please try again later.",
                    "detail": str(e) if settings.debug else None,
                }
            )
