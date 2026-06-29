"""
Cleanup Worker
Background tasks for cleaning up old data, temporary files, and expired resources
"""

import os
import shutil
from datetime import datetime, timedelta
from celery import shared_task
from celery.result import AsyncResult
from sqlalchemy import and_

from src.core.database import DatabaseManager
from src.services.cache_service import cache_service


@shared_task(name='cleanup_old_task_results', bind=True)
def cleanup_old_task_results(self, days_to_keep: int = 7):
    """
    Clean up old Celery task results from Redis/database

    Args:
        days_to_keep: Number of days to keep task results (default: 7)

    Returns:
        dict: Cleanup statistics
    """
    from celery_app import celery_app

    try:
        # Get all task IDs from Celery inspect
        inspect = celery_app.control.inspect()

        # Track statistics
        stats = {
            'tasks_checked': 0,
            'tasks_cleaned': 0,
            'errors': 0,
            'cutoff_date': (datetime.now() - timedelta(days=days_to_keep)).isoformat()
        }

        # Get all stored task results
        # Note: This is implementation-specific to Redis backend
        if cache_service.use_redis and cache_service.redis_client:
            try:
                # Get all celery task result keys
                task_keys = cache_service.redis_client.keys('celery-task-meta-*')
                stats['tasks_checked'] = len(task_keys)

                for key in task_keys:
                    try:
                        # Get task result
                        task_data = cache_service.redis_client.get(key)
                        if task_data:
                            import json
                            task_info = json.loads(task_data)

                            # Check if task is old enough to clean
                            if 'date_done' in task_info:
                                date_done = datetime.fromisoformat(task_info['date_done'].replace('Z', '+00:00'))
                                cutoff = datetime.now() - timedelta(days=days_to_keep)

                                if date_done < cutoff:
                                    # Delete old task result
                                    cache_service.redis_client.delete(key)
                                    stats['tasks_cleaned'] += 1
                    except Exception as e:
                        stats['errors'] += 1
                        print(f"Error cleaning task {key}: {e}")
            except Exception as e:
                print(f"Error accessing Redis for task cleanup: {e}")
                stats['errors'] += 1

        print(f"✅ Cleanup complete: Cleaned {stats['tasks_cleaned']} out of {stats['tasks_checked']} tasks")
        return stats

    except Exception as e:
        print(f"❌ Cleanup failed: {str(e)}")
        return {'error': str(e)}


@shared_task(name='cleanup_temporary_files', bind=True)
def cleanup_temporary_files(self, temp_dir: str = './data/temp', days_to_keep: int = 1):
    """
    Clean up temporary files older than specified days

    Args:
        temp_dir: Directory containing temporary files
        days_to_keep: Number of days to keep temporary files (default: 1)

    Returns:
        dict: Cleanup statistics
    """
    try:
        stats = {
            'files_checked': 0,
            'files_deleted': 0,
            'bytes_freed': 0,
            'errors': 0
        }

        if not os.path.exists(temp_dir):
            return stats

        cutoff_time = datetime.now() - timedelta(days=days_to_keep)
        cutoff_timestamp = cutoff_time.timestamp()

        # Walk through temp directory
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                stats['files_checked'] += 1

                try:
                    # Check file modification time
                    file_mtime = os.path.getmtime(file_path)

                    if file_mtime < cutoff_timestamp:
                        # Get file size before deletion
                        file_size = os.path.getsize(file_path)

                        # Delete old file
                        os.remove(file_path)
                        stats['files_deleted'] += 1
                        stats['bytes_freed'] += file_size
                except Exception as e:
                    stats['errors'] += 1
                    print(f"Error deleting {file_path}: {e}")

        # Clean up empty directories
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if not os.listdir(dir_path):  # Empty directory
                        os.rmdir(dir_path)
                except Exception as e:
                    print(f"Error removing empty directory {dir_path}: {e}")

        mb_freed = round(stats['bytes_freed'] / (1024 * 1024), 2)
        print(f"✅ Cleanup complete: Deleted {stats['files_deleted']} files, freed {mb_freed} MB")
        return stats

    except Exception as e:
        print(f"❌ Temporary file cleanup failed: {str(e)}")
        return {'error': str(e)}


@shared_task(name='cleanup_old_analysis_data', bind=True)
def cleanup_old_analysis_data(self, days_to_keep: int = 90):
    """
    Clean up old analysis data from database

    Args:
        days_to_keep: Number of days to keep analysis data (default: 90)

    Returns:
        dict: Cleanup statistics
    """
    try:
        from src.core.database import AnalysisJob, AnalysisJobStatus

        db_manager = DatabaseManager()
        stats = {
            'jobs_checked': 0,
            'jobs_deleted': 0,
            'errors': 0
        }

        with db_manager.get_session() as session:
            # Find old completed/failed jobs
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)

            old_jobs = session.query(AnalysisJob).filter(
                and_(
                    AnalysisJob.completed_at < cutoff_date,
                    AnalysisJob.status.in_([
                        AnalysisJobStatus.COMPLETED,
                        AnalysisJobStatus.FAILED
                    ])
                )
            ).all()

            stats['jobs_checked'] = len(old_jobs)

            for job in old_jobs:
                try:
                    # Delete job (cascades to related data if configured)
                    session.delete(job)
                    stats['jobs_deleted'] += 1
                except Exception as e:
                    stats['errors'] += 1
                    print(f"Error deleting job {job.id}: {e}")

            session.commit()

        print(f"✅ Analysis cleanup complete: Deleted {stats['jobs_deleted']} old jobs")
        return stats

    except Exception as e:
        print(f"❌ Analysis data cleanup failed: {str(e)}")
        return {'error': str(e)}


@shared_task(name='cleanup_cache', bind=True)
def cleanup_cache(self, pattern: str = None):
    """
    Clean up cache entries

    Args:
        pattern: Optional pattern to match cache keys (e.g., "analysis:*")
                 If None, clears all cache

    Returns:
        dict: Cleanup statistics
    """
    try:
        stats = {
            'keys_deleted': 0,
            'errors': 0
        }

        if pattern:
            # Delete keys matching pattern
            stats['keys_deleted'] = cache_service.delete_pattern(pattern)
        else:
            # Clear all cache
            stats['keys_deleted'] = cache_service.clear()

        print(f"✅ Cache cleanup complete: Cleared {stats['keys_deleted']} keys")
        return stats

    except Exception as e:
        print(f"❌ Cache cleanup failed: {str(e)}")
        return {'error': str(e)}


@shared_task(name='cleanup_orphaned_files', bind=True)
def cleanup_orphaned_files(self, repos_dir: str = './data/repos'):
    """
    Clean up orphaned repository files (repos that were deleted from database)

    Args:
        repos_dir: Directory containing cloned repositories

    Returns:
        dict: Cleanup statistics
    """
    try:
        from src.core.database import Repository

        db_manager = DatabaseManager()
        stats = {
            'directories_checked': 0,
            'directories_deleted': 0,
            'bytes_freed': 0,
            'errors': 0
        }

        if not os.path.exists(repos_dir):
            return stats

        # Get all repository IDs from database
        with db_manager.get_session() as session:
            active_repo_ids = {str(repo.id) for repo in session.query(Repository.id).all()}

        # Check each directory in repos_dir
        for dir_name in os.listdir(repos_dir):
            dir_path = os.path.join(repos_dir, dir_name)

            if not os.path.isdir(dir_path):
                continue

            stats['directories_checked'] += 1

            # Check if directory corresponds to an active repository
            if dir_name not in active_repo_ids:
                try:
                    # Calculate directory size
                    dir_size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, dirnames, filenames in os.walk(dir_path)
                        for filename in filenames
                    )

                    # Delete orphaned repository directory
                    shutil.rmtree(dir_path)
                    stats['directories_deleted'] += 1
                    stats['bytes_freed'] += dir_size

                    print(f"Deleted orphaned repository: {dir_name}")
                except Exception as e:
                    stats['errors'] += 1
                    print(f"Error deleting orphaned repo {dir_name}: {e}")

        mb_freed = round(stats['bytes_freed'] / (1024 * 1024), 2)
        print(f"✅ Orphaned files cleanup complete: Deleted {stats['directories_deleted']} directories, freed {mb_freed} MB")
        return stats

    except Exception as e:
        print(f"❌ Orphaned files cleanup failed: {str(e)}")
        return {'error': str(e)}


@shared_task(name='scheduled_cleanup', bind=True)
def scheduled_cleanup(self):
    """
    Scheduled task that runs all cleanup tasks
    Run this daily via Celery Beat

    Returns:
        dict: Combined cleanup statistics
    """
    try:
        print("🧹 Starting scheduled cleanup...")

        results = {}

        # Run all cleanup tasks
        results['task_results'] = cleanup_old_task_results.delay(days_to_keep=7).get(timeout=60)
        results['temp_files'] = cleanup_temporary_files.delay(days_to_keep=1).get(timeout=60)
        results['analysis_data'] = cleanup_old_analysis_data.delay(days_to_keep=90).get(timeout=60)
        results['orphaned_files'] = cleanup_orphaned_files.delay().get(timeout=60)

        # Clear old cached analysis results
        results['cache'] = cleanup_cache.delay(pattern='analysis:*').get(timeout=30)

        print("✅ Scheduled cleanup complete")
        return results

    except Exception as e:
        print(f"❌ Scheduled cleanup failed: {str(e)}")
        return {'error': str(e)}
