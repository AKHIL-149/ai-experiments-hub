"""
Celery application configuration for distributed task processing
"""

import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

# Initialize Celery app
celery_app = Celery(
    'multi_agent_orchestrator',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1'),
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',

    # Timezone
    timezone='UTC',
    enable_utc=True,

    # Task execution
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes max per task
    task_soft_time_limit=1500,  # 25 minutes soft limit

    # Worker configuration
    worker_prefetch_multiplier=1,  # Fetch one task at a time for better distribution
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks to prevent memory leaks
    worker_disable_rate_limits=False,

    # Result backend
    result_expires=86400,  # Results expire after 24 hours
    result_backend_transport_options={
        'master_name': 'mymaster',
    },

    # Task result settings
    task_ignore_result=False,  # Store results for monitoring
    task_store_errors_even_if_ignored=True,

    # Task routing
    task_routes={
        'src.workers.task_worker.*': {'queue': 'tasks'},
        'src.workers.agent_worker.*': {'queue': 'agents'},
        'src.workers.orchestration_worker.*': {'queue': 'orchestration'},
        'src.workers.monitoring_worker.*': {'queue': 'monitoring'},
    },

    # Task priority
    task_queue_max_priority=10,
    task_default_priority=5,

    # Retry configuration
    task_autoretry_for=(Exception,),
    task_retry_backoff=True,
    task_retry_backoff_max=600,  # Max 10 minutes between retries
    task_retry_jitter=True,  # Add randomness to retry delays
)

# Auto-discover tasks from workers module
celery_app.autodiscover_tasks(['src.workers'])

# Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # Monitor task queue health every 5 minutes
    'monitor-queue-health': {
        'task': 'src.workers.monitoring_worker.monitor_queue_health',
        'schedule': 300.0,  # Every 5 minutes
    },

    # Check for stalled tasks every 2 minutes
    'check-stalled-tasks': {
        'task': 'src.workers.monitoring_worker.check_stalled_tasks',
        'schedule': 120.0,  # Every 2 minutes
    },

    # Update agent metrics every 10 minutes
    'update-agent-metrics': {
        'task': 'src.workers.monitoring_worker.update_agent_metrics',
        'schedule': 600.0,  # Every 10 minutes
    },

    # Cleanup completed tasks daily at 2 AM UTC
    'cleanup-completed-tasks': {
        'task': 'src.workers.monitoring_worker.cleanup_completed_tasks',
        'schedule': crontab(hour=2, minute=0),
    },

    # Generate daily reports at 9 AM UTC
    'generate-daily-report': {
        'task': 'src.workers.monitoring_worker.generate_daily_report',
        'schedule': crontab(hour=9, minute=0),
    },
}

# Celery signals for lifecycle hooks
@celery_app.task(bind=True)
def debug_task(self):
    """Debug task to verify Celery is working"""
    print(f'Request: {self.request!r}')
    return 'Celery is working!'


if __name__ == '__main__':
    celery_app.start()
