"""Tests for Notification Service"""
import pytest
from datetime import datetime, timedelta
from src.services.notification_service import (
    NotificationService,
    NotificationType,
    NotificationPriority,
    notification_service
)


@pytest.fixture
def service():
    """Create fresh notification service"""
    return NotificationService()


def test_create_notification(service):
    """Test creating a basic notification"""
    notification = service.create_notification(
        notification_type=NotificationType.INFO,
        title="Test Notification",
        message="This is a test",
        user_id="user123"
    )

    assert notification is not None
    assert notification['title'] == "Test Notification"
    assert notification['message'] == "This is a test"
    assert notification['user_id'] == "user123"
    assert notification['type'] == NotificationType.INFO
    assert notification['read'] == False
    assert notification['dismissed'] == False
    assert 'id' in notification
    assert 'created_at' in notification


def test_create_notification_with_metadata(service):
    """Test creating notification with metadata"""
    metadata = {'filename': 'test.py', 'issues': 5}

    notification = service.create_notification(
        notification_type=NotificationType.ANALYSIS_COMPLETE,
        title="Analysis Done",
        message="Found 5 issues",
        metadata=metadata
    )

    assert notification['metadata'] == metadata


def test_create_notification_respects_preferences(service):
    """Test that disabled notifications are not created"""
    # Disable INFO notifications
    service.disable_notification_type(NotificationType.INFO)

    notification = service.create_notification(
        notification_type=NotificationType.INFO,
        title="Should Not Create",
        message="This should be None"
    )

    assert notification is None


def test_notify_analysis_complete(service):
    """Test analysis complete convenience method"""
    notification = service.notify_analysis_complete(
        filename="test.py",
        issues_count=3,
        user_id="user123"
    )

    assert notification is not None
    assert notification['type'] == NotificationType.ANALYSIS_COMPLETE
    assert 'test.py' in notification['message']
    assert notification['metadata']['issues_count'] == 3


def test_notify_critical_issue(service):
    """Test critical issue notification"""
    notification = service.notify_critical_issue(
        issue_title="SQL Injection",
        filename="database.py",
        user_id="user123"
    )

    assert notification is not None
    assert notification['type'] == NotificationType.CRITICAL_ISSUE
    assert notification['priority'] == NotificationPriority.CRITICAL
    assert 'SQL Injection' in notification['message']


def test_notify_pr_reviewed(service):
    """Test PR reviewed notification"""
    notification = service.notify_pr_reviewed(
        pr_number=42,
        issues_count=7,
        user_id="user123"
    )

    assert notification is not None
    assert notification['type'] == NotificationType.PR_REVIEWED
    assert '42' in notification['message']


def test_notify_health_score_changed(service):
    """Test health score change notification"""
    notification = service.notify_health_score_changed(
        old_score=75.0,
        new_score=85.0,
        user_id="user123"
    )

    assert notification is not None
    assert notification['type'] == NotificationType.HEALTH_SCORE_CHANGED
    assert 'improved' in notification['message'].lower()
    assert notification['metadata']['change'] == 10.0


def test_get_notifications(service):
    """Test getting notifications with filters"""
    # Create multiple notifications
    service.create_notification(NotificationType.INFO, "Test 1", "Message 1", user_id="user1")
    service.create_notification(NotificationType.INFO, "Test 2", "Message 2", user_id="user2")
    service.create_notification(NotificationType.ERROR, "Test 3", "Message 3", user_id="user1")

    # Get all notifications
    all_notifs = service.get_notifications()
    assert len(all_notifs) == 3

    # Filter by user
    user1_notifs = service.get_notifications(user_id="user1")
    assert len(user1_notifs) == 2

    # Filter by type
    error_notifs = service.get_notifications(notification_type=NotificationType.ERROR)
    assert len(error_notifs) == 1


def test_get_notifications_unread_only(service):
    """Test getting only unread notifications"""
    # Create notifications
    n1 = service.create_notification(NotificationType.INFO, "Test 1", "Message 1")
    n2 = service.create_notification(NotificationType.INFO, "Test 2", "Message 2")

    # Mark one as read
    service.mark_as_read(n1['id'])

    # Get unread only
    unread = service.get_notifications(unread_only=True)
    assert len(unread) == 1
    assert unread[0]['id'] == n2['id']


def test_mark_as_read(service):
    """Test marking notification as read"""
    notification = service.create_notification(
        NotificationType.INFO,
        "Test",
        "Message"
    )

    assert notification['read'] == False

    # Mark as read
    result = service.mark_as_read(notification['id'])
    assert result == True

    # Verify
    updated = service.get_notification(notification['id'])
    assert updated['read'] == True
    assert 'read_at' in updated


def test_mark_all_as_read(service):
    """Test marking all notifications as read"""
    # Create multiple notifications
    service.create_notification(NotificationType.INFO, "Test 1", "Message 1", user_id="user1")
    service.create_notification(NotificationType.INFO, "Test 2", "Message 2", user_id="user1")
    service.create_notification(NotificationType.INFO, "Test 3", "Message 3", user_id="user2")

    # Mark all for user1 as read
    count = service.mark_all_as_read(user_id="user1")
    assert count == 2

    # Verify
    unread = service.get_notifications(user_id="user1", unread_only=True)
    assert len(unread) == 0


def test_dismiss_notification(service):
    """Test dismissing a notification"""
    notification = service.create_notification(
        NotificationType.INFO,
        "Test",
        "Message"
    )

    # Dismiss
    result = service.dismiss_notification(notification['id'])
    assert result == True

    # Dismissed notifications are filtered out
    all_notifs = service.get_notifications()
    assert len(all_notifs) == 0


def test_delete_notification(service):
    """Test deleting a notification permanently"""
    notification = service.create_notification(
        NotificationType.INFO,
        "Test",
        "Message"
    )

    assert len(service.notifications) == 1

    # Delete
    result = service.delete_notification(notification['id'])
    assert result == True
    assert len(service.notifications) == 0


def test_clear_old_notifications(service):
    """Test clearing old notifications"""
    # Create old notification (manually set date)
    old_notification = service.create_notification(
        NotificationType.INFO,
        "Old",
        "Old message"
    )
    old_date = (datetime.now() - timedelta(days=60)).isoformat()
    old_notification['created_at'] = old_date

    # Create recent notification
    service.create_notification(NotificationType.INFO, "Recent", "Recent message")

    # Clear old (>30 days)
    deleted_count = service.clear_old_notifications(days=30)
    assert deleted_count == 1
    assert len(service.notifications) == 1


def test_update_preferences(service):
    """Test updating notification preferences"""
    new_prefs = {
        NotificationType.INFO: {
            'enabled': False,
            'show_toast': False
        }
    }

    result = service.update_preferences(new_prefs)
    assert result == True

    # Verify
    assert service.is_notification_enabled(NotificationType.INFO) == False


def test_get_preferences(service):
    """Test getting notification preferences"""
    prefs = service.get_preferences()

    assert isinstance(prefs, dict)
    assert NotificationType.INFO in prefs
    assert NotificationType.CRITICAL_ISSUE in prefs
    assert 'enabled' in prefs[NotificationType.INFO]


def test_enable_disable_notification_type(service):
    """Test enabling/disabling notification types"""
    # Disable
    result = service.disable_notification_type(NotificationType.INFO)
    assert result == True
    assert service.is_notification_enabled(NotificationType.INFO) == False

    # Enable
    result = service.enable_notification_type(NotificationType.INFO)
    assert result == True
    assert service.is_notification_enabled(NotificationType.INFO) == True


def test_get_statistics(service):
    """Test getting notification statistics"""
    # Create various notifications
    service.create_notification(NotificationType.INFO, "Info 1", "Message")
    service.create_notification(NotificationType.INFO, "Info 2", "Message")
    service.create_notification(NotificationType.ERROR, "Error 1", "Message")

    # Mark one as read
    notifs = service.get_notifications()
    service.mark_as_read(notifs[0]['id'])

    # Get statistics
    stats = service.get_statistics()

    assert stats['total'] == 3
    assert stats['unread'] == 2
    assert stats['read'] == 1
    assert stats['by_type'][NotificationType.INFO] == 2
    assert stats['by_type'][NotificationType.ERROR] == 1


def test_event_listeners(service):
    """Test event listener system"""
    events_received = []

    def listener(data):
        events_received.append(data)

    # Add listener
    service.add_listener('notification_created', listener)

    # Create notification
    notification = service.create_notification(
        NotificationType.INFO,
        "Test",
        "Message"
    )

    # Verify event was triggered
    assert len(events_received) == 1
    assert events_received[0]['id'] == notification['id']

    # Remove listener
    result = service.remove_listener('notification_created', listener)
    assert result == True


def test_export_import_notifications(service):
    """Test exporting and importing notifications"""
    # Create notifications
    service.create_notification(NotificationType.INFO, "Test 1", "Message 1")
    service.create_notification(NotificationType.ERROR, "Test 2", "Message 2")

    # Export
    exported = service.export_notifications()
    assert isinstance(exported, str)
    assert 'Test 1' in exported

    # Create new service and import
    new_service = NotificationService()
    result = new_service.import_notifications(exported)
    assert result == True
    assert len(new_service.notifications) == 2


def test_global_notification_service_instance():
    """Test that global instance exists and is usable"""
    assert notification_service is not None
    assert isinstance(notification_service, NotificationService)

    # Can create notifications
    notification = notification_service.create_notification(
        NotificationType.INFO,
        "Global Test",
        "Testing global instance"
    )
    assert notification is not None
