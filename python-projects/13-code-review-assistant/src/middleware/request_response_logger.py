"""
Request/Response Logging Middleware
Comprehensive logging of HTTP requests and responses for debugging and monitoring
"""

import time
import json
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from typing import Callable
import logging

from src.middleware.request_id import get_request_id

# Configure logger
logger = logging.getLogger(__name__)


class RequestResponseLoggerMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log detailed information about HTTP requests and responses.

    Features:
    - Request method, path, headers, query parameters
    - Response status code, headers
    - Request/response timing
    - Request body logging (for debugging, optional)
    - Integration with request ID tracking
    - Configurable log level
    - Excludes sensitive headers (Authorization, Cookie)

    Configuration:
    - Set ENABLE_REQUEST_LOGGING=true in .env to enable
    - Set LOG_REQUEST_BODY=true to log request bodies (caution: may log sensitive data)
    - Set LOG_RESPONSE_BODY=true to log response bodies
    """

    def __init__(
        self,
        app,
        log_request_body: bool = False,
        log_response_body: bool = False,
        excluded_paths: list = None
    ):
        super().__init__(app)
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.excluded_paths = excluded_paths or [
            '/health',
            '/metrics',
            '/favicon.ico',
            '/static'
        ]

        # Headers to exclude from logs (sensitive information)
        self.sensitive_headers = {
            'authorization',
            'cookie',
            'x-api-key',
            'x-auth-token',
            'proxy-authorization'
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response details"""

        # Skip logging for excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)

        # Get request ID for correlation
        request_id = get_request_id()

        # Record request start time
        start_time = time.time()

        # Log request details
        await self._log_request(request, request_id)

        # Process request and capture response
        response = await call_next(request)

        # Calculate request duration
        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Log response details
        self._log_response(request, response, duration_ms, request_id)

        # Add timing header to response
        response.headers['X-Response-Time'] = f"{duration_ms}ms"

        return response

    async def _log_request(self, request: Request, request_id: str):
        """Log incoming request details"""

        # Build request log data
        log_data = {
            'type': 'request',
            'request_id': request_id,
            'method': request.method,
            'path': request.url.path,
            'query_params': dict(request.query_params) if request.query_params else {},
            'client_host': request.client.host if request.client else 'unknown',
            'user_agent': request.headers.get('user-agent', 'unknown')
        }

        # Add non-sensitive headers
        headers = {}
        for key, value in request.headers.items():
            if key.lower() not in self.sensitive_headers:
                headers[key] = value
            else:
                headers[key] = '[REDACTED]'
        log_data['headers'] = headers

        # Log request body if enabled (be careful with sensitive data)
        if self.log_request_body and request.method in ['POST', 'PUT', 'PATCH']:
            try:
                body = await request.body()
                if body:
                    # Try to parse as JSON
                    try:
                        log_data['body'] = json.loads(body.decode('utf-8'))
                    except:
                        log_data['body'] = body.decode('utf-8', errors='replace')[:500]  # Limit size
            except Exception as e:
                log_data['body_error'] = str(e)

        # Log as INFO level
        logger.info(
            f"{request.method} {request.url.path}",
            extra={'log_data': log_data}
        )

    def _log_response(
        self,
        request: Request,
        response: Response,
        duration_ms: float,
        request_id: str
    ):
        """Log outgoing response details"""

        # Build response log data
        log_data = {
            'type': 'response',
            'request_id': request_id,
            'method': request.method,
            'path': request.url.path,
            'status_code': response.status_code,
            'duration_ms': duration_ms
        }

        # Add response headers (non-sensitive)
        headers = {}
        for key, value in response.headers.items():
            if key.lower() not in self.sensitive_headers:
                headers[key] = value
        log_data['headers'] = headers

        # Determine log level based on status code
        if response.status_code >= 500:
            log_level = logging.ERROR
            log_message = f"ERROR: {request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)"
        elif response.status_code >= 400:
            log_level = logging.WARNING
            log_message = f"WARNING: {request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)"
        else:
            log_level = logging.INFO
            log_message = f"SUCCESS: {request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)"

        # Log with appropriate level
        logger.log(
            log_level,
            log_message,
            extra={'log_data': log_data}
        )
