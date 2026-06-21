"""
Webhook Service
Handles webhook events and triggers automatic code analysis
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from ..core.webhook_handler import GitHubEvent, get_webhook_handler
from ..core.github_app import get_github_app
from ..core.database import DatabaseManager
from ..core.queue_manager import get_queue_manager


logger = logging.getLogger(__name__)


class WebhookService:
    """
    Service for processing GitHub webhook events.

    Features:
    - Automatic PR analysis on PR events
    - Push event handling
    - Installation management
    - Async job queuing
    """

    def __init__(self):
        """Initialize webhook service"""
        self.db = DatabaseManager()
        self.github_app = get_github_app()
        self.webhook_handler = get_webhook_handler()
        self.queue_manager = get_queue_manager()

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register webhook event handlers"""
        self.webhook_handler.register_handler(
            GitHubEvent.PULL_REQUEST,
            self.handle_pull_request
        )
        self.webhook_handler.register_handler(
            GitHubEvent.PUSH,
            self.handle_push
        )
        self.webhook_handler.register_handler(
            GitHubEvent.INSTALLATION,
            self.handle_installation
        )
        self.webhook_handler.register_handler(
            GitHubEvent.INSTALLATION_REPOSITORIES,
            self.handle_installation_repositories
        )

    async def handle_pull_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle pull_request webhook event.

        Args:
            payload: Webhook payload

        Returns:
            Response dictionary
        """
        action = payload.get('action')
        pr_info = self.webhook_handler.extract_pr_info(payload)

        if not pr_info:
            return {'status': 'error', 'message': 'Invalid PR payload'}

        # Only trigger analysis on opened, synchronized, or reopened
        if action not in ['opened', 'synchronize', 'reopened']:
            return {
                'status': 'ignored',
                'message': f'PR action {action} does not trigger analysis'
            }

        logger.info(
            f"PR #{pr_info['pr_number']} {action} in {pr_info['repo_full_name']}"
        )

        try:
            # Get or create repository
            repository = self._get_or_create_repository(pr_info)

            if not repository:
                return {
                    'status': 'error',
                    'message': 'Failed to get/create repository'
                }

            # Queue PR analysis job
            job = self.queue_manager.queue_pr_analysis(
                repository_id=repository.id,
                pr_number=pr_info['pr_number'],
                installation_id=pr_info.get('installation_id'),
                priority='high' if action == 'opened' else 'normal'
            )

            logger.info(
                f"Queued analysis job {job.id} for PR #{pr_info['pr_number']}"
            )

            return {
                'status': 'success',
                'message': 'PR analysis queued',
                'job_id': job.id,
                'pr_number': pr_info['pr_number']
            }

        except Exception as e:
            logger.error(f"Failed to handle PR event: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e)
            }

    async def handle_push(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle push webhook event.

        Args:
            payload: Webhook payload

        Returns:
            Response dictionary
        """
        push_info = self.webhook_handler.extract_push_info(payload)

        if not push_info:
            return {'status': 'error', 'message': 'Invalid push payload'}

        # Skip if it's a tag push
        if push_info['ref'].startswith('refs/tags/'):
            return {
                'status': 'ignored',
                'message': 'Tag pushes are not analyzed'
            }

        logger.info(
            f"Push to {push_info['ref']} in {push_info['repo_full_name']}"
        )

        # For now, we only analyze PRs automatically
        # Direct pushes to main could be configured for analysis
        return {
            'status': 'ignored',
            'message': 'Push events do not trigger analysis (PRs only)'
        }

    async def handle_installation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle installation webhook event.

        Args:
            payload: Webhook payload

        Returns:
            Response dictionary
        """
        action = payload.get('action')
        installation_id = payload.get('installation', {}).get('id')

        logger.info(f"GitHub App installation {action}: {installation_id}")

        if action == 'created':
            # Installation created - welcome message or setup
            repositories = payload.get('repositories', [])
            logger.info(
                f"App installed with access to {len(repositories)} repositories"
            )

        elif action == 'deleted':
            # Installation removed - cleanup
            logger.info(f"App uninstalled: {installation_id}")
            # Revoke cached tokens
            if installation_id:
                self.github_app.revoke_installation_token(installation_id)

        return {
            'status': 'success',
            'action': action,
            'installation_id': installation_id
        }

    async def handle_installation_repositories(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle installation_repositories webhook event.

        Args:
            payload: Webhook payload

        Returns:
            Response dictionary
        """
        action = payload.get('action')
        repositories_added = payload.get('repositories_added', [])
        repositories_removed = payload.get('repositories_removed', [])

        logger.info(
            f"Installation repositories {action}: "
            f"+{len(repositories_added)} -{len(repositories_removed)}"
        )

        return {
            'status': 'success',
            'action': action,
            'added': len(repositories_added),
            'removed': len(repositories_removed)
        }

    def _get_or_create_repository(self, pr_info: Dict[str, Any]):
        """
        Get existing repository or create new one.

        Args:
            pr_info: Pull request information

        Returns:
            Repository object
        """
        from ..core.database import Repository

        session = self.db.get_session()

        try:
            # Try to find existing repository
            github_url = f"https://github.com/{pr_info['repo_full_name']}"
            repository = session.query(Repository).filter_by(
                github_url=github_url
            ).first()

            if repository:
                return repository

            # Create new repository (associate with system user ID 1)
            repository = Repository(
                user_id=1,  # System/webhook user
                name=pr_info['repo_name'],
                github_url=github_url,
                default_branch=pr_info['base_ref'],
                status='active',
                last_synced_at=datetime.now(timezone.utc)
            )

            session.add(repository)
            session.commit()
            session.refresh(repository)

            logger.info(f"Created repository: {github_url}")

            return repository

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to get/create repository: {e}")
            raise
        finally:
            session.close()


# Global webhook service instance
_webhook_service: Optional[WebhookService] = None


def get_webhook_service() -> WebhookService:
    """
    Get the global webhook service instance.

    Returns:
        WebhookService instance
    """
    global _webhook_service

    if _webhook_service is None:
        _webhook_service = WebhookService()

    return _webhook_service
