"""
Logging configuration and utilities
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pythonjsonlogger import jsonlogger
from src.core.config import settings


# Create logs directory
LOGS_DIR = Path("./logs")
LOGS_DIR.mkdir(exist_ok=True)


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter with additional fields
    """

    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)

        # Add timestamp
        log_record['timestamp'] = datetime.utcnow().isoformat()

        # Add log level
        log_record['level'] = record.levelname

        # Add service name
        log_record['service'] = 'multi-agent-orchestrator'

        # Add process and thread info
        log_record['process_id'] = record.process
        log_record['thread_id'] = record.thread

        # Add file and line number
        log_record['filename'] = record.filename
        log_record['line_number'] = record.lineno


def setup_logging(
    log_level: Optional[str] = None,
    json_logs: bool = True,
    log_file: bool = True
) -> logging.Logger:
    """
    Setup application logging

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: Use JSON formatting for logs
        log_file: Enable file logging

    Returns:
        logging.Logger: Configured logger
    """
    # Get log level from config or parameter
    level = log_level or settings.LOG_LEVEL
    log_level_value = getattr(logging, level.upper(), logging.INFO)

    # Create logger
    logger = logging.getLogger('multi_agent_orchestrator')
    logger.setLevel(log_level_value)

    # Remove existing handlers
    logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level_value)

    if json_logs:
        # JSON formatter for structured logging
        json_formatter = CustomJsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s'
        )
        console_handler.setFormatter(json_formatter)
    else:
        # Standard formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    # File handler
    if log_file:
        # Application log file
        app_log_file = LOGS_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(app_log_file)
        file_handler.setLevel(log_level_value)

        if json_logs:
            file_handler.setFormatter(json_formatter)
        else:
            file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

        # Error log file (only ERROR and above)
        error_log_file = LOGS_DIR / f"error_{datetime.now().strftime('%Y%m%d')}.log"
        error_handler = logging.FileHandler(error_log_file)
        error_handler.setLevel(logging.ERROR)

        if json_logs:
            error_handler.setFormatter(json_formatter)
        else:
            error_handler.setFormatter(formatter)

        logger.addHandler(error_handler)

    return logger


# Initialize default logger
logger = setup_logging()


def log_task_execution(task_id: int, status: str, duration: float = None, error: str = None):
    """
    Log task execution details

    Args:
        task_id: Task ID
        status: Task status
        duration: Execution duration in seconds
        error: Error message if failed
    """
    log_data = {
        'event': 'task_execution',
        'task_id': task_id,
        'status': status,
    }

    if duration is not None:
        log_data['duration_seconds'] = duration

    if error:
        log_data['error'] = error
        logger.error(f"Task {task_id} failed", extra=log_data)
    else:
        logger.info(f"Task {task_id} {status}", extra=log_data)


def log_agent_activity(agent_id: int, activity: str, task_id: int = None, details: dict = None):
    """
    Log agent activity

    Args:
        agent_id: Agent ID
        activity: Activity description
        task_id: Associated task ID
        details: Additional details
    """
    log_data = {
        'event': 'agent_activity',
        'agent_id': agent_id,
        'activity': activity,
    }

    if task_id:
        log_data['task_id'] = task_id

    if details:
        log_data.update(details)

    logger.info(f"Agent {agent_id}: {activity}", extra=log_data)


def log_api_request(method: str, path: str, status_code: int, duration_ms: float, user_agent: str = None):
    """
    Log API request

    Args:
        method: HTTP method
        path: Request path
        status_code: Response status code
        duration_ms: Request duration in milliseconds
        user_agent: User agent string
    """
    log_data = {
        'event': 'api_request',
        'method': method,
        'path': path,
        'status_code': status_code,
        'duration_ms': duration_ms,
    }

    if user_agent:
        log_data['user_agent'] = user_agent

    logger.info(f"{method} {path} {status_code}", extra=log_data)


def log_llm_call(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost: float,
    duration_seconds: float
):
    """
    Log LLM API call

    Args:
        provider: LLM provider (openai, anthropic)
        model: Model name
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        cost: API call cost
        duration_seconds: Call duration
    """
    log_data = {
        'event': 'llm_call',
        'provider': provider,
        'model': model,
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': prompt_tokens + completion_tokens,
        'cost': cost,
        'duration_seconds': duration_seconds,
    }

    logger.info(f"LLM call: {provider}/{model}", extra=log_data)


def log_system_metric(metric_name: str, value: float, unit: str = None, tags: dict = None):
    """
    Log system metric

    Args:
        metric_name: Metric name
        value: Metric value
        unit: Metric unit
        tags: Additional tags
    """
    log_data = {
        'event': 'system_metric',
        'metric_name': metric_name,
        'value': value,
    }

    if unit:
        log_data['unit'] = unit

    if tags:
        log_data['tags'] = tags

    logger.info(f"Metric: {metric_name}={value}", extra=log_data)
