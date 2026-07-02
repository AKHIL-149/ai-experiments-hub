"""
Response Caching Middleware

Caches HTTP responses for improved performance.
"""

from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import hashlib
import json

from src.core.cache import cache_service
from src.core.logging import logger


class ResponseCachingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for caching HTTP responses

    Features:
    - GET request caching
    - Cache-Control header support
    - Configurable TTL per endpoint
    - Query parameter consideration
    """

    # Cache TTL per endpoint (in seconds)
    ENDPOINT_TTL = {
        "/api/tasks": 60,  # 1 minute
        "/api/agents": 120,  # 2 minutes
        "/api/agents/available": 30,  # 30 seconds
        "/api/metrics/summary": 300,  # 5 minutes
        "/api/workflows/workflows": 600,  # 10 minutes
        "/api/rate-limits/tiers": 3600,  # 1 hour
    }

    # Endpoints to never cache
    NOCACHE_ENDPOINTS = {
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/refresh",
        "/api/ws",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    # Endpoints with sensitive data
    PRIVATE_ENDPOINTS = {
        "/api/auth/me",
        "/api/rate-limits/me",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with response caching

        Args:
            request: FastAPI request
            call_next: Next middleware or route handler

        Returns:
            Response: HTTP response (cached or fresh)
        """
        # Only cache GET requests
        if request.method != "GET":
            return await call_next(request)

        path = request.url.path

        # Skip caching for excluded endpoints
        if any(path.startswith(endpoint) for endpoint in self.NOCACHE_ENDPOINTS):
            return await call_next(request)

        # Check if endpoint is cacheable
        cacheable = any(path.startswith(endpoint) for endpoint in self.ENDPOINT_TTL.keys())

        if not cacheable:
            response = await call_next(request)
            response.headers["X-Cache"] = "SKIP"
            return response

        # Build cache key
        cache_key = self._build_cache_key(request)
        namespace = "responses"

        # Check for private endpoints (user-specific caching)
        if any(path.startswith(endpoint) for endpoint in self.PRIVATE_ENDPOINTS):
            user = getattr(request.state, "user", None)
            if user:
                namespace = f"responses:user_{user.id}"

        # Try to get cached response
        cached_data = cache_service.get(cache_key, namespace)

        if cached_data:
            logger.debug(f"Response cache hit: {path}")

            # Return cached response
            return JSONResponse(
                content=cached_data["content"],
                status_code=cached_data["status_code"],
                headers={
                    **cached_data.get("headers", {}),
                    "X-Cache": "HIT",
                    "X-Cache-Key": cache_key[:16]  # First 16 chars for debugging
                }
            )

        # Execute request
        response = await call_next(request)

        # Only cache successful responses
        if response.status_code == 200:
            # Get TTL for this endpoint
            ttl = self._get_ttl_for_endpoint(path)

            # Read response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            try:
                # Parse JSON response
                content = json.loads(body.decode())

                # Cache the response
                cache_data = {
                    "content": content,
                    "status_code": response.status_code,
                    "headers": {
                        k: v for k, v in response.headers.items()
                        if k.lower() not in ["content-length", "transfer-encoding"]
                    }
                }

                cache_service.set(cache_key, cache_data, ttl, namespace)
                logger.debug(f"Response cached: {path} (TTL: {ttl}s)")

                # Return response with cache headers
                return JSONResponse(
                    content=content,
                    status_code=response.status_code,
                    headers={
                        **cache_data["headers"],
                        "X-Cache": "MISS",
                        "X-Cache-TTL": str(ttl)
                    }
                )

            except Exception as e:
                logger.error(f"Failed to cache response for {path}: {e}")

                # Return original response without caching
                return JSONResponse(
                    content=json.loads(body.decode()) if body else {},
                    status_code=response.status_code,
                    headers={**response.headers, "X-Cache": "ERROR"}
                )

        # Non-200 responses are not cached
        response.headers["X-Cache"] = "SKIP"
        return response

    def _build_cache_key(self, request: Request) -> str:
        """
        Build cache key from request

        Args:
            request: FastAPI request

        Returns:
            str: Cache key
        """
        # Include path and query parameters
        key_parts = [
            request.url.path,
            str(sorted(request.query_params.items()))
        ]

        # Create hash
        key_string = ":".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _get_ttl_for_endpoint(self, path: str) -> int:
        """
        Get TTL for endpoint

        Args:
            path: Request path

        Returns:
            int: TTL in seconds
        """
        for endpoint, ttl in self.ENDPOINT_TTL.items():
            if path.startswith(endpoint):
                return ttl

        # Default TTL
        return 60
