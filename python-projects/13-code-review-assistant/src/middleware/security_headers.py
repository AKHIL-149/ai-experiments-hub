"""
Security Headers Middleware
Adds security headers to all HTTP responses
"""

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from typing import Callable
import os


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses

    Headers added:
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-Frame-Options: Prevents clickjacking
    - X-XSS-Protection: XSS filter (legacy browsers)
    - Strict-Transport-Security: Force HTTPS
    - Content-Security-Policy: CSP policy
    - Referrer-Policy: Control referrer information
    - Permissions-Policy: Feature policy
    """

    def __init__(self, app, config: dict = None):
        super().__init__(app)
        self.config = config or self._default_config()

    def _default_config(self) -> dict:
        """Get default security headers configuration"""
        # Check if in production
        is_production = os.getenv('ENVIRONMENT', 'development') == 'production'
        cookie_secure = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'

        return {
            # Prevent MIME type sniffing
            'X-Content-Type-Options': 'nosniff',

            # Prevent clickjacking
            'X-Frame-Options': 'DENY',

            # XSS Protection (legacy, but still useful for older browsers)
            'X-XSS-Protection': '1; mode=block',

            # Strict Transport Security (HSTS) - only in production with HTTPS
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains' if (is_production and cookie_secure) else None,

            # Content Security Policy
            'Content-Security-Policy': self._get_csp_policy(),

            # Referrer Policy
            'Referrer-Policy': 'strict-origin-when-cross-origin',

            # Permissions Policy (formerly Feature Policy)
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',

            # Additional headers
            'X-Permitted-Cross-Domain-Policies': 'none',
        }

    def _get_csp_policy(self) -> str:
        """
        Get Content Security Policy

        Restrictive by default, can be customized via environment
        """
        # Default CSP - adjust based on your needs
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Allow inline scripts for now
            "style-src 'self' 'unsafe-inline'",  # Allow inline styles
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]

        # Allow WebSocket connections
        if os.getenv('ENABLE_WEBSOCKETS', 'false').lower() == 'true':
            csp_directives.append("connect-src 'self' ws: wss:")

        return "; ".join(csp_directives)

    async def dispatch(self, request: Request, call_next: Callable):
        """Add security headers to response"""
        response = await call_next(request)

        # Add security headers
        for header, value in self.config.items():
            if value is not None:  # Skip None values
                response.headers[header] = value

        # Add custom header to identify our application
        response.headers['X-Powered-By'] = 'AI Code Review Assistant'

        # Remove server header for security (if present)
        if 'Server' in response.headers:
            del response.headers['Server']

        return response


class CSPReportMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle CSP violation reports

    Logs CSP violations for monitoring and debugging
    """

    async def dispatch(self, request: Request, call_next: Callable):
        """Handle CSP reports"""
        if request.url.path == '/api/csp-report' and request.method == 'POST':
            # Log CSP violation
            try:
                body = await request.json()
                # In production, send to logging/monitoring service
                print(f"CSP Violation: {body}")
            except Exception as e:
                print(f"Error processing CSP report: {e}")

            # Return 204 No Content
            from fastapi.responses import Response
            return Response(status_code=204)

        return await call_next(request)


def get_security_headers_config() -> dict:
    """
    Get security headers configuration from environment

    Allows customization via environment variables
    """
    config = {}

    # X-Frame-Options
    frame_options = os.getenv('X_FRAME_OPTIONS', 'DENY')
    if frame_options:
        config['X-Frame-Options'] = frame_options

    # CSP
    csp = os.getenv('CONTENT_SECURITY_POLICY')
    if csp:
        config['Content-Security-Policy'] = csp

    # HSTS
    hsts = os.getenv('STRICT_TRANSPORT_SECURITY')
    if hsts:
        config['Strict-Transport-Security'] = hsts

    return config


# CORS Security Best Practices
def validate_cors_origin(origin: str, allowed_origins: list) -> bool:
    """
    Validate CORS origin against whitelist

    Args:
        origin: Origin header value
        allowed_origins: List of allowed origins

    Returns:
        True if origin is allowed
    """
    if not origin:
        return False

    # Exact match
    if origin in allowed_origins:
        return True

    # Wildcard support (e.g., https://*.example.com)
    for allowed in allowed_origins:
        if '*' in allowed:
            pattern = allowed.replace('*', '.*')
            import re
            if re.match(pattern, origin):
                return True

    return False


# Security utilities
def sanitize_redirect_url(url: str, allowed_domains: list = None) -> str:
    """
    Sanitize redirect URL to prevent open redirect vulnerabilities

    Args:
        url: URL to sanitize
        allowed_domains: List of allowed domains for redirect

    Returns:
        Sanitized URL or None if invalid
    """
    from urllib.parse import urlparse

    if not url:
        return None

    # Parse URL
    parsed = urlparse(url)

    # Only allow relative URLs or whitelisted domains
    if not parsed.netloc:
        # Relative URL - safe
        return url

    # Check if domain is whitelisted
    if allowed_domains and parsed.netloc in allowed_domains:
        return url

    # Block external redirects by default
    return None


def generate_nonce() -> str:
    """
    Generate cryptographic nonce for CSP

    Returns:
        Base64-encoded nonce
    """
    import secrets
    import base64

    # Generate 16 bytes of random data
    nonce_bytes = secrets.token_bytes(16)

    # Encode as base64
    nonce = base64.b64encode(nonce_bytes).decode('utf-8')

    return nonce


def add_csp_nonce_to_response(response, nonce: str):
    """
    Add CSP nonce to response header

    Updates Content-Security-Policy header to include nonce
    """
    if 'Content-Security-Policy' in response.headers:
        csp = response.headers['Content-Security-Policy']

        # Add nonce to script-src and style-src
        if "script-src" in csp:
            csp = csp.replace("script-src", f"script-src 'nonce-{nonce}'")

        response.headers['Content-Security-Policy'] = csp

    return response
