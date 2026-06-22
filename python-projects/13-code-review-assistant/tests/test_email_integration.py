"""
Tests for Email Integration
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import smtplib

from src.services.email_service import EmailService, EmailNotificationType


class TestEmailService:
    """Test Email service"""

    def test_is_configured_with_credentials(self):
        """Test that service is configured when credentials are provided"""
        service = EmailService(
            smtp_host='smtp.test.com',
            smtp_username='test@test.com',
            smtp_password='password'
        )
        assert service.is_configured() == True

    def test_is_configured_without_credentials(self):
        """Test that service is not configured without credentials"""
        service = EmailService(smtp_host='', smtp_username='', smtp_password='')
        assert service.is_configured() == False

    def test_send_email_not_configured(self):
        """Test sending email when not configured"""
        service = EmailService(smtp_host='', smtp_username='', smtp_password='')
        result = service.send_email(
            to_email='test@test.com',
            subject='Test',
            html_body='<p>Test</p>'
        )

        assert result['success'] == False
        assert 'not configured' in result['error']

    @patch('smtplib.SMTP')
    def test_send_email_success(self, mock_smtp):
        """Test successful email sending"""
        mock_server = Mock()
        mock_smtp.return_value = mock_server

        service = EmailService(
            smtp_host='smtp.test.com',
            smtp_port=587,
            smtp_username='test@test.com',
            smtp_password='password',
            from_email='sender@test.com'
        )

        result = service.send_email(
            to_email='recipient@test.com',
            subject='Test Email',
            html_body='<p>Test content</p>',
            text_body='Test content'
        )

        assert result['success'] == True
        assert mock_server.starttls.called
        assert mock_server.login.called
        assert mock_server.send_message.called
        assert mock_server.quit.called

    @patch('smtplib.SMTP')
    def test_send_email_with_reply_to(self, mock_smtp):
        """Test sending email with reply-to"""
        mock_server = Mock()
        mock_smtp.return_value = mock_server

        service = EmailService(
            smtp_host='smtp.test.com',
            smtp_username='test@test.com',
            smtp_password='password',
            from_email='sender@test.com'
        )

        result = service.send_email(
            to_email='recipient@test.com',
            subject='Test',
            html_body='<p>Test</p>',
            reply_to='reply@test.com'
        )

        assert result['success'] == True

    @patch('smtplib.SMTP')
    def test_send_email_smtp_exception(self, mock_smtp):
        """Test handling SMTP exception"""
        mock_smtp.side_effect = smtplib.SMTPException('SMTP error')

        service = EmailService(
            smtp_host='smtp.test.com',
            smtp_username='test@test.com',
            smtp_password='password',
            from_email='sender@test.com'
        )

        result = service.send_email(
            to_email='recipient@test.com',
            subject='Test',
            html_body='<p>Test</p>'
        )

        assert result['success'] == False
        assert 'SMTP error' in result['error']

    @patch('smtplib.SMTP')
    def test_notify_pr_analysis_complete_success(self, mock_smtp):
        """Test PR analysis complete notification"""
        mock_server = Mock()
        mock_smtp.return_value = mock_server

        service = EmailService(
            smtp_host='smtp.test.com',
            smtp_username='test@test.com',
            smtp_password='password',
            from_email='sender@test.com'
        )

        result = service.notify_pr_analysis_complete(
            to_email='user@test.com',
            pr_number=42,
            repository='test/repo',
            issues_count=5,
            critical_count=1,
            pr_url='https://github.com/test/repo/pull/42',
            analysis_url='http://localhost:8000/analysis/123'
        )

        assert result['success'] == True
        assert mock_server.send_message.called

    @patch('smtplib.SMTP')
    def test_notify_pr_analysis_complete_all_clear(self, mock_smtp):
        """Test PR analysis notification with no issues"""
        mock_server = Mock()
        mock_smtp.return_value = mock_server

        service = EmailService(
            smtp_host='smtp.test.com',
            smtp_username='test@test.com',
            smtp_password='password',
            from_email='sender@test.com'
        )

        result = service.notify_pr_analysis_complete(
            to_email='user@test.com',
            pr_number=42,
            repository='test/repo',
            issues_count=0,
            critical_count=0,
            pr_url='https://github.com/test/repo/pull/42',
            analysis_url='http://localhost:8000/analysis/123'
        )

        assert result['success'] == True

    @patch('smtplib.SMTP')
    def test_notify_critical_issue(self, mock_smtp):
        """Test critical issue notification"""
        mock_server = Mock()
        mock_smtp.return_value = mock_server

        service = EmailService(
            smtp_host='smtp.test.com',
            smtp_username='test@test.com',
            smtp_password='password',
            from_email='sender@test.com'
        )

        result = service.notify_critical_issue(
            to_email='user@test.com',
            issue_type='SQL Injection',
            severity='critical',
            file_path='app/models/user.py',
            line_number=42,
            description='Potential SQL injection vulnerability',
            pr_number=123,
            pr_url='https://github.com/test/repo/pull/123'
        )

        assert result['success'] == True
        assert mock_server.send_message.called

    @patch('smtplib.SMTP')
    def test_notify_analysis_failed(self, mock_smtp):
        """Test analysis failed notification"""
        mock_server = Mock()
        mock_smtp.return_value = mock_server

        service = EmailService(
            smtp_host='smtp.test.com',
            smtp_username='test@test.com',
            smtp_password='password',
            from_email='sender@test.com'
        )

        result = service.notify_analysis_failed(
            to_email='user@test.com',
            pr_number=42,
            repository='test/repo',
            error_message='Failed to parse code',
            pr_url='https://github.com/test/repo/pull/42'
        )

        assert result['success'] == True
        assert mock_server.send_message.called

    @patch('smtplib.SMTP')
    def test_notify_pr_opened(self, mock_smtp):
        """Test PR opened notification"""
        mock_server = Mock()
        mock_smtp.return_value = mock_server

        service = EmailService(
            smtp_host='smtp.test.com',
            smtp_username='test@test.com',
            smtp_password='password',
            from_email='sender@test.com'
        )

        result = service.notify_pr_opened(
            to_email='user@test.com',
            pr_number=42,
            repository='test/repo',
            title='Add new feature',
            author='testuser',
            pr_url='https://github.com/test/repo/pull/42',
            auto_analyze=True
        )

        assert result['success'] == True
        assert mock_server.send_message.called

    @patch('smtplib.SMTP')
    def test_send_digest(self, mock_smtp):
        """Test digest email"""
        mock_server = Mock()
        mock_smtp.return_value = mock_server

        service = EmailService(
            smtp_host='smtp.test.com',
            smtp_username='test@test.com',
            smtp_password='password',
            from_email='sender@test.com'
        )

        notifications = [
            {
                'type': 'pr_opened',
                'title': 'PR #42 opened',
                'summary': 'New PR in test/repo'
            },
            {
                'type': 'pr_analysis_complete',
                'title': 'PR #42 analysis complete',
                'summary': '5 issues found'
            }
        ]

        result = service.send_digest(
            to_email='user@test.com',
            notifications=notifications,
            period='daily'
        )

        assert result['success'] == True
        assert mock_server.send_message.called


class TestEmailEndpoints:
    """Test Email API endpoints"""

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
            'username': 'email_test_user',
            'email': 'email@test.com',
            'password': 'password123'
        })

        response = client.post('/api/auth/login', json={
            'username': 'email_test_user',
            'password': 'password123'
        })

        return response.cookies.get('session_token')

    def test_get_email_config_empty(self, client, user_session):
        """Test getting Email config endpoint"""
        response = client.get(
            '/api/email/config',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'configurations' in data
        assert isinstance(data['configurations'], list)

    def test_create_email_config(self, client, user_session):
        """Test creating Email configuration"""
        response = client.post(
            '/api/email/config',
            json={
                'smtp_host': 'smtp.test.com',
                'smtp_port': 587,
                'smtp_username': 'test@test.com',
                'smtp_password': 'password',
                'from_email': 'sender@test.com',
                'to_email': 'recipient@test.com',
                'enabled': True
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'configuration' in data
        assert data['configuration']['from_email'] == 'sender@test.com'
        assert data['configuration']['to_email'] == 'recipient@test.com'

    def test_create_email_config_missing_fields(self, client, user_session):
        """Test creating config without required fields"""
        response = client.post(
            '/api/email/config',
            json={'smtp_host': 'smtp.test.com'},
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400

    def test_update_email_config(self, client, user_session):
        """Test updating Email configuration"""
        # Create config
        create_response = client.post(
            '/api/email/config',
            json={
                'smtp_host': 'smtp.test.com',
                'from_email': 'sender@test.com',
                'to_email': 'recipient@test.com'
            },
            cookies={'session_token': user_session}
        )

        config_id = create_response.json()['configuration']['id']

        # Update it
        response = client.post(
            '/api/email/config',
            json={
                'id': config_id,
                'smtp_host': 'smtp.updated.com',
                'from_email': 'updated@test.com',
                'to_email': 'recipient@test.com'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['configuration']['smtp_host'] == 'smtp.updated.com'

    def test_delete_email_config(self, client, user_session):
        """Test deleting Email configuration"""
        # Get initial count
        initial_response = client.get(
            '/api/email/config',
            cookies={'session_token': user_session}
        )
        initial_count = len(initial_response.json()['configurations'])

        # Create config
        create_response = client.post(
            '/api/email/config',
            json={
                'from_email': 'delete@test.com',
                'to_email': 'recipient@test.com'
            },
            cookies={'session_token': user_session}
        )

        config_id = create_response.json()['configuration']['id']

        # Delete it
        response = client.delete(
            f'/api/email/config/{config_id}',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert response.json()['success'] == True

        # Verify count
        get_response = client.get(
            '/api/email/config',
            cookies={'session_token': user_session}
        )

        assert len(get_response.json()['configurations']) == initial_count

    def test_delete_nonexistent_config(self, client, user_session):
        """Test deleting non-existent configuration"""
        response = client.delete(
            '/api/email/config/nonexistent-id',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 404

    @patch('smtplib.SMTP')
    def test_email_test_endpoint(self, mock_smtp, client, user_session):
        """Test Email connection test endpoint"""
        mock_server = Mock()
        mock_smtp.return_value = mock_server

        response = client.post(
            '/api/email/test',
            json={
                'smtp_host': 'smtp.test.com',
                'smtp_port': 587,
                'smtp_username': 'test@test.com',
                'smtp_password': 'password',
                'from_email': 'sender@test.com',
                'to_email': 'recipient@test.com'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True

    def test_email_test_endpoint_missing_fields(self, client, user_session):
        """Test Email test without required fields"""
        response = client.post(
            '/api/email/test',
            json={
                'smtp_host': 'smtp.test.com'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400
