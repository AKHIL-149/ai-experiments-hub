"""
Request ID Middleware
Adds unique request ID to each request for tracking and correlation
"""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from typing import Callable
import contextvars

# Context variable to store request ID
request_id_context_var = contextvars.ContextVar('request_id', default=None)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track requests with unique IDs.

    Features:
    - Generates UUID for each request
    - Accepts existing X-Request-ID from client/load balancer
    - Adds X-Request-ID to response headers
    - Stores in context variable for logging
    - Available throughout request lifecycle
    """

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable):
        """Add request ID to request and response"""

        # Check if request already has an ID (from load balancer or client)
        request_id = request.headers.get('X-Request-ID') or request.headers.get('X-Correlation-ID')

        # Generate new ID if not provided
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in context variable for access throughout request
        request_id_context_var.set(request_id)

        # Add to request state for easy access
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers['X-Request-ID'] = request_id

        return response


def get_request_id() -> str:
    """
    Get the current request ID from context.

    Returns:
        Request ID string, or 'no-request-id' if not in request context

    Usage:
        from src.middleware.request_id import get_request_id

        def my_function():
            request_id = get_request_id()
            logger.info(f"Processing request {request_id}")
    """
    return request_id_context_var.get() or 'no-request-id'
