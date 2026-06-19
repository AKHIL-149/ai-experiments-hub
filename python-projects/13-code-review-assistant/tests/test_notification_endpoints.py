"""Tests for Notification API Endpoints"""
import pytest
import sys
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

# Mock celery before imports
mock_celery = Mock()
mock_celery.celery_app = Mock()
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()
sys.modules['celery_app'] = mock_celery

from src.core.database import UserRole
from src.services.notification_service import NotificationType


def test_get_notifications_endpoint():
    """Test getting notifications via API"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/notifications")

        assert response.status_code == 200
        data = response.json()
        assert 'notifications' in data
        assert 'count' in data
        assert isinstance(data['notifications'], list)


def test_get_notifications_with_filters():
    """Test getting notifications with filters"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)

        # Test unread_only filter
        response = client.get("/api/notifications?unread_only=true")
        assert response.status_code == 200

        # Test notification_type filter
        response = client.get("/api/notifications?notification_type=info")
        assert response.status_code == 200

        # Test limit
        response = client.get("/api/notifications?limit=10")
        assert response.status_code == 200


def test_get_notification_by_id():
    """Test getting a specific notification"""
    from server import app
    from src.services.notification_service import notification_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        # Create a test notification
        notification = notification_service.create_notification(
            NotificationType.INFO,
            "Test",
            "Test message"
        )

        client = TestClient(app)
        response = client.get(f"/api/notifications/{notification['id']}")

        assert response.status_code == 200
        data = response.json()
        assert data['id'] == notification['id']
        assert data['title'] == "Test"


def test_get_notification_not_found():
    """Test getting non-existent notification"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/notifications/nonexistent")

        assert response.status_code == 404


def test_mark_notification_read():
    """Test marking notification as read"""
    from server import app
    from src.services.notification_service import notification_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        # Create a test notification
        notification = notification_service.create_notification(
            NotificationType.INFO,
            "Test",
            "Test message"
        )

        client = TestClient(app)
        response = client.post(f"/api/notifications/{notification['id']}/read")

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True

        # Verify it's marked as read
        updated = notification_service.get_notification(notification['id'])
        assert updated['read'] == True


def test_mark_all_notifications_read():
    """Test marking all notifications as read"""
    from server import app
    from src.services.notification_service import notification_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        # Create test notifications
        notification_service.create_notification(NotificationType.INFO, "Test 1", "Message 1", user_id="user1")
        notification_service.create_notification(NotificationType.INFO, "Test 2", "Message 2", user_id="user1")

        client = TestClient(app)
        response = client.post("/api/notifications/read-all?user_id=user1")

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert data['count'] >= 0


def test_dismiss_notification():
    """Test dismissing a notification"""
    from server import app
    from src.services.notification_service import notification_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        # Create a test notification
        notification = notification_service.create_notification(
            NotificationType.INFO,
            "Test",
            "Test message"
        )

        client = TestClient(app)
        response = client.post(f"/api/notifications/{notification['id']}/dismiss")

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True


def test_delete_notification():
    """Test deleting a notification"""
    from server import app
    from src.services.notification_service import notification_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        # Create a test notification
        notification = notification_service.create_notification(
            NotificationType.INFO,
            "Test",
            "Test message"
        )

        client = TestClient(app)
        response = client.delete(f"/api/notifications/{notification['id']}")

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True

        # Verify it's deleted
        deleted = notification_service.get_notification(notification['id'])
        assert deleted is None


def test_clear_old_notifications():
    """Test clearing old notifications"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.delete("/api/notifications/old?days=30")

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'count' in data


def test_get_notification_preferences():
    """Test getting notification preferences"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/notifications/preferences")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


def test_update_notification_preferences():
    """Test updating notification preferences"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    new_prefs = {
        NotificationType.INFO: {
            'enabled': False,
            'show_toast': False
        }
    }

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.post("/api/notifications/preferences", json=new_prefs)

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True


def test_get_notification_statistics():
    """Test getting notification statistics"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/notifications/statistics")

        assert response.status_code == 200
        data = response.json()
        assert 'total' in data
        assert 'unread' in data
        assert 'read' in data


def test_notification_endpoints_require_auth():
    """Test that notification endpoints require authentication"""
    from server import app

    client = TestClient(app)

    endpoints = [
        ("/api/notifications", "GET"),
        ("/api/notifications/test-id", "GET"),
        ("/api/notifications/test-id/read", "POST"),
        ("/api/notifications/read-all", "POST"),
        ("/api/notifications/test-id/dismiss", "POST"),
        ("/api/notifications/test-id", "DELETE"),
        ("/api/notifications/old", "DELETE"),
        ("/api/notifications/preferences", "GET"),
        ("/api/notifications/preferences", "POST"),
        ("/api/notifications/statistics", "GET")
    ]

    for endpoint, method in endpoints:
        if method == "GET":
            response = client.get(endpoint)
        elif method == "POST":
            response = client.post(endpoint, json={})
        elif method == "DELETE":
            response = client.delete(endpoint)

        assert response.status_code == 401, f"{method} {endpoint} should require auth"


def test_invalid_notification_type_filter():
    """Test that invalid notification type returns 400"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/notifications?notification_type=invalid_type")

        assert response.status_code == 400
