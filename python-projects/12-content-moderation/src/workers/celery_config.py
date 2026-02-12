"""
Celery Configuration for Content Moderation System.

Defines queues, routing, retry policies, and worker settings.
"""

import os
from kombu import Queue, Exchange

# Broker and backend
broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')

# Task serialization
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'UTC'
enable_utc = True

# Result backend settings
result_expires = 3600  # Results expire after 1 hour
result_persistent = True

# Task execution settings
task_acks_late = True  # Acknowledge tasks after completion
task_reject_on_worker_lost = True
worker_prefetch_multiplier = 1  # One task at a time per worker

# Retry settings
task_default_retry_delay = 60  # Retry after 60 seconds
task_max_retries = 3

# Queue configuration
default_exchange = Exchange('moderation', type='direct')

task_queues = (
    Queue('critical', exchange=default_exchange, routing_key='critical', priority=10),
    Queue('high', exchange=default_exchange, routing_key='high', priority=5),
    Queue('default', exchange=default_exchange, routing_key='default', priority=0),
    Queue('batch', exchange=default_exchange, routing_key='batch', priority=-5),
)

task_default_queue = 'default'
task_default_exchange = 'moderation'
task_default_routing_key = 'default'

# Task routing
task_routes = {
    'src.workers.text_worker.classify_text_task': {'queue': 'default'},
    'src.workers.image_worker.classify_image_task': {'queue': 'high'},
    'src.workers.video_worker.classify_video_task': {'queue': 'high'},
}

# Worker settings
worker_max_tasks_per_child = 1000  # Restart worker after 1000 tasks
worker_disable_rate_limits = True

# Monitoring
worker_send_task_events = True
task_send_sent_event = True

# Task time limits
task_soft_time_limit = 300  # 5 minutes soft limit
task_time_limit = 600  # 10 minutes hard limit

# Retry configuration with exponential backoff
task_autoretry_for = (Exception,)
task_retry_backoff = True  # Enable exponential backoff
task_retry_backoff_max = 600  # Max 10 minutes between retries
task_retry_jitter = True  # Add randomness to retry delays
