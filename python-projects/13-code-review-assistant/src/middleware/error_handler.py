"""
Global Error Handler
Centralized error handling with structured error responses and logging
"""

import traceback
from typing import Union
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from pydantic import ValidationError


class ErrorResponse:
    """Standardized error response format"""

    @staticmethod
    def create(
        status_code: int,
        error_type: str,
        message: str,
        details: Union[dict, list, str, None] = None,
        correlation_id: str = None
    ) -> dict:
        """
        Create standardized error response

        Args:
            status_code: HTTP status code
            error_type: Error type/category
            message: Human-readable error message
            details: Additional error details
            correlation_id: Request correlation ID

        Returns:
            Error response dictionary
        """
        response = {
            'error': {
                'code': status_code,
                'type': error_type,
                'message': message
            }
        }

        if details:
            response['error']['details'] = details

        if correlation_id:
            response['correlation_id'] = correlation_id

        return response


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle HTTP exceptions

    Args:
        request: FastAPI request
        exc: HTTP exception

    Returns:
        JSON response
    """
    correlation_id = getattr(request.state, 'correlation_id', None)

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse.create(
            status_code=exc.status_code,
            error_type='http_error',
            message=exc.detail if isinstance(exc.detail, str) else 'HTTP error',
            details=exc.detail if not isinstance(exc.detail, str) else None,
            correlation_id=correlation_id
        )
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle request validation errors

    Args:
        request: FastAPI request
        exc: Validation exception

    Returns:
        JSON response
    """
    correlation_id = getattr(request.state, 'correlation_id', None)

    # Format validation errors
    errors = []
    for error in exc.errors():
        errors.append({
            'field': '.'.join(str(x) for x in error['loc']),
            'message': error['msg'],
            'type': error['type']
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse.create(
            status_code=422,
            error_type='validation_error',
            message='Request validation failed',
            details=errors,
            correlation_id=correlation_id
        )
    )


async def database_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle database exceptions

    Args:
        request: FastAPI request
        exc: Database exception

    Returns:
        JSON response
    """
    correlation_id = getattr(request.state, 'correlation_id', None)

    if isinstance(exc, IntegrityError):
        # Duplicate key or constraint violation
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse.create(
                status_code=409,
                error_type='database_integrity_error',
                message='Database constraint violation',
                details=str(exc.orig) if hasattr(exc, 'orig') else str(exc),
                correlation_id=correlation_id
            )
        )
    elif isinstance(exc, OperationalError):
        # Database connection or operational error
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse.create(
                status_code=503,
                error_type='database_unavailable',
                message='Database service temporarily unavailable',
                correlation_id=correlation_id
            )
        )
    else:
        # Generic database error
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse.create(
                status_code=500,
                error_type='database_error',
                message='Database operation failed',
                correlation_id=correlation_id
            )
        )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle all other exceptions

    Args:
        request: FastAPI request
        exc: Any exception

    Returns:
        JSON response
    """
    correlation_id = getattr(request.state, 'correlation_id', None)

    # Log full traceback for debugging
    print(f"Unhandled exception (correlation_id: {correlation_id}):")
    traceback.print_exc()

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse.create(
            status_code=500,
            error_type='internal_server_error',
            message='An unexpected error occurred',
            details={'type': type(exc).__name__} if hasattr(exc, '__name__') else None,
            correlation_id=correlation_id
        )
    )


def register_exception_handlers(app):
    """
    Register all exception handlers with FastAPI app

    Args:
        app: FastAPI application instance
    """
    # HTTP exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # Validation errors
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)

    # Database errors
    app.add_exception_handler(IntegrityError, database_exception_handler)
    app.add_exception_handler(OperationalError, database_exception_handler)

    # Catch-all for unhandled exceptions
    app.add_exception_handler(Exception, generic_exception_handler)


# Retry decorator for transient failures
def retry_on_transient_error(max_retries: int = 3, delay: float = 1.0):
    """
    Decorator to retry operations on transient errors

    Args:
        max_retries: Maximum number of retry attempts
        delay: Delay between retries in seconds

    Returns:
        Decorated function
    """
    import time
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (OperationalError, ConnectionError, TimeoutError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        print(f"Transient error on attempt {attempt + 1}/{max_retries}: {e}")
                        time.sleep(delay * (attempt + 1))  # Exponential backoff
                    else:
                        print(f"Max retries ({max_retries}) exceeded")

            # If all retries failed, raise the last exception
            raise last_exception

        return wrapper
    return decorator
