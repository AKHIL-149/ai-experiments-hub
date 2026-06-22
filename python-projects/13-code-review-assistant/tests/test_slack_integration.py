"""
Tests for Slack Integration
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

from src.services.slack_service import SlackService, SlackNotificationType


class TestSlackService:
    """Test Slack service"""

    def test_is_configured_with_webhook(self):
        """Test that service is configured when webhook URL is provided"""
        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        assert service.is_configured() == True

    def test_is_configured_without_webhook(self):
        """Test that service is not configured without webhook URL"""
        service = SlackService(webhook_url='')
        assert service.is_configured() == False

    def test_send_message_not_configured(self):
        """Test sending message when not configured"""
        service = SlackService(webhook_url='')
        result = service.send_message('Test')

        assert result['success'] == False
        assert 'not configured' in result['error']

    @patch('requests.post')
    def test_send_message_success(self, mock_post):
        """Test successful message sending"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        result = service.send_message('Test message')

        assert result['success'] == True
        assert mock_post.called
        assert mock_post.call_args[1]['json']['text'] == 'Test message'

    @patch('requests.post')
    def test_send_message_with_blocks(self, mock_post):
        """Test sending message with blocks"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        blocks = [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': 'Test'}}]
        result = service.send_message('Test', blocks=blocks)

        assert result['success'] == True
        assert mock_post.call_args[1]['json']['blocks'] == blocks

    @patch('requests.post')
    def test_send_message_with_channel(self, mock_post):
        """Test sending message to specific channel"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        result = service.send_message('Test', channel='#alerts')

        assert result['success'] == True
        assert mock_post.call_args[1]['json']['channel'] == '#alerts'

    @patch('requests.post')
    def test_send_message_with_thread(self, mock_post):
        """Test sending message as thread reply"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        result = service.send_message('Test', thread_ts='1234567890.123456')

        assert result['success'] == True
        assert mock_post.call_args[1]['json']['thread_ts'] == '1234567890.123456'

    @patch('requests.post')
    def test_send_message_http_error(self, mock_post):
        """Test handling HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Not found'
        mock_post.return_value = mock_response

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        result = service.send_message('Test')

        assert result['success'] == False
        assert '404' in result['error']

    @patch('requests.post')
    def test_send_message_request_exception(self, mock_post):
        """Test handling request exception"""
        mock_post.side_effect = requests.RequestException('Connection error')

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        result = service.send_message('Test')

        assert result['success'] == False
        assert 'Connection error' in result['error']

    @patch('requests.post')
    def test_notify_pr_analysis_complete_success(self, mock_post):
        """Test PR analysis complete notification"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        result = service.notify_pr_analysis_complete(
            pr_number=42,
            repository='test/repo',
            issues_count=5,
            critical_count=1,
            pr_url='https://github.com/test/repo/pull/42',
            analysis_url='http://localhost:8000/analysis/123'
        )

        assert result['success'] == True
        assert mock_post.called

        # Check payload structure
        payload = mock_post.call_args[1]['json']
        assert 'blocks' in payload
        assert len(payload['blocks']) > 0

    @patch('requests.post')
    def test_notify_pr_analysis_complete_with_thread(self, mock_post):
        """Test PR analysis notification with thread reply"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        result = service.notify_pr_analysis_complete(
            pr_number=42,
            repository='test/repo',
            issues_count=0,
            critical_count=0,
            pr_url='https://github.com/test/repo/pull/42',
            analysis_url='http://localhost:8000/analysis/123',
            thread_ts='1234567890.123456'
        )

        assert result['success'] == True
        assert mock_post.call_args[1]['json']['thread_ts'] == '1234567890.123456'

    @patch('requests.post')
    def test_notify_critical_issue(self, mock_post):
        """Test critical issue notification"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        result = service.notify_critical_issue(
            issue_type='SQL Injection',
            severity='critical',
            file_path='app/models/user.py',
            line_number=42,
            description='Potential SQL injection vulnerability',
            pr_number=123,
            pr_url='https://github.com/test/repo/pull/123'
        )

        assert result['success'] == True
        payload = mock_post.call_args[1]['json']
        assert 'blocks' in payload
        assert 'SQL Injection' in payload['text']

    @patch('requests.post')
    def test_notify_analysis_failed(self, mock_post):
        """Test analysis failed notification"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        result = service.notify_analysis_failed(
            pr_number=42,
            repository='test/repo',
            error_message='Failed to parse code',
            pr_url='https://github.com/test/repo/pull/42'
        )

        assert result['success'] == True
        payload = mock_post.call_args[1]['json']
        assert 'blocks' in payload
        assert 'failed' in payload['text'].lower()

    @patch('requests.post')
    def test_notify_pr_opened(self, mock_post):
        """Test PR opened notification"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        service = SlackService(webhook_url='https://hooks.slack.com/services/test')
        result = service.notify_pr_opened(
            pr_number=42,
            repository='test/repo',
            title='Add new feature',
            author='testuser',
            pr_url='https://github.com/test/repo/pull/42',
            auto_analyze=True
        )

        assert result['success'] == True
        payload = mock_post.call_args[1]['json']
        assert 'blocks' in payload
        assert 'New Pull Request' in payload['blocks'][0]['text']['text']

    def test_format_issue_summary(self):
        """Test formatting issue summary"""
        service = SlackService(webhook_url='https://hooks.slack.com/services/test')

        issues = [
            {
                'type': 'SQL Injection',
                'severity': 'critical',
                'file': 'app.py',
                'line': 10,
                'message': 'Potential SQL injection'
            },
            {
                'type': 'Hardcoded Secret',
                'severity': 'error',
                'file': 'config.py',
                'line': 5,
                'message': 'API key in source code'
            }
        ]

        blocks = service.format_issue_summary(issues, max_issues=5)

        assert len(blocks) == 2  # One block per issue
        assert blocks[0]['type'] == 'section'
        assert 'SQL Injection' in blocks[0]['text']['text']

    def test_format_issue_summary_with_overflow(self):
        """Test formatting issue summary with more issues than max"""
        service = SlackService(webhook_url='https://hooks.slack.com/services/test')

        issues = [
            {'type': f'Issue {i}', 'severity': 'info', 'file': 'test.py', 'line': i, 'message': f'Message {i}'}
            for i in range(10)
        ]

        blocks = service.format_issue_summary(issues, max_issues=3)

        assert len(blocks) == 4  # 3 issues + 1 overflow message
        assert blocks[-1]['type'] == 'context'
        assert '7 more issues' in blocks[-1]['elements'][0]['text']


class TestSlackEndpoints:
    """Test Slack API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from server import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    @pytest.fixture
    def user_session(self, client):
        """Create user session"""
        response = client.post('/api/auth/register', json={
            'username': 'slack_test_user',
            'email': 'slack@test.com',
            'password': 'password123'
        })

        response = client.post('/api/auth/login', json={
            'username': 'slack_test_user',
            'password': 'password123'
        })

        return response.cookies.get('session_token')

    def test_get_slack_config_empty(self, client, user_session):
        """Test getting Slack config endpoint"""
        response = client.get(
            '/api/slack/config',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'configurations' in data
        assert isinstance(data['configurations'], list)

    def test_create_slack_config(self, client, user_session):
        """Test creating Slack configuration"""
        response = client.post(
            '/api/slack/config',
            json={
                'webhook_url': 'https://hooks.slack.com/services/test',
                'channel': '#alerts',
                'username': 'Test Bot',
                'enabled': True
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'configuration' in data
        assert data['configuration']['channel'] == '#alerts'

    def test_create_slack_config_missing_webhook(self, client, user_session):
        """Test creating config without webhook URL"""
        response = client.post(
            '/api/slack/config',
            json={'channel': '#alerts'},
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400

    def test_update_slack_config(self, client, user_session):
        """Test updating Slack configuration"""
        # Create config
        create_response = client.post(
            '/api/slack/config',
            json={
                'webhook_url': 'https://hooks.slack.com/services/test',
                'channel': '#alerts'
            },
            cookies={'session_token': user_session}
        )

        config_id = create_response.json()['configuration']['id']

        # Update it
        response = client.post(
            '/api/slack/config',
            json={
                'id': config_id,
                'webhook_url': 'https://hooks.slack.com/services/updated',
                'channel': '#notifications'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['configuration']['channel'] == '#notifications'

    def test_delete_slack_config(self, client, user_session):
        """Test deleting Slack configuration"""
        # Get initial count
        initial_response = client.get(
            '/api/slack/config',
            cookies={'session_token': user_session}
        )
        initial_count = len(initial_response.json()['configurations'])

        # Create config
        create_response = client.post(
            '/api/slack/config',
            json={
                'webhook_url': 'https://hooks.slack.com/services/test-delete'
            },
            cookies={'session_token': user_session}
        )

        config_id = create_response.json()['configuration']['id']

        # Delete it
        response = client.delete(
            f'/api/slack/config/{config_id}',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert response.json()['success'] == True

        # Verify count decreased
        get_response = client.get(
            '/api/slack/config',
            cookies={'session_token': user_session}
        )

        assert len(get_response.json()['configurations']) == initial_count

    def test_delete_nonexistent_config(self, client, user_session):
        """Test deleting non-existent configuration"""
        response = client.delete(
            '/api/slack/config/nonexistent-id',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 404

    @patch('requests.post')
    def test_slack_test_endpoint(self, mock_post, client, user_session):
        """Test Slack connection test endpoint"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_post.return_value = mock_response

        response = client.post(
            '/api/slack/test',
            json={
                'webhook_url': 'https://hooks.slack.com/services/test',
                'channel': '#test'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True

    def test_slack_test_endpoint_missing_webhook(self, client, user_session):
        """Test Slack test without webhook URL"""
        response = client.post(
            '/api/slack/test',
            json={},
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400
