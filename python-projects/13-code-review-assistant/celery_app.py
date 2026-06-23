"""
Celery application configuration for async task processing
"""

import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Initialize Celery app
celery_app = Celery(
    'code_review_assistant',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1'),
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes max
    task_soft_time_limit=1500,  # 25 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    result_expires=86400,  # Results expire after 24 hours
)

# Auto-discover tasks from workers module
celery_app.autodiscover_tasks(['src.workers'])

# Task routes
celery_app.conf.task_routes = {
    'src.workers.analysis_worker.*': {'queue': 'analysis'},
    'src.workers.pr_worker.*': {'queue': 'pr_review'},
    'src.workers.notification_worker.*': {'queue': 'notifications'},
    'src.workers.schedule_worker.*': {'queue': 'scheduled'},
}

# Celery Beat schedule for periodic tasks
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'check-due-schedules': {
        'task': 'schedule_worker.check_due_schedules',
        'schedule': 60.0,  # Every 60 seconds
    },
    'send-daily-digests': {
        'task': 'notification_worker.send_daily_digests',
        'schedule': crontab(hour=9, minute=0),  # Daily at 9:00 AM UTC
    },
    'send-weekly-digests': {
        'task': 'notification_worker.send_weekly_digests',
        'schedule': crontab(hour=9, minute=0, day_of_week=1),  # Monday at 9:00 AM UTC
    },
}

if __name__ == '__main__':
    celery_app.start()
