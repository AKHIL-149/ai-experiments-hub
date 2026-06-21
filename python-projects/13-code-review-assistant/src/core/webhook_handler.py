"""
GitHub Webhook Handler
Processes incoming GitHub webhook events with signature verification
"""

import hmac
import hashlib
import os
from typing import Dict, Any, Optional, Callable
from enum import Enum


class GitHubEvent(Enum):
    """GitHub webhook event types"""
    PULL_REQUEST = 'pull_request'
    PUSH = 'push'
    PULL_REQUEST_REVIEW = 'pull_request_review'
    PULL_REQUEST_REVIEW_COMMENT = 'pull_request_review_comment'
    ISSUE_COMMENT = 'issue_comment'
    CHECK_RUN = 'check_run'
    CHECK_SUITE = 'check_suite'
    INSTALLATION = 'installation'
    INSTALLATION_REPOSITORIES = 'installation_repositories'
    PING = 'ping'


class WebhookHandler:
    """
    Handles GitHub webhook events with signature verification.

    Features:
    - HMAC signature verification
    - Event type detection
    - Event routing to registered handlers
    - Error handling and logging
    """

    def __init__(self, secret: Optional[str] = None):
        """
        Initialize webhook handler.

        Args:
            secret: Webhook secret for signature verification (defaults to env var)
        """
        self.secret = (secret or os.getenv('GITHUB_WEBHOOK_SECRET', '')).encode('utf-8')
        self._handlers: Dict[GitHubEvent, list] = {}

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify GitHub webhook signature.

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value

        Returns:
            True if signature is valid
        """
        if not self.secret:
            # If no secret configured, skip verification (development only)
            return True

        # GitHub sends signature as 'sha256=<hash>'
        if not signature.startswith('sha256='):
            return False

        expected_signature = signature.split('=', 1)[1]

        # Calculate HMAC
        mac = hmac.new(self.secret, msg=payload, digestmod=hashlib.sha256)
        computed_signature = mac.hexdigest()

        # Constant-time comparison
        return hmac.compare_digest(computed_signature, expected_signature)

    def register_handler(self, event: GitHubEvent, handler: Callable):
        """
        Register a handler for a specific event type.

        Args:
            event: GitHub event type
            handler: Async function to handle the event
        """
        if event not in self._handlers:
            self._handlers[event] = []

        self._handlers[event].append(handler)

    def unregister_handler(self, event: GitHubEvent, handler: Callable):
        """
        Unregister a handler for a specific event type.

        Args:
            event: GitHub event type
            handler: Handler function to remove
        """
        if event in self._handlers and handler in self._handlers[event]:
            self._handlers[event].remove(handler)

    async def handle_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a webhook event.

        Args:
            event_type: GitHub event type (from X-GitHub-Event header)
            payload: Parsed JSON payload

        Returns:
            Response dictionary with status and message
        """
        try:
            # Convert event type to enum
            try:
                github_event = GitHubEvent(event_type)
            except ValueError:
                return {
                    'status': 'ignored',
                    'message': f'Unsupported event type: {event_type}'
                }

            # Handle ping events
            if github_event == GitHubEvent.PING:
                return {
                    'status': 'success',
                    'message': 'Pong!'
                }

            # Get handlers for this event
            handlers = self._handlers.get(github_event, [])

            if not handlers:
                return {
                    'status': 'ignored',
                    'message': f'No handlers registered for {event_type}'
                }

            # Execute all handlers
            results = []
            for handler in handlers:
                try:
                    result = await handler(payload)
                    results.append(result)
                except Exception as e:
                    results.append({
                        'status': 'error',
                        'handler': handler.__name__,
                        'error': str(e)
                    })

            return {
                'status': 'success',
                'event': event_type,
                'handlers_executed': len(results),
                'results': results
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to process event: {str(e)}'
            }

    def extract_pr_info(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract pull request information from payload.

        Args:
            payload: Webhook payload

        Returns:
            Dictionary with PR info or None
        """
        if 'pull_request' not in payload:
            return None

        pr = payload['pull_request']
        repo = payload['repository']

        return {
            'pr_number': pr['number'],
            'pr_title': pr['title'],
            'pr_state': pr['state'],
            'pr_action': payload.get('action'),
            'repo_owner': repo['owner']['login'],
            'repo_name': repo['name'],
            'repo_full_name': repo['full_name'],
            'head_sha': pr['head']['sha'],
            'head_ref': pr['head']['ref'],
            'base_ref': pr['base']['ref'],
            'author': pr['user']['login'],
            'html_url': pr['html_url'],
            'installation_id': payload.get('installation', {}).get('id')
        }

    def extract_push_info(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract push information from payload.

        Args:
            payload: Webhook payload

        Returns:
            Dictionary with push info or None
        """
        if 'ref' not in payload:
            return None

        repo = payload['repository']

        return {
            'ref': payload['ref'],
            'before': payload['before'],
            'after': payload['after'],
            'repo_owner': repo['owner']['login'],
            'repo_name': repo['name'],
            'repo_full_name': repo['full_name'],
            'pusher': payload['pusher']['name'],
            'commits': payload.get('commits', []),
            'installation_id': payload.get('installation', {}).get('id')
        }


# Global webhook handler instance
_webhook_handler: Optional[WebhookHandler] = None


def get_webhook_handler() -> WebhookHandler:
    """
    Get the global webhook handler instance.

    Returns:
        WebhookHandler instance
    """
    global _webhook_handler

    if _webhook_handler is None:
        _webhook_handler = WebhookHandler()

    return _webhook_handler
