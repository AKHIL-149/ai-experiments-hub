"""
Tests for Notification Worker
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from src.workers.notification_worker import (
    _group_notifications_by_user_and_channel,
    _send_batched_notification,
    _create_batch_email_html
)


class TestNotificationWorkerHelpers:
    """Test notification worker helper functions"""

    def test_group_notifications_by_user_and_channel(self):
        """Test grouping notifications"""
        notifications = [
            {
                'user_id': 'user-1',
                'issue': {'type': 'Issue 1'},
                'channels': [
                    {'type': 'slack', 'config_id': 'slack-1'},
                    {'type': 'email', 'config_id': 'email-1'}
                ]
            },
            {
                'user_id': 'user-1',
                'issue': {'type': 'Issue 2'},
                'channels': [
                    {'type': 'slack', 'config_id': 'slack-1'}
                ]
            },
            {
                'user_id': 'user-2',
                'issue': {'type': 'Issue 3'},
                'channels': [
                    {'type': 'email', 'config_id': 'email-2'}
                ]
            }
        ]

        result = _group_notifications_by_user_and_channel(notifications)

        # Should have 3 batches: user-1/slack, user-1/email, user-2/email
        assert len(result) == 3
        assert ('user-1', 'slack', 'slack-1') in result
        assert ('user-1', 'email', 'email-1') in result
        assert ('user-2', 'email', 'email-2') in result

        # user-1/slack should have 2 notifications
        assert len(result[('user-1', 'slack', 'slack-1')]) == 2

    def test_group_notifications_empty(self):
        """Test grouping empty list"""
        result = _group_notifications_by_user_and_channel([])
        assert len(result) == 0

    def test_create_batch_email_html(self):
        """Test creating batch email HTML"""
        notifications = [
            {'title': 'Issue 1', 'summary': 'Summary 1'},
            {'title': 'Issue 2', 'summary': 'Summary 2'}
        ]

        html = _create_batch_email_html(notifications)

        assert 'Issue 1' in html
        assert 'Issue 2' in html
        assert 'Summary 1' in html
        assert '2 notifications' in html

    def test_create_batch_email_html_empty(self):
        """Test creating HTML with empty list"""
        html = _create_batch_email_html([])
        assert '0 notifications' in html


class TestBatchedNotificationSending:
    """Test batched notification sending"""

    @patch('src.services.slack_service.SlackService')
    @patch('src.core.database.DatabaseManager')
    def test_send_batched_slack(self, mock_db_manager, mock_slack_service):
        """Test sending batched Slack notification"""
        from src.core.database import SlackConfiguration

        # Mock database
        mock_db = MagicMock()
        mock_config = SlackConfiguration()
        mock_config.id = 'slack-1'
        mock_config.webhook_url = 'https://hooks.slack.com/test'
        mock_config.channel = '#test'

        mock_db.query().filter().first.return_value = mock_config
        mock_db_manager.return_value.get_session.return_value.__enter__.return_value = mock_db

        # Mock Slack service
        mock_slack = Mock()
        mock_slack.send_message.return_value = {'success': True}
        mock_slack_service.return_value = mock_slack

        notifications = [
            {'issue': {'type': 'Issue 1', 'file': 'app.py', 'line': 10}},
            {'issue': {'type': 'Issue 2', 'file': 'app.py', 'line': 20}}
        ]

        result = _send_batched_notification(
            user_id='user-1',
            channel_type='slack',
            config_id='slack-1',
            notifications=notifications
        )

        assert result['success'] == True
        assert mock_slack.send_message.called

    @patch('src.services.email_service.EmailService')
    @patch('src.core.database.DatabaseManager')
    def test_send_batched_email(self, mock_db_manager, mock_email_service):
        """Test sending batched email notification"""
        from src.core.database import EmailConfiguration

        # Mock database
        mock_db = MagicMock()
        mock_config = EmailConfiguration()
        mock_config.id = 'email-1'
        mock_config.smtp_host = 'smtp.test.com'
        mock_config.smtp_port = 587
        mock_config.smtp_username = 'test@test.com'
        mock_config.smtp_password = 'password'
        mock_config.smtp_use_tls = True
        mock_config.from_email = 'sender@test.com'
        mock_config.to_email = 'recipient@test.com'

        mock_db.query().filter().first.return_value = mock_config
        mock_db_manager.return_value.get_session.return_value.__enter__.return_value = mock_db

        # Mock email service
        mock_email = Mock()
        mock_email.send_email.return_value = {'success': True}
        mock_email_service.return_value = mock_email

        notifications = [
            {'issue': {'type': 'Issue 1', 'file': 'app.py', 'message': 'Test 1'}},
            {'issue': {'type': 'Issue 2', 'file': 'app.py', 'message': 'Test 2'}}
        ]

        result = _send_batched_notification(
            user_id='user-1',
            channel_type='email',
            config_id='email-1',
            notifications=notifications
        )

        assert result['success'] == True
        assert mock_email.send_email.called

    @patch('src.services.discord_service.DiscordService')
    @patch('src.core.database.DatabaseManager')
    def test_send_batched_discord(self, mock_db_manager, mock_discord_service):
        """Test sending batched Discord notification"""
        from src.core.database import DiscordConfiguration

        # Mock database
        mock_db = MagicMock()
        mock_config = DiscordConfiguration()
        mock_config.id = 'discord-1'
        mock_config.webhook_url = 'https://discord.com/api/webhooks/test'

        mock_db.query().filter().first.return_value = mock_config
        mock_db_manager.return_value.get_session.return_value.__enter__.return_value = mock_db

        # Mock Discord service
        mock_discord = Mock()
        mock_discord.send_message.return_value = {'success': True}
        mock_discord_service.return_value = mock_discord

        notifications = [
            {'issue': {'type': 'Issue 1', 'file': 'app.py', 'line': 10}},
            {'issue': {'type': 'Issue 2', 'file': 'app.py', 'line': 20}}
        ]

        result = _send_batched_notification(
            user_id='user-1',
            channel_type='discord',
            config_id='discord-1',
            notifications=notifications
        )

        assert result['success'] == True
        assert mock_discord.send_message.called

    @patch('src.workers.notification_worker.DatabaseManager')
    def test_send_batched_config_not_found(self, mock_db_manager):
        """Test sending batched notification when config not found"""
        # Mock database with no config
        mock_db = MagicMock()
        mock_db.query().filter().first.return_value = None
        mock_db_manager.return_value.get_session.return_value.__enter__.return_value = mock_db

        notifications = [
            {'issue': {'type': 'Issue 1'}}
        ]

        result = _send_batched_notification(
            user_id='user-1',
            channel_type='slack',
            config_id='nonexistent',
            notifications=notifications
        )

        assert result['success'] == False
        assert 'not found' in result['error'].lower()

    @patch('src.workers.notification_worker.DatabaseManager')
    def test_send_batched_unknown_channel(self, mock_db_manager):
        """Test sending batched notification with unknown channel type"""
        mock_db = MagicMock()
        mock_db_manager.return_value.get_session.return_value.__enter__.return_value = mock_db

        notifications = [
            {'issue': {'type': 'Issue 1'}}
        ]

        result = _send_batched_notification(
            user_id='user-1',
            channel_type='unknown',
            config_id='config-1',
            notifications=notifications
        )

        assert result['success'] == False
        assert 'Unknown channel type' in result['error']

    @patch('src.services.discord_service.DiscordService')
    @patch('src.core.database.DatabaseManager')
    def test_send_batched_discord_with_overflow(self, mock_db_manager, mock_discord_service):
        """Test batched Discord with more than 10 notifications"""
        from src.core.database import DiscordConfiguration

        # Mock database
        mock_db = MagicMock()
        mock_config = DiscordConfiguration()
        mock_config.id = 'discord-1'
        mock_config.webhook_url = 'https://discord.com/api/webhooks/test'

        mock_db.query().filter().first.return_value = mock_config
        mock_db_manager.return_value.get_session.return_value.__enter__.return_value = mock_db

        # Mock Discord service
        mock_discord = Mock()
        mock_discord.send_message.return_value = {'success': True}
        mock_discord_service.return_value = mock_discord

        # Create 15 notifications
        notifications = [
            {'issue': {'type': f'Issue {i}', 'file': 'app.py', 'line': i}}
            for i in range(15)
        ]

        result = _send_batched_notification(
            user_id='user-1',
            channel_type='discord',
            config_id='discord-1',
            notifications=notifications
        )

        assert result['success'] == True

        # Check embed structure
        call_args = mock_discord.send_message.call_args
        embeds = call_args[1]['embeds']
        assert len(embeds) > 0

        # Should have "More Items" field
        fields = embeds[0]['fields']
        more_items_field = [f for f in fields if f['name'] == 'More Items']
        assert len(more_items_field) > 0


class TestCeleryTasks:
    """Test Celery task functions"""

    @patch('src.workers.notification_worker.get_rules_engine')
    @patch('src.workers.notification_worker.process_batch_notifications')
    def test_queue_notification_task(self, mock_batch_task, mock_get_engine):
        """Test queue_notification task"""
        from src.workers.notification_worker import queue_notification

        # Mock rules engine
        mock_engine = Mock()
        mock_engine.evaluate_issue.return_value = [
            {'batch': False, 'channels': [{'type': 'slack'}]},
            {'batch': True, 'batch_interval': 60, 'channels': [{'type': 'email'}]}
        ]
        mock_engine.execute_action.return_value = [{'success': True}]
        mock_get_engine.return_value = mock_engine

        # Mock batch task
        mock_task = Mock()
        mock_batch_task.apply_async.return_value = mock_task

        issue = {'type': 'Test Issue', 'severity': 'critical'}
        result = queue_notification(issue, None, 'user-1', None, None)

        assert result['success'] == True
        assert result['immediate_count'] == 1
        assert result['batched_count'] == 1
        assert mock_batch_task.apply_async.called

    @patch('src.workers.notification_worker.get_digest_service')
    def test_send_daily_digests_task(self, mock_get_service):
        """Test send_daily_digests task"""
        from src.workers.notification_worker import send_daily_digests

        # Mock digest service
        mock_service = Mock()
        mock_service.send_all_digests.return_value = {
            'total_sent': 5,
            'total_failed': 0,
            'email': []
        }
        mock_get_service.return_value = mock_service

        result = send_daily_digests()

        assert result['total_sent'] == 5
        assert mock_service.send_all_digests.called
        call_args = mock_service.send_all_digests.call_args
        assert call_args[1]['period'] == 'daily'

    @patch('src.workers.notification_worker.get_digest_service')
    def test_send_weekly_digests_task(self, mock_get_service):
        """Test send_weekly_digests task"""
        from src.workers.notification_worker import send_weekly_digests

        # Mock digest service
        mock_service = Mock()
        mock_service.send_all_digests.return_value = {
            'total_sent': 3,
            'total_failed': 1,
            'email': []
        }
        mock_get_service.return_value = mock_service

        result = send_weekly_digests()

        assert result['total_sent'] == 3
        assert mock_service.send_all_digests.called
        call_args = mock_service.send_all_digests.call_args
        assert call_args[1]['period'] == 'weekly'

    @patch('src.workers.notification_worker.get_digest_service')
    def test_send_user_digest_task(self, mock_get_service):
        """Test send_user_digest task"""
        from src.workers.notification_worker import send_user_digest

        # Mock digest service
        mock_service = Mock()
        mock_service.create_email_digest.return_value = {'success': True}
        mock_get_service.return_value = mock_service

        result = send_user_digest('user-1', 'daily', 'repo-1')

        assert result['success'] == True
        assert mock_service.create_email_digest.called

    @patch('src.workers.notification_worker._send_batched_notification')
    @patch('src.workers.notification_worker._group_notifications_by_user_and_channel')
    def test_process_batch_notifications_task(self, mock_group, mock_send):
        """Test process_batch_notifications task"""
        from src.workers.notification_worker import process_batch_notifications

        # Mock grouping
        mock_group.return_value = {
            ('user-1', 'slack', 'slack-1'): [
                {'issue': {'type': 'Issue 1'}},
                {'issue': {'type': 'Issue 2'}}
            ]
        }

        # Mock sending
        mock_send.return_value = {'success': True}

        notifications = [
            {'issue': {'type': 'Issue 1'}},
            {'issue': {'type': 'Issue 2'}}
        ]

        result = process_batch_notifications(notifications, 60)

        assert result['total_batches'] == 1
        assert result['successful'] == 1
        assert result['failed'] == 0
        assert mock_send.called

    @patch('src.workers.notification_worker._send_batched_notification')
    @patch('src.workers.notification_worker._group_notifications_by_user_and_channel')
    def test_process_batch_notifications_with_failure(self, mock_group, mock_send):
        """Test batch processing with failure"""
        from src.workers.notification_worker import process_batch_notifications

        # Mock grouping
        mock_group.return_value = {
            ('user-1', 'slack', 'slack-1'): [{'issue': {'type': 'Issue 1'}}],
            ('user-2', 'email', 'email-1'): [{'issue': {'type': 'Issue 2'}}]
        }

        # Mock sending - first succeeds, second fails
        mock_send.side_effect = [
            {'success': True},
            {'success': False, 'error': 'Failed to send'}
        ]

        notifications = [
            {'issue': {'type': 'Issue 1'}},
            {'issue': {'type': 'Issue 2'}}
        ]

        result = process_batch_notifications(notifications, 60)

        assert result['total_batches'] == 2
        assert result['successful'] == 1
        assert result['failed'] == 1
