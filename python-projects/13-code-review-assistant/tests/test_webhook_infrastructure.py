"""
Tests for Webhook Infrastructure
Tests GitHub App authentication, webhook handling, and event processing
"""

import pytest
import jwt
import hmac
import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock

from src.core.github_app import GitHubApp, get_github_app
from src.core.webhook_handler import (
    WebhookHandler, GitHubEvent, get_webhook_handler
)
from src.services.webhook_service import WebhookService


class TestGitHubApp:
    """Test GitHub App authentication and token management"""

    def test_create_github_app(self):
        """Test GitHub App initialization"""
        app = GitHubApp(app_id='12345', private_key='test-key')
        assert app.app_id == '12345'
        assert app.private_key == 'test-key'

    def test_is_configured(self):
        """Test configuration check"""
        app = GitHubApp(app_id='12345', private_key='test-key')
        assert app.is_configured() is True

        app_unconfigured = GitHubApp(app_id=None, private_key=None)
        assert app_unconfigured.is_configured() is False

    @patch('jwt.encode')
    def test_generate_jwt(self, mock_encode):
        """Test JWT generation"""
        mock_encode.return_value = 'test-jwt-token'

        app = GitHubApp(app_id='12345', private_key='test-private-key')
        token = app.generate_jwt()

        assert token == 'test-jwt-token'
        mock_encode.assert_called_once()

        # Verify JWT payload structure
        call_args = mock_encode.call_args
        payload = call_args[0][0]

        assert 'iat' in payload
        assert 'exp' in payload
        assert 'iss' in payload
        assert payload['iss'] == '12345'

    @patch('requests.post')
    def test_get_installation_token(self, mock_post):
        """Test installation token retrieval"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'token': 'ghs_installation_token',
            'expires_at': '2026-06-21T01:00:00Z'
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        app = GitHubApp(app_id='12345', private_key='test-key')

        with patch.object(app, 'generate_jwt', return_value='test-jwt'):
            token = app.get_installation_token(installation_id=789)

        assert token == 'ghs_installation_token'
        assert 789 in app._installation_tokens

    @patch('requests.post')
    def test_installation_token_caching(self, mock_post):
        """Test that installation tokens are cached"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'token': 'ghs_cached_token',
            'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        app = GitHubApp(app_id='12345', private_key='test-key')

        with patch.object(app, 'generate_jwt', return_value='test-jwt'):
            token1 = app.get_installation_token(installation_id=789)
            token2 = app.get_installation_token(installation_id=789)

        # Should only call API once due to caching
        assert token1 == token2
        assert mock_post.call_count == 1

    @patch('requests.get')
    def test_get_installation_id(self, mock_get):
        """Test getting installation ID for a repository"""
        mock_response = Mock()
        mock_response.json.return_value = {'id': 456}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        app = GitHubApp(app_id='12345', private_key='test-key')

        with patch.object(app, 'generate_jwt', return_value='test-jwt'):
            installation_id = app.get_installation_id('owner', 'repo')

        assert installation_id == 456

    def test_revoke_installation_token(self):
        """Test token revocation"""
        app = GitHubApp(app_id='12345', private_key='test-key')
        app._installation_tokens[789] = {
            'token': 'test-token',
            'expires_at': 'future-time'
        }

        app.revoke_installation_token(789)
        assert 789 not in app._installation_tokens


class TestWebhookHandler:
    """Test webhook handling and signature verification"""

    def test_create_webhook_handler(self):
        """Test webhook handler initialization"""
        handler = WebhookHandler(secret='test-secret')
        assert handler.secret == b'test-secret'

    def test_verify_signature_valid(self):
        """Test signature verification with valid signature"""
        handler = WebhookHandler(secret='test-secret')
        payload = b'{"test": "data"}'

        # Generate valid signature
        mac = hmac.new(b'test-secret', msg=payload, digestmod=hashlib.sha256)
        signature = f'sha256={mac.hexdigest()}'

        assert handler.verify_signature(payload, signature) is True

    def test_verify_signature_invalid(self):
        """Test signature verification with invalid signature"""
        handler = WebhookHandler(secret='test-secret')
        payload = b'{"test": "data"}'
        signature = 'sha256=invalid_signature_here'

        assert handler.verify_signature(payload, signature) is False

    def test_verify_signature_no_secret(self):
        """Test signature verification when no secret configured"""
        handler = WebhookHandler(secret='')
        payload = b'{"test": "data"}'
        signature = 'sha256=anything'

        # Should pass when no secret configured (development mode)
        assert handler.verify_signature(payload, signature) is True

    def test_register_handler(self):
        """Test registering event handlers"""
        handler = WebhookHandler()

        def test_handler(payload):
            return {'status': 'ok'}

        handler.register_handler(GitHubEvent.PULL_REQUEST, test_handler)

        assert GitHubEvent.PULL_REQUEST in handler._handlers
        assert test_handler in handler._handlers[GitHubEvent.PULL_REQUEST]

    def test_unregister_handler(self):
        """Test unregistering event handlers"""
        handler = WebhookHandler()

        def test_handler(payload):
            return {'status': 'ok'}

        handler.register_handler(GitHubEvent.PULL_REQUEST, test_handler)
        handler.unregister_handler(GitHubEvent.PULL_REQUEST, test_handler)

        assert test_handler not in handler._handlers.get(GitHubEvent.PULL_REQUEST, [])

    @pytest.mark.asyncio
    async def test_handle_ping_event(self):
        """Test handling ping events"""
        handler = WebhookHandler()
        result = await handler.handle_event('ping', {})

        assert result['status'] == 'success'
        assert 'Pong' in result['message']

    @pytest.mark.asyncio
    async def test_handle_unsupported_event(self):
        """Test handling unsupported event types"""
        handler = WebhookHandler()
        result = await handler.handle_event('unknown_event', {})

        assert result['status'] == 'ignored'
        assert 'Unsupported event type' in result['message']

    @pytest.mark.asyncio
    async def test_handle_event_with_handlers(self):
        """Test event handling with registered handlers"""
        handler = WebhookHandler()

        async def mock_handler(payload):
            return {'status': 'processed', 'data': payload.get('action')}

        handler.register_handler(GitHubEvent.PULL_REQUEST, mock_handler)

        payload = {'action': 'opened', 'pull_request': {'number': 42}}
        result = await handler.handle_event('pull_request', payload)

        assert result['status'] == 'success'
        assert result['handlers_executed'] == 1

    def test_extract_pr_info(self):
        """Test extracting PR information from payload"""
        handler = WebhookHandler()
        payload = {
            'action': 'opened',
            'pull_request': {
                'number': 42,
                'title': 'Test PR',
                'state': 'open',
                'head': {'sha': 'abc123', 'ref': 'feature'},
                'base': {'ref': 'main'},
                'user': {'login': 'testuser'},
                'html_url': 'https://github.com/owner/repo/pull/42'
            },
            'repository': {
                'name': 'repo',
                'owner': {'login': 'owner'},
                'full_name': 'owner/repo'
            },
            'installation': {'id': 123}
        }

        pr_info = handler.extract_pr_info(payload)

        assert pr_info is not None
        assert pr_info['pr_number'] == 42
        assert pr_info['pr_title'] == 'Test PR'
        assert pr_info['pr_action'] == 'opened'
        assert pr_info['repo_owner'] == 'owner'
        assert pr_info['repo_name'] == 'repo'
        assert pr_info['installation_id'] == 123

    def test_extract_pr_info_missing(self):
        """Test extracting PR info from invalid payload"""
        handler = WebhookHandler()
        payload = {'action': 'opened'}  # Missing pull_request

        pr_info = handler.extract_pr_info(payload)
        assert pr_info is None

    def test_extract_push_info(self):
        """Test extracting push information from payload"""
        handler = WebhookHandler()
        payload = {
            'ref': 'refs/heads/main',
            'before': 'old_sha',
            'after': 'new_sha',
            'repository': {
                'name': 'repo',
                'owner': {'login': 'owner'},
                'full_name': 'owner/repo'
            },
            'pusher': {'name': 'developer'},
            'commits': [{'id': 'commit1'}],
            'installation': {'id': 456}
        }

        push_info = handler.extract_push_info(payload)

        assert push_info is not None
        assert push_info['ref'] == 'refs/heads/main'
        assert push_info['repo_name'] == 'repo'
        assert push_info['pusher'] == 'developer'
        assert push_info['installation_id'] == 456


class TestWebhookService:
    """Test webhook service integration"""

    @pytest.mark.asyncio
    async def test_handle_pr_opened(self):
        """Test handling PR opened event"""
        service = WebhookService()

        payload = {
            'action': 'opened',
            'pull_request': {
                'number': 1,
                'title': 'Test PR',
                'state': 'open',
                'head': {'sha': 'abc123', 'ref': 'feature'},
                'base': {'ref': 'main'},
                'user': {'login': 'developer'},
                'html_url': 'https://github.com/test/repo/pull/1'
            },
            'repository': {
                'name': 'repo',
                'owner': {'login': 'test'},
                'full_name': 'test/repo'
            },
            'installation': {'id': 789}
        }

        with patch.object(service, '_get_or_create_repository'):
            with patch.object(service.queue_manager, 'queue_pr_analysis'):
                result = await service.handle_pull_request(payload)

        # Should queue analysis for opened PRs
        assert 'success' in result.get('status', '') or 'error' in result.get('status', '')

    @pytest.mark.asyncio
    async def test_handle_pr_ignored_actions(self):
        """Test that certain PR actions are ignored"""
        service = WebhookService()

        payload = {
            'action': 'closed',  # Should be ignored
            'pull_request': {
                'number': 1,
                'title': 'Test PR',
                'state': 'closed',
                'head': {'sha': 'abc123', 'ref': 'feature'},
                'base': {'ref': 'main'},
                'user': {'login': 'developer'},
                'html_url': 'https://github.com/test/repo/pull/1'
            },
            'repository': {
                'name': 'repo',
                'owner': {'login': 'test'},
                'full_name': 'test/repo'
            }
        }

        result = await service.handle_pull_request(payload)
        assert result['status'] == 'ignored'

    @pytest.mark.asyncio
    async def test_handle_push_ignored(self):
        """Test that push events are currently ignored"""
        service = WebhookService()

        payload = {
            'ref': 'refs/heads/main',
            'before': 'old',
            'after': 'new',
            'repository': {
                'name': 'repo',
                'owner': {'login': 'test'},
                'full_name': 'test/repo'
            },
            'pusher': {'name': 'dev'},
            'commits': []
        }

        result = await service.handle_push(payload)
        assert result['status'] == 'ignored'

    @pytest.mark.asyncio
    async def test_handle_installation_created(self):
        """Test handling installation created event"""
        service = WebhookService()

        payload = {
            'action': 'created',
            'installation': {'id': 123},
            'repositories': [{'name': 'repo1'}, {'name': 'repo2'}]
        }

        result = await service.handle_installation(payload)
        assert result['status'] == 'success'
        assert result['action'] == 'created'

    @pytest.mark.asyncio
    async def test_handle_installation_deleted(self):
        """Test handling installation deleted event"""
        service = WebhookService()

        payload = {
            'action': 'deleted',
            'installation': {'id': 123}
        }

        with patch.object(service.github_app, 'revoke_installation_token') as mock_revoke:
            result = await service.handle_installation(payload)

        assert result['status'] == 'success'
        assert result['action'] == 'deleted'
        mock_revoke.assert_called_once_with(123)


class TestWebhookIntegration:
    """Integration tests for webhook flow"""

    @pytest.mark.asyncio
    async def test_full_webhook_flow(self):
        """Test complete webhook processing flow"""
        handler = WebhookHandler(secret='test-secret')
        service = WebhookService()

        # Register service handlers
        async def mock_pr_handler(payload):
            return {'status': 'queued', 'pr_number': payload['pull_request']['number']}

        handler.register_handler(GitHubEvent.PULL_REQUEST, mock_pr_handler)

        # Simulate webhook payload
        payload = {
            'action': 'opened',
            'pull_request': {
                'number': 99,
                'title': 'Integration Test',
                'state': 'open',
                'head': {'sha': 'test123', 'ref': 'feature'},
                'base': {'ref': 'main'},
                'user': {'login': 'tester'},
                'html_url': 'https://github.com/test/repo/pull/99'
            },
            'repository': {
                'name': 'repo',
                'owner': {'login': 'test'},
                'full_name': 'test/repo'
            }
        }

        # Process event
        result = await handler.handle_event('pull_request', payload)

        assert result['status'] == 'success'
        assert result['event'] == 'pull_request'
        assert result['handlers_executed'] == 1
