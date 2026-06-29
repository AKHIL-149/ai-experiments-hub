"""
Logging Service
Provides structured logging with correlation IDs, sensitive data masking, and error tracking
"""

import logging
import sys
import json
import re
import uuid
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from contextlib import contextmanager


class LogLevel(str, Enum):
    """Log levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    Outputs logs in JSON format for easy parsing by log aggregation systems.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': self.formatException(record.exc_info) if record.exc_info else None
            }

        # Try to get request ID from context if not already set
        if not hasattr(record, 'request_id'):
            try:
                from src.middleware.request_id import get_request_id
                request_id = get_request_id()
                if request_id and request_id != 'no-request-id':
                    log_data['request_id'] = request_id
            except (ImportError, Exception):
                pass  # Ignore if middleware not available

        # Add extra fields if present
        if hasattr(record, 'correlation_id'):
            log_data['correlation_id'] = record.correlation_id

        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id

        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id

        if hasattr(record, 'metadata'):
            log_data['metadata'] = record.metadata

        return json.dumps(log_data)


class LoggingService:
    """
    Centralized logging service with structured logging, correlation IDs,
    and sensitive data masking
    """

    def __init__(self, service_name: str = "code-review-assistant"):
        self.service_name = service_name
        self.logs: List[Dict] = []
        self.max_logs = 10000  # Maximum logs to keep in memory
        self.correlation_id: Optional[str] = None

        # Patterns for sensitive data masking
        self.sensitive_patterns = {
            'api_key': re.compile(r'(api[_-]?key|apikey)["\s:=]+([a-zA-Z0-9_\-]+)', re.IGNORECASE),
            'token': re.compile(r'(token|bearer)["\s:=]+([a-zA-Z0-9_\-\.]+)', re.IGNORECASE),
            'password': re.compile(r'(password|passwd|pwd)["\s:=]+([^\s,}]+)', re.IGNORECASE),
            'secret': re.compile(r'(secret|auth)["\s:=]+([a-zA-Z0-9_\-]+)', re.IGNORECASE),
            'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            'credit_card': re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'),
            'ssn': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        }

        # Initialize Python logger
        self.logger = self._setup_logger()

        # Error tracking
        self.error_count = 0
        self.errors: List[Dict] = []
        self.max_errors = 1000

    def _setup_logger(self) -> logging.Logger:
        """Set up Python logger with custom formatting"""
        import os

        logger = logging.getLogger(self.service_name)
        logger.setLevel(logging.DEBUG)

        # Remove existing handlers
        logger.handlers.clear()

        # Console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)

        # Use JSON formatter in production, human-readable in development
        use_json_logs = os.getenv('LOG_FORMAT', 'text').lower() == 'json' or \
                        os.getenv('ENVIRONMENT', 'development') == 'production'

        if use_json_logs:
            # JSON formatter for production log aggregation
            formatter = JSONFormatter()
        else:
            # Human-readable formatter for development
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    # ============================================================================
    # Correlation ID Management
    # ============================================================================

    def generate_correlation_id(self) -> str:
        """Generate a new correlation ID"""
        return str(uuid.uuid4())

    def set_correlation_id(self, correlation_id: str) -> None:
        """Set the current correlation ID"""
        self.correlation_id = correlation_id

    def get_correlation_id(self) -> Optional[str]:
        """Get the current correlation ID"""
        return self.correlation_id

    @contextmanager
    def correlation_context(self, correlation_id: Optional[str] = None):
        """
        Context manager for correlation ID

        Usage:
            with logging_service.correlation_context():
                logging_service.info("Request started")
        """
        old_correlation_id = self.correlation_id
        self.correlation_id = correlation_id or self.generate_correlation_id()

        try:
            yield self.correlation_id
        finally:
            self.correlation_id = old_correlation_id

    # ============================================================================
    # Sensitive Data Masking
    # ============================================================================

    def mask_sensitive_data(self, text: str) -> str:
        """
        Mask sensitive data in text

        Args:
            text: Input text that may contain sensitive data

        Returns:
            Text with sensitive data masked
        """
        if not isinstance(text, str):
            text = str(text)

        masked_text = text

        for pattern_name, pattern in self.sensitive_patterns.items():
            if pattern_name in ['api_key', 'token', 'password', 'secret']:
                # Mask the value part of key=value patterns
                masked_text = pattern.sub(r'\1="***MASKED***"', masked_text)
            elif pattern_name == 'email':
                # Mask email addresses (keep first char + domain)
                def mask_email(match):
                    email = match.group(0)
                    parts = email.split('@')
                    if len(parts) == 2:
                        return f"{parts[0][0]}***@{parts[1]}"
                    return "***@***"
                masked_text = pattern.sub(mask_email, masked_text)
            else:
                # Mask credit cards, SSNs completely
                masked_text = pattern.sub('***MASKED***', masked_text)

        return masked_text

    def mask_dict_sensitive_data(self, data: Dict) -> Dict:
        """
        Recursively mask sensitive data in dictionaries

        Args:
            data: Dictionary that may contain sensitive data

        Returns:
            Dictionary with sensitive data masked
        """
        if not isinstance(data, dict):
            return data

        masked = {}
        sensitive_keys = {'password', 'token', 'api_key', 'secret', 'apikey', 'auth', 'credential'}

        for key, value in data.items():
            if isinstance(value, dict):
                masked[key] = self.mask_dict_sensitive_data(value)
            elif isinstance(value, list):
                masked[key] = [
                    self.mask_dict_sensitive_data(item) if isinstance(item, dict) else
                    self.mask_sensitive_data(str(item)) if isinstance(item, str) else item
                    for item in value
                ]
            elif isinstance(value, str):
                # Check if key is sensitive
                if any(sensitive in key.lower() for sensitive in sensitive_keys):
                    masked[key] = "***MASKED***"
                else:
                    masked[key] = self.mask_sensitive_data(value)
            else:
                masked[key] = value

        return masked

    # ============================================================================
    # Logging Methods
    # ============================================================================

    def log(
        self,
        level: LogLevel,
        message: str,
        metadata: Optional[Dict] = None,
        mask_sensitive: bool = True,
        exception: Optional[Exception] = None
    ) -> Dict:
        """
        Core logging method

        Args:
            level: Log level
            message: Log message
            metadata: Additional metadata
            mask_sensitive: Whether to mask sensitive data
            exception: Exception object if logging an error

        Returns:
            Log entry dictionary
        """
        # Mask sensitive data if enabled
        if mask_sensitive:
            message = self.mask_sensitive_data(message)
            if metadata:
                metadata = self.mask_dict_sensitive_data(metadata)

        # Create log entry
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'service': self.service_name,
            'level': level.value,
            'message': message,
            'correlation_id': self.correlation_id,
            'metadata': metadata or {}
        }

        # Add exception info if present
        if exception:
            log_entry['exception'] = {
                'type': type(exception).__name__,
                'message': str(exception),
                'traceback': traceback.format_exc()
            }

        # Store in memory
        self.logs.append(log_entry)

        # Trim logs if exceeded max
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]

        # Track errors
        if level in [LogLevel.ERROR, LogLevel.CRITICAL]:
            self.error_count += 1
            self.errors.append(log_entry)

            # Trim errors if exceeded max
            if len(self.errors) > self.max_errors:
                self.errors = self.errors[-self.max_errors:]

        # Log to Python logger with extra fields for JSON formatter
        python_level = getattr(logging, level.value)
        log_message = self._format_log_message(log_entry)

        # Pass extra fields to logger for JSON formatter
        extra = {}
        if self.correlation_id:
            extra['correlation_id'] = self.correlation_id
        if metadata:
            extra['metadata'] = metadata

        self.logger.log(python_level, log_message, extra=extra if extra else None)

        return log_entry

    def _format_log_message(self, log_entry: Dict) -> str:
        """Format log entry for Python logger"""
        parts = [log_entry['message']]

        if log_entry.get('correlation_id'):
            parts.append(f"[correlation_id={log_entry['correlation_id']}]")

        if log_entry.get('metadata'):
            parts.append(f"[metadata={json.dumps(log_entry['metadata'])}]")

        return " ".join(parts)

    def debug(self, message: str, metadata: Optional[Dict] = None, **kwargs) -> Dict:
        """Log debug message"""
        return self.log(LogLevel.DEBUG, message, metadata, **kwargs)

    def info(self, message: str, metadata: Optional[Dict] = None, **kwargs) -> Dict:
        """Log info message"""
        return self.log(LogLevel.INFO, message, metadata, **kwargs)

    def warning(self, message: str, metadata: Optional[Dict] = None, **kwargs) -> Dict:
        """Log warning message"""
        return self.log(LogLevel.WARNING, message, metadata, **kwargs)

    def error(
        self,
        message: str,
        metadata: Optional[Dict] = None,
        exception: Optional[Exception] = None,
        **kwargs
    ) -> Dict:
        """Log error message"""
        return self.log(LogLevel.ERROR, message, metadata, exception=exception, **kwargs)

    def critical(
        self,
        message: str,
        metadata: Optional[Dict] = None,
        exception: Optional[Exception] = None,
        **kwargs
    ) -> Dict:
        """Log critical message"""
        return self.log(LogLevel.CRITICAL, message, metadata, exception=exception, **kwargs)

    # ============================================================================
    # Log Retrieval
    # ============================================================================

    def get_logs(
        self,
        level: Optional[LogLevel] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Get logs with filtering

        Args:
            level: Filter by log level
            correlation_id: Filter by correlation ID
            limit: Maximum number of logs to return
            offset: Number of logs to skip

        Returns:
            List of log entries
        """
        filtered_logs = self.logs

        # Filter by level
        if level:
            filtered_logs = [log for log in filtered_logs if log['level'] == level.value]

        # Filter by correlation ID
        if correlation_id:
            filtered_logs = [
                log for log in filtered_logs
                if log.get('correlation_id') == correlation_id
            ]

        # Apply pagination
        return filtered_logs[offset:offset + limit]

    def get_errors(self, limit: int = 100) -> List[Dict]:
        """Get recent errors"""
        return self.errors[-limit:]

    def get_statistics(self) -> Dict:
        """Get logging statistics"""
        level_counts = {
            'DEBUG': 0,
            'INFO': 0,
            'WARNING': 0,
            'ERROR': 0,
            'CRITICAL': 0
        }

        for log in self.logs:
            level = log['level']
            if level in level_counts:
                level_counts[level] += 1

        return {
            'total_logs': len(self.logs),
            'total_errors': self.error_count,
            'level_counts': level_counts,
            'recent_errors': len(self.errors)
        }

    def clear_logs(self) -> int:
        """Clear all logs and return count of cleared logs"""
        count = len(self.logs)
        self.logs.clear()
        return count

    def clear_errors(self) -> int:
        """Clear error log and return count of cleared errors"""
        count = len(self.errors)
        self.errors.clear()
        self.error_count = 0
        return count

    # ============================================================================
    # Export/Import
    # ============================================================================

    def export_logs(self, format: str = 'json') -> str:
        """
        Export logs to JSON or other formats

        Args:
            format: Export format ('json' or 'csv')

        Returns:
            Serialized logs
        """
        if format == 'json':
            return json.dumps({
                'service': self.service_name,
                'exported_at': datetime.now().isoformat(),
                'total_logs': len(self.logs),
                'logs': self.logs
            }, indent=2)
        elif format == 'csv':
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(['timestamp', 'level', 'message', 'correlation_id', 'metadata'])

            # Write logs
            for log in self.logs:
                writer.writerow([
                    log['timestamp'],
                    log['level'],
                    log['message'],
                    log.get('correlation_id', ''),
                    json.dumps(log.get('metadata', {}))
                ])

            return output.getvalue()

        raise ValueError(f"Unsupported format: {format}")


# Global instance
logging_service = LoggingService()
