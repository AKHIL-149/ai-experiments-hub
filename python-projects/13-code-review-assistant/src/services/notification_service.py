"""
Notification Service
Manages in-app notifications with preferences and persistence
"""

from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import json


class NotificationType(str, Enum):
    """Notification types"""
    ANALYSIS_COMPLETE = "analysis_complete"
    ISSUE_FOUND = "issue_found"
    CRITICAL_ISSUE = "critical_issue"
    PR_REVIEWED = "pr_reviewed"
    REFACTORING_SUGGESTED = "refactoring_suggested"
    HEALTH_SCORE_CHANGED = "health_score_changed"
    SYSTEM = "system"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class NotificationPriority(str, Enum):
    """Notification priorities"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationService:
    """Service for managing notifications"""

    def __init__(self):
        self.notifications = []
        self.preferences = self._default_preferences()
        self.listeners = {}

    def _default_preferences(self) -> Dict:
        """Get default notification preferences"""
        return {
            NotificationType.ANALYSIS_COMPLETE: {
                'enabled': True,
                'show_toast': True,
                'priority': NotificationPriority.MEDIUM
            },
            NotificationType.ISSUE_FOUND: {
                'enabled': True,
                'show_toast': False,
                'priority': NotificationPriority.LOW
            },
            NotificationType.CRITICAL_ISSUE: {
                'enabled': True,
                'show_toast': True,
                'priority': NotificationPriority.CRITICAL
            },
            NotificationType.PR_REVIEWED: {
                'enabled': True,
                'show_toast': True,
                'priority': NotificationPriority.MEDIUM
            },
            NotificationType.REFACTORING_SUGGESTED: {
                'enabled': True,
                'show_toast': False,
                'priority': NotificationPriority.LOW
            },
            NotificationType.HEALTH_SCORE_CHANGED: {
                'enabled': True,
                'show_toast': True,
                'priority': NotificationPriority.MEDIUM
            },
            NotificationType.SYSTEM: {
                'enabled': True,
                'show_toast': True,
                'priority': NotificationPriority.HIGH
            },
            NotificationType.INFO: {
                'enabled': True,
                'show_toast': True,
                'priority': NotificationPriority.LOW
            },
            NotificationType.WARNING: {
                'enabled': True,
                'show_toast': True,
                'priority': NotificationPriority.MEDIUM
            },
            NotificationType.ERROR: {
                'enabled': True,
                'show_toast': True,
                'priority': NotificationPriority.HIGH
            }
        }

    # ============================================================================
    # Notification Creation
    # ============================================================================

    def create_notification(
        self,
        notification_type: NotificationType,
        title: str,
        message: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        priority: Optional[NotificationPriority] = None
    ) -> Dict:
        """
        Create a new notification

        Args:
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            user_id: User ID to send notification to
            metadata: Additional metadata
            priority: Override default priority

        Returns:
            Created notification dictionary
        """
        # Check if this notification type is enabled
        if not self.is_notification_enabled(notification_type):
            return None

        # Get priority from preferences if not specified
        if priority is None:
            priority = self.preferences.get(notification_type, {}).get(
                'priority',
                NotificationPriority.MEDIUM
            )

        # Create notification
        notification = {
            'id': self._generate_id(),
            'type': notification_type,
            'title': title,
            'message': message,
            'user_id': user_id,
            'priority': priority,
            'metadata': metadata or {},
            'created_at': datetime.now().isoformat(),
            'read': False,
            'dismissed': False,
            'show_toast': self.preferences.get(notification_type, {}).get('show_toast', True)
        }

        # Store notification
        self.notifications.append(notification)

        # Trigger event listeners
        self._trigger_event('notification_created', notification)

        return notification

    def _generate_id(self) -> str:
        """Generate unique notification ID"""
        import uuid
        return str(uuid.uuid4())

    # ============================================================================
    # Convenience Methods for Common Notifications
    # ============================================================================

    def notify_analysis_complete(
        self,
        filename: str,
        issues_count: int,
        user_id: Optional[str] = None
    ) -> Dict:
        """Notify when analysis is complete"""
        return self.create_notification(
            notification_type=NotificationType.ANALYSIS_COMPLETE,
            title="Analysis Complete",
            message=f"Analyzed {filename} - found {issues_count} issue(s)",
            user_id=user_id,
            metadata={'filename': filename, 'issues_count': issues_count}
        )

    def notify_critical_issue(
        self,
        issue_title: str,
        filename: str,
        user_id: Optional[str] = None
    ) -> Dict:
        """Notify when critical issue is found"""
        return self.create_notification(
            notification_type=NotificationType.CRITICAL_ISSUE,
            title="Critical Issue Found",
            message=f"{issue_title} in {filename}",
            user_id=user_id,
            metadata={'issue_title': issue_title, 'filename': filename},
            priority=NotificationPriority.CRITICAL
        )

    def notify_pr_reviewed(
        self,
        pr_number: int,
        issues_count: int,
        user_id: Optional[str] = None
    ) -> Dict:
        """Notify when PR review is complete"""
        return self.create_notification(
            notification_type=NotificationType.PR_REVIEWED,
            title="Pull Request Reviewed",
            message=f"PR #{pr_number} reviewed - {issues_count} issue(s) found",
            user_id=user_id,
            metadata={'pr_number': pr_number, 'issues_count': issues_count}
        )

    def notify_health_score_changed(
        self,
        old_score: float,
        new_score: float,
        user_id: Optional[str] = None
    ) -> Dict:
        """Notify when health score changes significantly"""
        change = new_score - old_score
        direction = "improved" if change > 0 else "declined"

        return self.create_notification(
            notification_type=NotificationType.HEALTH_SCORE_CHANGED,
            title=f"Health Score {direction.title()}",
            message=f"Code health {direction} from {old_score:.1f} to {new_score:.1f}",
            user_id=user_id,
            metadata={'old_score': old_score, 'new_score': new_score, 'change': change}
        )

    # ============================================================================
    # Notification Management
    # ============================================================================

    def get_notifications(
        self,
        user_id: Optional[str] = None,
        unread_only: bool = False,
        notification_type: Optional[NotificationType] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get notifications with filters

        Args:
            user_id: Filter by user ID
            unread_only: Only return unread notifications
            notification_type: Filter by type
            limit: Maximum number to return

        Returns:
            List of notifications
        """
        filtered = self.notifications

        # Filter by user
        if user_id:
            filtered = [n for n in filtered if n.get('user_id') == user_id]

        # Filter by read status
        if unread_only:
            filtered = [n for n in filtered if not n.get('read', False)]

        # Filter by type
        if notification_type:
            filtered = [n for n in filtered if n.get('type') == notification_type]

        # Filter out dismissed
        filtered = [n for n in filtered if not n.get('dismissed', False)]

        # Sort by created_at (newest first)
        filtered.sort(key=lambda n: n.get('created_at', ''), reverse=True)

        return filtered[:limit]

    def get_notification(self, notification_id: str) -> Optional[Dict]:
        """Get a specific notification by ID"""
        for notification in self.notifications:
            if notification['id'] == notification_id:
                return notification
        return None

    def mark_as_read(self, notification_id: str) -> bool:
        """Mark notification as read"""
        notification = self.get_notification(notification_id)
        if notification:
            notification['read'] = True
            notification['read_at'] = datetime.now().isoformat()
            self._trigger_event('notification_read', notification)
            return True
        return False

    def mark_all_as_read(self, user_id: Optional[str] = None) -> int:
        """Mark all notifications as read"""
        count = 0
        for notification in self.notifications:
            if user_id and notification.get('user_id') != user_id:
                continue
            if not notification.get('read', False):
                notification['read'] = True
                notification['read_at'] = datetime.now().isoformat()
                count += 1

        if count > 0:
            self._trigger_event('notifications_marked_read', {'count': count, 'user_id': user_id})

        return count

    def dismiss_notification(self, notification_id: str) -> bool:
        """Dismiss a notification"""
        notification = self.get_notification(notification_id)
        if notification:
            notification['dismissed'] = True
            notification['dismissed_at'] = datetime.now().isoformat()
            self._trigger_event('notification_dismissed', notification)
            return True
        return False

    def delete_notification(self, notification_id: str) -> bool:
        """Delete a notification permanently"""
        notification = self.get_notification(notification_id)
        if notification:
            self.notifications.remove(notification)
            self._trigger_event('notification_deleted', notification)
            return True
        return False

    def clear_old_notifications(self, days: int = 30) -> int:
        """Clear notifications older than specified days"""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        before_count = len(self.notifications)
        self.notifications = [
            n for n in self.notifications
            if n.get('created_at', '') >= cutoff_str
        ]
        after_count = len(self.notifications)

        deleted_count = before_count - after_count

        if deleted_count > 0:
            self._trigger_event('notifications_cleared', {'count': deleted_count, 'days': days})

        return deleted_count

    # ============================================================================
    # Preference Management
    # ============================================================================

    def update_preferences(self, preferences: Dict) -> bool:
        """Update notification preferences"""
        try:
            # Merge with existing preferences
            for notification_type, settings in preferences.items():
                if notification_type in self.preferences:
                    self.preferences[notification_type].update(settings)
                else:
                    self.preferences[notification_type] = settings

            self._trigger_event('preferences_updated', preferences)
            return True
        except Exception as e:
            print(f"Error updating preferences: {e}")
            return False

    def get_preferences(self) -> Dict:
        """Get current notification preferences"""
        return self.preferences.copy()

    def is_notification_enabled(self, notification_type: NotificationType) -> bool:
        """Check if a notification type is enabled"""
        return self.preferences.get(notification_type, {}).get('enabled', True)

    def enable_notification_type(self, notification_type: NotificationType) -> bool:
        """Enable a notification type"""
        if notification_type in self.preferences:
            self.preferences[notification_type]['enabled'] = True
            return True
        return False

    def disable_notification_type(self, notification_type: NotificationType) -> bool:
        """Disable a notification type"""
        if notification_type in self.preferences:
            self.preferences[notification_type]['enabled'] = False
            return True
        return False

    # ============================================================================
    # Statistics
    # ============================================================================

    def get_statistics(self, user_id: Optional[str] = None) -> Dict:
        """Get notification statistics"""
        notifications = self.get_notifications(user_id=user_id, limit=10000)

        total = len(notifications)
        unread = len([n for n in notifications if not n.get('read', False)])
        by_type = {}
        by_priority = {}

        for notification in notifications:
            # Count by type
            ntype = notification.get('type', 'unknown')
            by_type[ntype] = by_type.get(ntype, 0) + 1

            # Count by priority
            priority = notification.get('priority', 'medium')
            by_priority[priority] = by_priority.get(priority, 0) + 1

        return {
            'total': total,
            'unread': unread,
            'read': total - unread,
            'by_type': by_type,
            'by_priority': by_priority
        }

    # ============================================================================
    # Event System
    # ============================================================================

    def add_listener(self, event_name: str, callback) -> None:
        """Add event listener"""
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def remove_listener(self, event_name: str, callback) -> bool:
        """Remove event listener"""
        if event_name in self.listeners and callback in self.listeners[event_name]:
            self.listeners[event_name].remove(callback)
            return True
        return False

    def _trigger_event(self, event_name: str, data: any) -> None:
        """Trigger event listeners"""
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                try:
                    callback(data)
                except Exception as e:
                    print(f"Error in event listener: {e}")

    # ============================================================================
    # Persistence
    # ============================================================================

    def export_notifications(self) -> str:
        """Export notifications to JSON"""
        return json.dumps({
            'notifications': self.notifications,
            'preferences': self.preferences,
            'exported_at': datetime.now().isoformat()
        }, indent=2)

    def import_notifications(self, json_str: str) -> bool:
        """Import notifications from JSON"""
        try:
            data = json.loads(json_str)
            self.notifications = data.get('notifications', [])
            self.preferences = data.get('preferences', self._default_preferences())
            self._trigger_event('notifications_imported', data)
            return True
        except Exception as e:
            print(f"Error importing notifications: {e}")
            return False


# Global instance
notification_service = NotificationService()
