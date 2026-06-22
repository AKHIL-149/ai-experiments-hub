"""
Tests for Notification UI Pages
"""

import pytest
from fastapi.testclient import TestClient


class TestNotificationUIPages:
    """Test notification UI page rendering"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from server import app
        return TestClient(app)

    @pytest.fixture
    def user_session(self, client):
        """Create user session"""
        response = client.post('/api/auth/register', json={
            'username': 'ui_test_user',
            'email': 'ui@test.com',
            'password': 'password123'
        })

        response = client.post('/api/auth/login', json={
            'username': 'ui_test_user',
            'password': 'password123'
        })

        return response.cookies.get('session_token')

    def test_notifications_page_requires_auth(self, client):
        """Test notifications page redirects when not authenticated"""
        response = client.get('/notifications', follow_redirects=False)
        assert response.status_code == 307  # Redirect
        assert '/login' in response.headers['location']

    def test_notifications_page_renders(self, client, user_session):
        """Test notifications page renders for authenticated user"""
        response = client.get(
            '/notifications',
            cookies={'session_token': user_session},
            follow_redirects=True
        )

        assert response.status_code == 200
        assert b'Notification Center' in response.content
        assert b'notification-manager.js' in response.content

    def test_notification_preferences_requires_auth(self, client):
        """Test preferences page redirects when not authenticated"""
        response = client.get('/notifications/preferences', follow_redirects=False)
        assert response.status_code == 307
        assert '/login' in response.headers['location']

    def test_notification_preferences_renders(self, client, user_session):
        """Test preferences page renders for authenticated user"""
        response = client.get(
            '/notifications/preferences',
            cookies={'session_token': user_session},
            follow_redirects=True
        )

        assert response.status_code == 200
        assert b'Notification Preferences' in response.content
        assert b'Notification Channels' in response.content
        assert b'Notification Rules' in response.content
        assert b'Quiet Hours' in response.content

    def test_notifications_css_loaded(self, client, user_session):
        """Test that notifications CSS is properly referenced"""
        response = client.get(
            '/notifications',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'notifications.css' in response.content

    def test_notification_filters_present(self, client, user_session):
        """Test that notification filters are present"""
        response = client.get(
            '/notifications',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'filter-tab' in response.content
        assert b'All' in response.content
        assert b'Unread' in response.content
        assert b'Critical' in response.content

    def test_channel_cards_present(self, client, user_session):
        """Test that channel configuration cards are present"""
        response = client.get(
            '/notifications/preferences',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'Email' in response.content
        assert b'Slack' in response.content
        assert b'Discord' in response.content
        assert b'channel-card' in response.content

    def test_rules_section_present(self, client, user_session):
        """Test that rules section is present"""
        response = client.get(
            '/notifications/preferences',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'Notification Rules' in response.content
        assert b'New Rule' in response.content
        assert b'rules-list' in response.content

    def test_severity_filters_present(self, client, user_session):
        """Test that severity filters are present"""
        response = client.get(
            '/notifications/preferences',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'Severity Filters' in response.content
        assert b'Critical' in response.content
        assert b'Error' in response.content
        assert b'Warning' in response.content
        assert b'Info' in response.content

    def test_quiet_hours_section_present(self, client, user_session):
        """Test that quiet hours section is present"""
        response = client.get(
            '/notifications/preferences',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'Quiet Hours' in response.content
        assert b'quiet-hours-enabled' in response.content
        assert b'quiet-start' in response.content
        assert b'quiet-end' in response.content

    def test_advanced_settings_present(self, client, user_session):
        """Test that advanced settings are present"""
        response = client.get(
            '/notifications/preferences',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'Advanced Settings' in response.content
        assert b'Batch Notifications' in response.content
        assert b'Rate Limiting' in response.content

    def test_rule_modal_present(self, client, user_session):
        """Test that rule modal is present"""
        response = client.get(
            '/notifications/preferences',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'rule-modal' in response.content
        assert b'rule-form' in response.content

    def test_notification_template_present(self, client, user_session):
        """Test that notification template is present"""
        response = client.get(
            '/notifications',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'notification-template' in response.content
        assert b'notification-item' in response.content

    def test_empty_state_present(self, client, user_session):
        """Test that empty state is present"""
        response = client.get(
            '/notifications',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'empty-state' in response.content
        assert b'No notifications' in response.content

    def test_save_button_present(self, client, user_session):
        """Test that save button is present on preferences page"""
        response = client.get(
            '/notifications/preferences',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'Save Changes' in response.content
        assert b'savePreferences' in response.content


class TestNotificationUINavigation:
    """Test notification UI navigation"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from server import app
        return TestClient(app)

    @pytest.fixture
    def user_session(self, client):
        """Create user session"""
        response = client.post('/api/auth/register', json={
            'username': 'nav_test_user',
            'email': 'nav@test.com',
            'password': 'password123'
        })

        response = client.post('/api/auth/login', json={
            'username': 'nav_test_user',
            'password': 'password123'
        })

        return response.cookies.get('session_token')

    def test_notifications_link_in_nav(self, client, user_session):
        """Test that notifications link appears in navigation"""
        response = client.get(
            '/dashboard',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'/notifications' in response.content
        assert b'Notifications' in response.content

    def test_back_to_notifications_link(self, client, user_session):
        """Test that preferences page has back link"""
        response = client.get(
            '/notifications/preferences',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'Back to Notifications' in response.content

    def test_preferences_link_from_notifications(self, client, user_session):
        """Test that notifications page has preferences link"""
        response = client.get(
            '/notifications',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'/notifications/preferences' in response.content
        assert b'Preferences' in response.content
