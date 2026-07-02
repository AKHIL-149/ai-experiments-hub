"""
Rate Limiting Middleware for FastAPI

Applies rate limiting to incoming requests based on user role and endpoint.
"""

from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.core.rate_limiter import rate_limiter, RateLimitExceeded, RateLimitTier
from src.core.logging import logger
from src.models.user import UserRole


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware for rate limiting HTTP requests

    Features:
    - Role-based rate limits
    - Endpoint-specific limits
    - IP-based fallback
    - Rate limit headers in response
    """

    # Endpoints that require strict rate limiting
    STRICT_ENDPOINTS = {
        "/api/workflows/execute": RateLimitTier.WORKFLOW_EXECUTE,
        "/api/tasks": RateLimitTier.TASK_CREATE,
        "/api/agents": RateLimitTier.AGENT_CREATE,
    }

    # Endpoints to exclude from rate limiting
    EXEMPT_ENDPOINTS = {
        "/api/health",
        "/api/health/db",
        "/api/health/redis",
        "/api/health/celery",
        "/api/health/full",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with rate limiting

        Args:
            request: FastAPI request
            call_next: Next middleware or route handler

        Returns:
            Response: HTTP response
        """
        path = request.url.path

        # Skip rate limiting for exempt endpoints
        if path in self.EXEMPT_ENDPOINTS:
            return await call_next(request)

        # Get user from request state (set by auth middleware)
        user = getattr(request.state, "user", None)

        # Determine identifier and rate limit
        if user:
            identifier = f"user_{user.id}"
            rate_limit_config = self._get_rate_limit_for_role(user.role)
        else:
            # Use IP address for unauthenticated requests
            client_ip = self._get_client_ip(request)
            identifier = f"ip_{client_ip}"
            rate_limit_config = RateLimitTier.GLOBAL_IP_STRICT

        # Check for endpoint-specific limits
        endpoint_config = self._get_endpoint_limit(path, request.method)

        try:
            # Apply global rate limit
            is_allowed, remaining, reset_time = rate_limiter.check_rate_limit(
                identifier=identifier,
                max_requests=rate_limit_config["max_requests"],
                window_seconds=rate_limit_config["window_seconds"]
            )

            # Apply endpoint-specific rate limit if exists
            if endpoint_config:
                endpoint_identifier = f"{identifier}:{path}"
                is_allowed, remaining, reset_time = rate_limiter.check_rate_limit(
                    identifier=endpoint_identifier,
                    max_requests=endpoint_config["max_requests"],
                    window_seconds=endpoint_config["window_seconds"],
                    endpoint=path
                )

            # Process request
            response = await call_next(request)

            # Add rate limit headers
            self._add_rate_limit_headers(
                response,
                limit=rate_limit_config["max_requests"],
                remaining=remaining,
                reset=reset_time
            )

            return response

        except RateLimitExceeded as e:
            logger.warning(
                f"Rate limit exceeded for {identifier} on {path}: {e.message}"
            )

            # Return rate limit error response
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": e.message,
                    "retry_after": e.retry_after
                },
                headers={
                    "X-RateLimit-Limit": str(rate_limit_config["max_requests"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(e.retry_after)
                }
            )

    def _get_rate_limit_for_role(self, role: UserRole) -> dict:
        """
        Get rate limit configuration for user role

        Args:
            role: User role

        Returns:
            dict: Rate limit configuration
        """
        role_limits = {
            UserRole.VIEWER: RateLimitTier.VIEWER,
            UserRole.USER: RateLimitTier.USER,
            UserRole.ADMIN: RateLimitTier.ADMIN,
        }

        return role_limits.get(role, RateLimitTier.USER)

    def _get_endpoint_limit(self, path: str, method: str) -> dict:
        """
        Get endpoint-specific rate limit

        Args:
            path: Request path
            method: HTTP method

        Returns:
            dict: Rate limit configuration or None
        """
        # Check for POST requests to strict endpoints
        if method == "POST":
            for endpoint, config in self.STRICT_ENDPOINTS.items():
                if path.startswith(endpoint):
                    return config

        return None

    def _get_client_ip(self, request: Request) -> str:
        """
        Get client IP address from request

        Args:
            request: FastAPI request

        Returns:
            str: Client IP address
        """
        # Check for X-Forwarded-For header (proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take first IP in the list
            return forwarded_for.split(",")[0].strip()

        # Check for X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct client IP
        return request.client.host if request.client else "unknown"

    def _add_rate_limit_headers(
        self,
        response: Response,
        limit: int,
        remaining: int,
        reset: int
    ) -> None:
        """
        Add rate limit headers to response

        Args:
            response: HTTP response
            limit: Maximum requests allowed
            remaining: Remaining requests
            reset: Reset timestamp
        """
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)
