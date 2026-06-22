"""
Tests for Notification Digest Service
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from src.services.notification_digest_service import NotificationDigestService


class TestNotificationDigestService:
    """Test NotificationDigestService"""

    @pytest.fixture
    def service(self):
        """Create digest service"""
        return NotificationDigestService()

    @pytest.fixture
    def sample_digest_data(self):
        """Sample digest data for testing"""
        return {
            'period': 'daily',
            'start_time': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            'end_time': datetime.now(timezone.utc).isoformat(),
            'user_id': 'user-123',
            'repository_id': 'repo-456',
            'summary': {
                'total_notifications': 10,
                'critical_issues': 2,
                'prs_analyzed': 3,
                'total_issues': 15
            },
            'notifications_by_type': {
                'pr_opened': [
                    {'title': 'PR #1 opened', 'summary': 'New PR'}
                ],
                'critical_issue': [
                    {'title': 'SQL Injection', 'summary': 'In app.py'}
                ]
            },
            'notifications_by_severity': {
                'critical': 2,
                'error': 5,
                'warning': 3
            },
            'top_issues': []
        }

    def test_aggregate_notifications_daily(self, service):
        """Test daily notification aggregation"""
        result = service.aggregate_notifications(
            user_id='user-123',
            period='daily'
        )

        assert result['period'] == 'daily'
        assert result['user_id'] == 'user-123'
        assert 'summary' in result
        assert 'start_time' in result
        assert 'end_time' in result

    def test_aggregate_notifications_weekly(self, service):
        """Test weekly notification aggregation"""
        result = service.aggregate_notifications(
            user_id='user-123',
            period='weekly'
        )

        assert result['period'] == 'weekly'
        # Should cover 7 days
        start = datetime.fromisoformat(result['start_time'])
        end = datetime.fromisoformat(result['end_time'])
        diff = end - start
        assert diff.days >= 6

    def test_aggregate_notifications_with_repository(self, service):
        """Test aggregation with repository filter"""
        result = service.aggregate_notifications(
            user_id='user-123',
            period='daily',
            repository_id='repo-456'
        )

        assert result['repository_id'] == 'repo-456'

    @patch('src.services.notification_digest_service.get_email_service')
    def test_create_email_digest_no_config(self, mock_get_email, service):
        """Test email digest with no configuration"""
        from src.core.database import DatabaseManager

        result = service.create_email_digest(
            user_id='nonexistent',
            period='daily'
        )

        assert result['success'] == False
        assert 'configuration' in result['error'].lower()

    def test_create_slack_digest(self, service, sample_digest_data):
        """Test Slack digest creation"""
        mock_slack = Mock()
        mock_slack.send_message.return_value = {'success': True}

        # Override slack_service and aggregate on the instance
        service.slack_service = mock_slack
        service.aggregate_notifications = Mock(return_value=sample_digest_data)

        result = service.create_slack_digest(
            user_id='user-123',
            period='daily'
        )

        assert result['success'] == True
        assert mock_slack.send_message.called

    def test_create_discord_digest(self, service, sample_digest_data):
        """Test Discord digest creation"""
        mock_discord = Mock()
        mock_discord.send_message.return_value = {'success': True}

        # Override discord_service and aggregate on the instance
        service.discord_service = mock_discord
        service.aggregate_notifications = Mock(return_value=sample_digest_data)

        result = service.create_discord_digest(
            user_id='user-123',
            period='daily'
        )

        assert result['success'] == True
        assert mock_discord.send_message.called

        # Verify embed structure
        call_args = mock_discord.send_message.call_args
        assert 'embeds' in call_args[1]

    def test_should_send_digest_no_previous(self, service):
        """Test should send when no previous digest sent"""
        from src.core.database import EmailConfiguration

        config = EmailConfiguration()
        config.last_digest_sent = None

        result = service._should_send_digest(config, 'daily')
        assert result == True

    def test_should_send_digest_daily_ready(self, service):
        """Test should send daily digest when ready"""
        from src.core.database import EmailConfiguration

        config = EmailConfiguration()
        config.last_digest_sent = datetime.now(timezone.utc) - timedelta(days=2)

        result = service._should_send_digest(config, 'daily')
        assert result == True

    def test_should_send_digest_daily_not_ready(self, service):
        """Test should not send daily digest when not ready"""
        from src.core.database import EmailConfiguration

        config = EmailConfiguration()
        config.last_digest_sent = datetime.now(timezone.utc) - timedelta(hours=12)

        result = service._should_send_digest(config, 'daily')
        assert result == False

    def test_should_send_digest_weekly_ready(self, service):
        """Test should send weekly digest when ready"""
        from src.core.database import EmailConfiguration

        config = EmailConfiguration()
        config.last_digest_sent = datetime.now(timezone.utc) - timedelta(days=8)

        result = service._should_send_digest(config, 'weekly')
        assert result == True

    def test_should_send_digest_weekly_not_ready(self, service):
        """Test should not send weekly digest when not ready"""
        from src.core.database import EmailConfiguration

        config = EmailConfiguration()
        config.last_digest_sent = datetime.now(timezone.utc) - timedelta(days=5)

        result = service._should_send_digest(config, 'weekly')
        assert result == False

    def test_format_notifications_for_email(self, service, sample_digest_data):
        """Test formatting notifications for email"""
        result = service._format_notifications_for_email(sample_digest_data)

        assert isinstance(result, list)
        assert len(result) > 0
        assert 'type' in result[0]
        assert 'title' in result[0]

    def test_format_notifications_for_slack(self, service, sample_digest_data):
        """Test formatting notifications for Slack"""
        result = service._format_notifications_for_slack(sample_digest_data)

        assert isinstance(result, list)
        # Should have summary block
        assert len(result) > 0
        assert result[0]['type'] == 'section'

    def test_format_notifications_for_slack_with_critical(self, service, sample_digest_data):
        """Test Slack formatting with critical issues"""
        sample_digest_data['summary']['critical_issues'] = 5

        result = service._format_notifications_for_slack(sample_digest_data)

        # Should have critical issues section
        assert len(result) > 1

    def test_send_all_digests_empty(self, service):
        """Test sending digests when no configs"""
        result = service.send_all_digests(period='daily')

        assert 'email' in result
        assert 'total_sent' in result
        assert 'total_failed' in result


class TestNotificationDigestEndpoints:
    """Test Notification Digest API endpoints"""

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
            'username': 'digest_test_user',
            'email': 'digest@test.com',
            'password': 'password123'
        })

        response = client.post('/api/auth/login', json={
            'username': 'digest_test_user',
            'password': 'password123'
        })

        return response.cookies.get('session_token')

    @patch('src.workers.notification_worker.queue_notification')
    def test_queue_notification(self, mock_queue, client, user_session):
        """Test queuing notification"""
        mock_task = Mock()
        mock_task.id = 'task-123'
        mock_queue.apply_async.return_value = mock_task

        response = client.post(
            '/api/notifications/queue',
            json={
                'issue': {
                    'type': 'SQL Injection',
                    'severity': 'critical',
                    'file': 'app.py',
                    'line': 10
                }
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'task_id' in data

    def test_queue_notification_missing_issue(self, client, user_session):
        """Test queuing notification without issue"""
        response = client.post(
            '/api/notifications/queue',
            json={},
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400

    @patch('src.workers.notification_worker.process_batch_notifications')
    def test_process_batch(self, mock_batch, client, user_session):
        """Test batch processing"""
        mock_task = Mock()
        mock_task.id = 'batch-task-123'
        mock_batch.apply_async.return_value = mock_task

        response = client.post(
            '/api/notifications/batch',
            json={
                'notifications': [
                    {'issue': {'type': 'Issue 1'}},
                    {'issue': {'type': 'Issue 2'}}
                ],
                'batch_interval_minutes': 30
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert data['batch_size'] == 2

    def test_process_batch_missing_notifications(self, client, user_session):
        """Test batch processing without notifications"""
        response = client.post(
            '/api/notifications/batch',
            json={},
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400

    @patch('src.workers.notification_worker.send_user_digest')
    def test_send_digest(self, mock_send, client, user_session):
        """Test sending digest"""
        mock_task = Mock()
        mock_task.id = 'digest-task-123'
        mock_send.apply_async.return_value = mock_task

        response = client.post(
            '/api/digest/send',
            json={'period': 'daily'},
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert data['period'] == 'daily'

    def test_send_digest_invalid_period(self, client, user_session):
        """Test sending digest with invalid period"""
        response = client.post(
            '/api/digest/send',
            json={'period': 'monthly'},
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400

    def test_preview_digest(self, client, user_session):
        """Test previewing digest"""
        response = client.get(
            '/api/digest/preview?period=daily',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'digest' in data

    def test_preview_digest_invalid_period(self, client, user_session):
        """Test preview with invalid period"""
        response = client.get(
            '/api/digest/preview?period=invalid',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400

    @patch('src.services.notification_digest_service.NotificationDigestService.create_email_digest')
    def test_test_digest_email(self, mock_create, client, user_session):
        """Test sending test email digest"""
        mock_create.return_value = {'success': True}

        response = client.post(
            '/api/digest/test',
            json={
                'channel': 'email',
                'period': 'daily'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert mock_create.called

    def test_test_digest_invalid_channel(self, client, user_session):
        """Test test digest with invalid channel"""
        response = client.post(
            '/api/digest/test',
            json={
                'channel': 'invalid',
                'period': 'daily'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400
