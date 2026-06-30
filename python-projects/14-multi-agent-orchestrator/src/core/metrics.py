"""
Prometheus metrics collection
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from typing import Dict, Any

# Task metrics
task_created_total = Counter(
    'task_created_total',
    'Total number of tasks created',
    ['task_type']
)

task_completed_total = Counter(
    'task_completed_total',
    'Total number of tasks completed',
    ['task_type', 'status']
)

task_duration_seconds = Histogram(
    'task_duration_seconds',
    'Task execution duration in seconds',
    ['task_type'],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800)
)

task_queue_size = Gauge(
    'task_queue_size',
    'Current number of tasks in queue',
    ['status']
)

# Agent metrics
agent_active_total = Gauge(
    'agent_active_total',
    'Total number of active agents',
    ['role']
)

agent_task_execution_total = Counter(
    'agent_task_execution_total',
    'Total number of tasks executed by agents',
    ['agent_name', 'role', 'status']
)

agent_idle_time_seconds = Histogram(
    'agent_idle_time_seconds',
    'Agent idle time in seconds',
    ['agent_name', 'role'],
    buckets=(1, 5, 10, 30, 60, 300, 600, 1800)
)

# LLM metrics
llm_call_total = Counter(
    'llm_call_total',
    'Total number of LLM API calls',
    ['provider', 'model']
)

llm_tokens_total = Counter(
    'llm_tokens_total',
    'Total number of tokens used',
    ['provider', 'model', 'token_type']
)

llm_cost_total = Counter(
    'llm_cost_total',
    'Total cost of LLM API calls in USD',
    ['provider', 'model']
)

llm_latency_seconds = Histogram(
    'llm_latency_seconds',
    'LLM API call latency in seconds',
    ['provider', 'model'],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30)
)

# API metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5)
)

# System metrics
system_errors_total = Counter(
    'system_errors_total',
    'Total number of system errors',
    ['error_type', 'component']
)

celery_worker_active = Gauge(
    'celery_worker_active',
    'Number of active Celery workers'
)

database_connections_active = Gauge(
    'database_connections_active',
    'Number of active database connections'
)


class MetricsCollector:
    """
    Centralized metrics collection
    """

    @staticmethod
    def record_task_created(task_type: str):
        """Record task creation"""
        task_created_total.labels(task_type=task_type).inc()

    @staticmethod
    def record_task_completed(task_type: str, status: str, duration: float):
        """Record task completion"""
        task_completed_total.labels(task_type=task_type, status=status).inc()
        task_duration_seconds.labels(task_type=task_type).observe(duration)

    @staticmethod
    def update_task_queue_size(status: str, count: int):
        """Update task queue size"""
        task_queue_size.labels(status=status).set(count)

    @staticmethod
    def update_agent_count(role: str, count: int):
        """Update active agent count"""
        agent_active_total.labels(role=role).set(count)

    @staticmethod
    def record_agent_task_execution(agent_name: str, role: str, status: str):
        """Record agent task execution"""
        agent_task_execution_total.labels(
            agent_name=agent_name,
            role=role,
            status=status
        ).inc()

    @staticmethod
    def record_agent_idle_time(agent_name: str, role: str, idle_seconds: float):
        """Record agent idle time"""
        agent_idle_time_seconds.labels(
            agent_name=agent_name,
            role=role
        ).observe(idle_seconds)

    @staticmethod
    def record_llm_call(
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
        latency: float
    ):
        """Record LLM API call"""
        llm_call_total.labels(provider=provider, model=model).inc()
        llm_tokens_total.labels(provider=provider, model=model, token_type='prompt').inc(prompt_tokens)
        llm_tokens_total.labels(provider=provider, model=model, token_type='completion').inc(completion_tokens)
        llm_cost_total.labels(provider=provider, model=model).inc(cost)
        llm_latency_seconds.labels(provider=provider, model=model).observe(latency)

    @staticmethod
    def record_http_request(method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request"""
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code
        ).inc()
        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

    @staticmethod
    def record_error(error_type: str, component: str):
        """Record system error"""
        system_errors_total.labels(
            error_type=error_type,
            component=component
        ).inc()

    @staticmethod
    def update_celery_workers(count: int):
        """Update Celery worker count"""
        celery_worker_active.set(count)

    @staticmethod
    def update_database_connections(count: int):
        """Update database connection count"""
        database_connections_active.set(count)

    @staticmethod
    def get_metrics() -> bytes:
        """
        Get all metrics in Prometheus format

        Returns:
            bytes: Prometheus metrics
        """
        return generate_latest()

    @staticmethod
    def get_content_type() -> str:
        """
        Get Prometheus metrics content type

        Returns:
            str: Content type
        """
        return CONTENT_TYPE_LATEST


# Singleton instance
metrics_collector = MetricsCollector()
