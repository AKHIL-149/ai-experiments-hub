"""Celery worker for repository operations"""
import os
from datetime import datetime
from typing import Dict, Any, Optional
from celery_app import celery_app
from src.core.git_client import GitClient
from src.core.database import DatabaseManager, RepositoryStatus
from src.services.repository_service import RepositoryService


# Initialize components
db_url = os.getenv('DATABASE_URL', 'sqlite:///./data/database.db')
db_manager = DatabaseManager(db_url)
git_client = GitClient()


@celery_app.task(name='src.workers.repository_worker.clone_repository_task', bind=True)
def clone_repository_task(
    self,
    repository_id: str,
    github_url: str,
    branch: Optional[str] = None,
    depth: Optional[int] = 1
) -> Dict[str, Any]:
    """
    Async task to clone a repository.

    Args:
        repository_id: Repository ID in database
        github_url: GitHub repository URL
        branch: Specific branch to clone (optional)
        depth: Clone depth for shallow clone (default: 1)

    Returns:
        Result dictionary with success status and clone path
    """
    job_id = self.request.id

    try:
        # Update task state to CLONING
        self.update_state(
            state='CLONING',
            meta={
                'status': 'Cloning repository...',
                'repository_id': repository_id,
                'github_url': github_url,
                'started_at': datetime.utcnow().isoformat()
            }
        )

        # Update repository status to CLONING in database
        with db_manager.get_session() as db:
            service = RepositoryService(db)
            service.mark_as_cloning(repository_id)

        # Clone the repository
        success, clone_path, error = git_client.clone_repository(
            repo_url=github_url,
            repo_name=repository_id,  # Use repository_id as directory name
            branch=branch,
            depth=depth
        )

        if not success:
            # Update repository status to ERROR
            with db_manager.get_session() as db:
                service = RepositoryService(db)
                service.mark_as_error(repository_id, error)

            self.update_state(
                state='FAILURE',
                meta={
                    'status': 'Clone failed',
                    'error': error,
                    'repository_id': repository_id
                }
            )

            return {
                'success': False,
                'error': error,
                'repository_id': repository_id
            }

        # Update repository status to READY
        with db_manager.get_session() as db:
            service = RepositoryService(db)
            service.mark_as_ready(repository_id, clone_path)

        self.update_state(
            state='SUCCESS',
            meta={
                'status': 'Repository cloned successfully',
                'clone_path': clone_path,
                'repository_id': repository_id,
                'completed_at': datetime.utcnow().isoformat()
            }
        )

        return {
            'success': True,
            'clone_path': clone_path,
            'repository_id': repository_id,
            'message': 'Repository cloned successfully'
        }

    except Exception as e:
        # Update repository status to ERROR
        with db_manager.get_session() as db:
            service = RepositoryService(db)
            service.mark_as_error(repository_id, str(e))

        self.update_state(
            state='FAILURE',
            meta={
                'status': 'Clone failed',
                'error': str(e),
                'repository_id': repository_id
            }
        )

        return {
            'success': False,
            'error': str(e),
            'repository_id': repository_id
        }


@celery_app.task(name='src.workers.repository_worker.sync_repository_task', bind=True)
def sync_repository_task(
    self,
    repository_id: str,
    clone_path: str
) -> Dict[str, Any]:
    """
    Async task to sync (pull) repository updates.

    Args:
        repository_id: Repository ID in database
        clone_path: Local path to the cloned repository

    Returns:
        Result dictionary with success status
    """
    try:
        # Update task state
        self.update_state(
            state='SYNCING',
            meta={
                'status': 'Syncing repository...',
                'repository_id': repository_id,
                'started_at': datetime.utcnow().isoformat()
            }
        )

        # Check if repository exists locally
        if not git_client.repository_exists(clone_path):
            return {
                'success': False,
                'error': 'Repository not found locally. Please clone first.',
                'repository_id': repository_id
            }

        # Fetch updates
        success, error = git_client.fetch_repository(clone_path)
        if not success:
            return {
                'success': False,
                'error': f'Fetch failed: {error}',
                'repository_id': repository_id
            }

        # Pull updates
        success, error = git_client.pull_repository(clone_path)
        if not success:
            return {
                'success': False,
                'error': f'Pull failed: {error}',
                'repository_id': repository_id
            }

        # Update repository last_synced_at
        with db_manager.get_session() as db:
            service = RepositoryService(db)
            service.mark_as_ready(repository_id, clone_path)

        self.update_state(
            state='SUCCESS',
            meta={
                'status': 'Repository synced successfully',
                'repository_id': repository_id,
                'completed_at': datetime.utcnow().isoformat()
            }
        )

        return {
            'success': True,
            'repository_id': repository_id,
            'message': 'Repository synced successfully'
        }

    except Exception as e:
        self.update_state(
            state='FAILURE',
            meta={
                'status': 'Sync failed',
                'error': str(e),
                'repository_id': repository_id
            }
        )

        return {
            'success': False,
            'error': str(e),
            'repository_id': repository_id
        }


@celery_app.task(name='src.workers.repository_worker.delete_repository_task', bind=True)
def delete_repository_task(
    self,
    repository_id: str,
    clone_path: str
) -> Dict[str, Any]:
    """
    Async task to delete a cloned repository.

    Args:
        repository_id: Repository ID in database
        clone_path: Local path to the cloned repository

    Returns:
        Result dictionary with success status
    """
    try:
        # Update task state
        self.update_state(
            state='DELETING',
            meta={
                'status': 'Deleting repository files...',
                'repository_id': repository_id,
                'started_at': datetime.utcnow().isoformat()
            }
        )

        # Delete repository if it exists
        if os.path.exists(clone_path):
            success, error = git_client.delete_repository(clone_path)
            if not success:
                return {
                    'success': False,
                    'error': error,
                    'repository_id': repository_id
                }

        self.update_state(
            state='SUCCESS',
            meta={
                'status': 'Repository deleted successfully',
                'repository_id': repository_id,
                'completed_at': datetime.utcnow().isoformat()
            }
        )

        return {
            'success': True,
            'repository_id': repository_id,
            'message': 'Repository files deleted successfully'
        }

    except Exception as e:
        self.update_state(
            state='FAILURE',
            meta={
                'status': 'Delete failed',
                'error': str(e),
                'repository_id': repository_id
            }
        )

        return {
            'success': False,
            'error': str(e),
            'repository_id': repository_id
        }
