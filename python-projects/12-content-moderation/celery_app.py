#!/usr/bin/env python3
"""
Celery Application Entry Point.

Start workers with:
    celery -A celery_app worker -Q critical,high,default,batch -l info
"""

import os
from celery import Celery
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Celery app
app = Celery('content_moderation')

# Load configuration from celery_config module
app.config_from_object('src.workers.celery_config')

# Auto-discover tasks in workers module
app.autodiscover_tasks(['src.workers'])

if __name__ == '__main__':
    app.start()
