"""
Global error handling utilities
"""

import sys
import traceback
from typing import Dict, Any, Optional
from functools import wraps

from src.core.logging import logger
from src.core.metrics import metrics_collector
from src.core.exceptions import (
    MultiAgentOrchestratorException,
    TaskException,
    AgentException,
    LLMException,
    DatabaseException,
    ValidationException
)


class ErrorHandler:
    """
    Centralized error handling
    """

    @staticmethod
    def handle_exception(
        exception: Exception,
        context: Dict[str, Any] = None,
        reraise: bool = True
    ) -> Dict[str, Any]:
        """
        Handle exception with logging and metrics

        Args:
            exception: The exception to handle
            context: Additional context information
            reraise: Whether to reraise the exception

        Returns:
            dict: Error information

        Raises:
            Exception: If reraise is True
        """
        # Determine error type
        error_type = type(exception).__name__
        error_message = str(exception)

        # Determine component
        component = "unknown"
        if isinstance(exception, TaskException):
            component = "task"
        elif isinstance(exception, AgentException):
            component = "agent"
        elif isinstance(exception, LLMException):
            component = "llm"
        elif isinstance(exception, DatabaseException):
            component = "database"
        elif isinstance(exception, ValidationException):
            component = "validation"

        # Build error info
        error_info = {
            'error_type': error_type,
            'error_message': error_message,
            'component': component,
        }

        if context:
            error_info['context'] = context

        # Get traceback
        tb = traceback.format_exc()
        error_info['traceback'] = tb

        # Log error
        logger.error(
            f"{component.upper()} ERROR: {error_message}",
            extra=error_info,
            exc_info=True
        )

        # Record metric
        metrics_collector.record_error(error_type, component)

        # Reraise if requested
        if reraise:
            raise

        return error_info

    @staticmethod
    def safe_execute(func, *args, default=None, **kwargs):
        """
        Execute function with error handling

        Args:
            func: Function to execute
            args: Positional arguments
            default: Default value to return on error
            kwargs: Keyword arguments

        Returns:
            Any: Function result or default value
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            ErrorHandler.handle_exception(
                e,
                context={
                    'function': func.__name__,
                    'args': str(args),
                    'kwargs': str(kwargs)
                },
                reraise=False
            )
            return default


def handle_errors(
    error_types: tuple = (Exception,),
    default_return: Any = None,
    log_errors: bool = True
):
    """
    Decorator for handling errors in functions

    Args:
        error_types: Tuple of exception types to catch
        default_return: Default return value on error
        log_errors: Whether to log errors

    Returns:
        decorator: Error handling decorator
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except error_types as e:
                if log_errors:
                    ErrorHandler.handle_exception(
                        e,
                        context={
                            'function': func.__name__,
                            'module': func.__module__
                        },
                        reraise=False
                    )
                return default_return
        return wrapper
    return decorator


def handle_async_errors(
    error_types: tuple = (Exception,),
    default_return: Any = None,
    log_errors: bool = True
):
    """
    Decorator for handling errors in async functions

    Args:
        error_types: Tuple of exception types to catch
        default_return: Default return value on error
        log_errors: Whether to log errors

    Returns:
        decorator: Error handling decorator
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except error_types as e:
                if log_errors:
                    ErrorHandler.handle_exception(
                        e,
                        context={
                            'function': func.__name__,
                            'module': func.__module__
                        },
                        reraise=False
                    )
                return default_return
        return wrapper
    return decorator


def format_error_response(
    exception: Exception,
    include_traceback: bool = False
) -> Dict[str, Any]:
    """
    Format exception as API error response

    Args:
        exception: Exception to format
        include_traceback: Whether to include traceback

    Returns:
        dict: Formatted error response
    """
    response = {
        'success': False,
        'error': {
            'type': type(exception).__name__,
            'message': str(exception)
        }
    }

    # Add specific error attributes
    if isinstance(exception, MultiAgentOrchestratorException):
        if hasattr(exception, 'task_id'):
            response['error']['task_id'] = exception.task_id
        if hasattr(exception, 'agent_id'):
            response['error']['agent_id'] = exception.agent_id
        if hasattr(exception, 'field'):
            response['error']['field'] = exception.field

    # Add traceback if requested
    if include_traceback:
        response['error']['traceback'] = traceback.format_exc()

    return response


# Singleton instance
error_handler = ErrorHandler()
