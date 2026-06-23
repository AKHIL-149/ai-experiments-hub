"""
Logging Middleware
Structured request/response logging with correlation IDs and sensitive data masking
"""

import time
import json
import uuid
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message
import re


# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'  # We'll use JSON format
)

logger = logging.getLogger(__name__)


class StructuredLogger:
    """Structured JSON logger"""

    SENSITIVE_FIELDS = {
        'password', 'token', 'secret', 'api_key', 'apikey',
        'authorization', 'cookie', 'session', 'github_token'
    }

    SENSITIVE_PATTERNS = [
        (re.compile(r'Bearer\s+[\w-]+\.[\w-]+\.[\w-]+'), 'Bearer [REDACTED]'),  # JWT
        (re.compile(r'ghp_[a-zA-Z0-9]{36}'), 'ghp_[REDACTED]'),  # GitHub token
        (re.compile(r'gho_[a-zA-Z0-9]{36}'), 'gho_[REDACTED]'),  # GitHub OAuth
        (re.compile(r'"password"\s*:\s*"[^"]*"'), '"password":"[REDACTED]"'),  # Password in JSON
        (re.compile(r'"token"\s*:\s*"[^"]*"'), '"token":"[REDACTED]"'),  # Token in JSON
    ]

    @staticmethod
    def mask_sensitive_data(data: any) -> any:
        """Mask sensitive data in logs"""
        if isinstance(data, dict):
            return {
                key: '[REDACTED]' if key.lower() in StructuredLogger.SENSITIVE_FIELDS else StructuredLogger.mask_sensitive_data(value)
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return [StructuredLogger.mask_sensitive_data(item) for item in data]
        elif isinstance(data, str):
            # Apply regex patterns
            result = data
            for pattern, replacement in StructuredLogger.SENSITIVE_PATTERNS:
                result = pattern.sub(replacement, result)
            return result
        else:
            return data

    @staticmethod
    def log(level: str, message: str, **kwargs):
        """Log structured message"""
        log_entry = {
            'timestamp': time.time(),
            'level': level,
            'message': message,
            **StructuredLogger.mask_sensitive_data(kwargs)
        }

        log_message = json.dumps(log_entry)

        if level == 'DEBUG':
            logger.debug(log_message)
        elif level == 'INFO':
            logger.info(log_message)
        elif level == 'WARNING':
            logger.warning(log_message)
        elif level == 'ERROR':
            logger.error(log_message)
        elif level == 'CRITICAL':
            logger.critical(log_message)

    @staticmethod
    def info(message: str, **kwargs):
        """Log info message"""
        StructuredLogger.log('INFO', message, **kwargs)

    @staticmethod
    def warning(message: str, **kwargs):
        """Log warning message"""
        StructuredLogger.log('WARNING', message, **kwargs)

    @staticmethod
    def error(message: str, **kwargs):
        """Log error message"""
        StructuredLogger.log('ERROR', message, **kwargs)

    @staticmethod
    def debug(message: str, **kwargs):
        """Log debug message"""
        StructuredLogger.log('DEBUG', message, **kwargs)


class LoggingMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for request/response logging"""

    def __init__(self, app):
        super().__init__(app)
        self.logger = StructuredLogger()

    async def dispatch(self, request: Request, call_next):
        """Log request and response"""
        # Generate correlation ID
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        # Get client info
        client_ip = request.client.host if request.client else 'unknown'
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            client_ip = forwarded_for.split(',')[0].strip()

        # Get user info if authenticated
        user_id = None
        if hasattr(request.state, 'user') and request.state.user:
            user_id = request.state.user.id

        # Start timer
        start_time = time.time()

        # Log request
        self.logger.info(
            'Incoming request',
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
            client_ip=client_ip,
            user_agent=request.headers.get('User-Agent', 'unknown'),
            user_id=user_id
        )

        # Process request and catch exceptions
        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Log response
            self.logger.info(
                'Request completed',
                correlation_id=correlation_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
                user_id=user_id
            )

            # Add correlation ID to response headers
            response.headers['X-Correlation-ID'] = correlation_id

            return response

        except Exception as e:
            duration = time.time() - start_time

            # Log error
            self.logger.error(
                'Request failed',
                correlation_id=correlation_id,
                method=request.method,
                path=request.url.path,
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=round(duration * 1000, 2),
                user_id=user_id
            )

            # Re-raise exception to be handled by error handler
            raise


# Global structured logger instance
structured_logger = StructuredLogger()
