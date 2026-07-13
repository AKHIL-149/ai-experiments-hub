"""
Notification Service and Delivery Tracking

Provides multi-channel notifications (email, SMS, push, in-app), template management,
delivery tracking, and comprehensive analytics for user communication.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import random
import hashlib


class NotificationChannel(str, Enum):
    """Notification delivery channels"""
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"
    WEBHOOK = "webhook"


class NotificationPriority(str, Enum):
    """Notification priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationStatus(str, Enum):
    """Notification delivery status"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    OPENED = "opened"
    CLICKED = "clicked"


class TemplateType(str, Enum):
    """Template types"""
    TRANSACTIONAL = "transactional"
    MARKETING = "marketing"
    ALERT = "alert"
    SYSTEM = "system"


class NotificationService:
    """Notification Service and Delivery Tracking"""

    # In-memory storage
    _notifications: Dict[str, Dict] = {}
    _templates: Dict[str, Dict] = {}
    _delivery_logs: List[Dict] = []
    _user_preferences: Dict[str, Dict] = {}
    _notification_batches: Dict[str, Dict] = {}

    @staticmethod
    def create_template(
        session,
        template_id: str,
        name: str,
        channel: NotificationChannel,
        template_type: TemplateType,
        subject: Optional[str] = None,
        body: str = None,
        variables: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Create a notification template."""
        if template_id in NotificationService._templates:
            raise ValueError(f"Template already exists: {template_id}")

        template = {
            "template_id": template_id,
            "name": name,
            "channel": channel,
            "template_type": template_type,
            "subject": subject,
            "body": body or "",
            "variables": variables or [],
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "is_active": True,
            "usage_count": 0,
            "version": 1
        }

        NotificationService._templates[template_id] = template

        return template

    @staticmethod
    def send_notification(
        session,
        notification_id: str,
        user_id: str,
        channel: NotificationChannel,
        template_id: Optional[str] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        data: Optional[Dict] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        scheduled_at: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Send a notification to a user."""
        # Check user preferences
        preferences = NotificationService._user_preferences.get(user_id, {})
        channel_enabled = preferences.get("channels", {}).get(channel, True)

        if not channel_enabled:
            return {
                "notification_id": notification_id,
                "status": NotificationStatus.FAILED,
                "error": f"User has disabled {channel} notifications"
            }

        # Use template if provided
        if template_id:
            template = NotificationService._templates.get(template_id)
            if not template:
                raise ValueError(f"Template not found: {template_id}")

            # Render template with data
            rendered_subject = NotificationService._render_template(
                template.get("subject", ""),
                data or {}
            )
            rendered_body = NotificationService._render_template(
                template["body"],
                data or {}
            )

            subject = rendered_subject or subject
            body = rendered_body

            # Update template usage
            template["usage_count"] += 1

        notification = {
            "notification_id": notification_id,
            "user_id": user_id,
            "channel": channel,
            "template_id": template_id,
            "subject": subject,
            "body": body,
            "data": data or {},
            "priority": priority,
            "status": NotificationStatus.PENDING,
            "scheduled_at": scheduled_at,
            "sent_at": None,
            "delivered_at": None,
            "opened_at": None,
            "clicked_at": None,
            "failed_at": None,
            "error_message": None,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "attempts": 0,
            "max_attempts": 3
        }

        # If not scheduled, send immediately
        if not scheduled_at or scheduled_at <= datetime.utcnow().isoformat():
            notification = NotificationService._deliver_notification(notification)

        NotificationService._notifications[notification_id] = notification

        return notification

    @staticmethod
    def _render_template(template: str, data: Dict) -> str:
        """Render template with variables."""
        rendered = template
        for key, value in data.items():
            placeholder = f"{{{{{key}}}}}"
            rendered = rendered.replace(placeholder, str(value))
        return rendered

    @staticmethod
    def _deliver_notification(notification: dict) -> dict:
        """Deliver a notification through the specified channel."""
        channel = notification["channel"]
        notification["attempts"] += 1

        # Simulate delivery based on channel
        success = random.random() > 0.05  # 95% success rate

        if success:
            notification["status"] = NotificationStatus.SENT
            notification["sent_at"] = datetime.utcnow().isoformat()

            # Simulate delivery confirmation
            if random.random() > 0.1:  # 90% delivery rate
                notification["status"] = NotificationStatus.DELIVERED
                notification["delivered_at"] = datetime.utcnow().isoformat()

            # Log delivery
            NotificationService._log_delivery(notification, success=True)
        else:
            notification["status"] = NotificationStatus.FAILED
            notification["failed_at"] = datetime.utcnow().isoformat()
            notification["error_message"] = f"Failed to deliver via {channel}"

            # Log failure
            NotificationService._log_delivery(notification, success=False)

        return notification

    @staticmethod
    def _log_delivery(notification: dict, success: bool):
        """Log notification delivery."""
        log_entry = {
            "log_id": f"log_{len(NotificationService._delivery_logs)}_{datetime.utcnow().timestamp()}",
            "notification_id": notification["notification_id"],
            "user_id": notification["user_id"],
            "channel": notification["channel"],
            "status": notification["status"],
            "success": success,
            "attempt": notification["attempts"],
            "timestamp": datetime.utcnow().isoformat()
        }

        NotificationService._delivery_logs.append(log_entry)

        # Keep only last 100000 logs
        NotificationService._delivery_logs = NotificationService._delivery_logs[-100000:]

    @staticmethod
    def track_event(
        session,
        notification_id: str,
        event_type: str
    ) -> dict:
        """Track notification events (opened, clicked)."""
        notification = NotificationService._notifications.get(notification_id)
        if not notification:
            raise ValueError(f"Notification not found: {notification_id}")

        timestamp = datetime.utcnow().isoformat()

        if event_type == "opened":
            notification["status"] = NotificationStatus.OPENED
            notification["opened_at"] = timestamp
        elif event_type == "clicked":
            notification["status"] = NotificationStatus.CLICKED
            notification["clicked_at"] = timestamp

        return notification

    @staticmethod
    def send_batch(
        session,
        batch_id: str,
        user_ids: List[str],
        channel: NotificationChannel,
        template_id: str,
        data: Optional[Dict] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL
    ) -> dict:
        """Send notifications to multiple users."""
        batch = {
            "batch_id": batch_id,
            "user_ids": user_ids,
            "channel": channel,
            "template_id": template_id,
            "data": data or {},
            "priority": priority,
            "created_at": datetime.utcnow().isoformat(),
            "total_recipients": len(user_ids),
            "sent_count": 0,
            "delivered_count": 0,
            "failed_count": 0,
            "notification_ids": []
        }

        # Send to each user
        for user_id in user_ids:
            notification_id = f"{batch_id}_{user_id}_{datetime.utcnow().timestamp()}"

            try:
                notification = NotificationService.send_notification(
                    session=session,
                    notification_id=notification_id,
                    user_id=user_id,
                    channel=channel,
                    template_id=template_id,
                    data=data,
                    priority=priority
                )

                batch["notification_ids"].append(notification_id)

                if notification["status"] == NotificationStatus.SENT:
                    batch["sent_count"] += 1
                if notification["status"] == NotificationStatus.DELIVERED:
                    batch["delivered_count"] += 1
                if notification["status"] == NotificationStatus.FAILED:
                    batch["failed_count"] += 1

            except Exception as e:
                batch["failed_count"] += 1

        NotificationService._notification_batches[batch_id] = batch

        return batch

    @staticmethod
    def set_user_preferences(
        session,
        user_id: str,
        channels: Optional[Dict[str, bool]] = None,
        quiet_hours: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Set notification preferences for a user."""
        preferences = NotificationService._user_preferences.get(user_id, {
            "user_id": user_id,
            "channels": {
                NotificationChannel.EMAIL: True,
                NotificationChannel.SMS: True,
                NotificationChannel.PUSH: True,
                NotificationChannel.IN_APP: True
            },
            "quiet_hours": None,
            "metadata": {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        })

        if channels:
            preferences["channels"].update(channels)
        if quiet_hours:
            preferences["quiet_hours"] = quiet_hours
        if metadata:
            preferences["metadata"] = metadata

        preferences["updated_at"] = datetime.utcnow().isoformat()

        NotificationService._user_preferences[user_id] = preferences

        return preferences

    @staticmethod
    def get_user_notifications(
        session,
        user_id: str,
        channel: Optional[NotificationChannel] = None,
        status: Optional[NotificationStatus] = None,
        limit: int = 50
    ) -> List[dict]:
        """Get notifications for a user."""
        notifications = [
            n for n in NotificationService._notifications.values()
            if n["user_id"] == user_id
        ]

        # Apply filters
        if channel:
            notifications = [n for n in notifications if n["channel"] == channel]
        if status:
            notifications = [n for n in notifications if n["status"] == status]

        # Sort by created_at descending
        notifications.sort(key=lambda x: x["created_at"], reverse=True)

        return notifications[:limit]

    @staticmethod
    def retry_failed_notification(session, notification_id: str) -> dict:
        """Retry a failed notification."""
        notification = NotificationService._notifications.get(notification_id)
        if not notification:
            raise ValueError(f"Notification not found: {notification_id}")

        if notification["status"] not in [NotificationStatus.FAILED, NotificationStatus.BOUNCED]:
            raise ValueError("Can only retry failed notifications")

        if notification["attempts"] >= notification["max_attempts"]:
            raise ValueError("Maximum retry attempts reached")

        # Reset status and retry
        notification["status"] = NotificationStatus.PENDING
        notification = NotificationService._deliver_notification(notification)

        return notification

    @staticmethod
    def get_template_analytics(session, template_id: str) -> dict:
        """Get analytics for a template."""
        template = NotificationService._templates.get(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        # Get notifications using this template
        notifications = [
            n for n in NotificationService._notifications.values()
            if n["template_id"] == template_id
        ]

        total = len(notifications)
        sent = sum(1 for n in notifications if n["status"] in [NotificationStatus.SENT, NotificationStatus.DELIVERED])
        delivered = sum(1 for n in notifications if n["status"] == NotificationStatus.DELIVERED)
        opened = sum(1 for n in notifications if n["status"] == NotificationStatus.OPENED)
        clicked = sum(1 for n in notifications if n["status"] == NotificationStatus.CLICKED)
        failed = sum(1 for n in notifications if n["status"] == NotificationStatus.FAILED)

        return {
            "template_id": template_id,
            "name": template["name"],
            "channel": template["channel"],
            "total_sent": total,
            "sent_count": sent,
            "delivered_count": delivered,
            "opened_count": opened,
            "clicked_count": clicked,
            "failed_count": failed,
            "delivery_rate": (delivered / total * 100) if total > 0 else 0,
            "open_rate": (opened / delivered * 100) if delivered > 0 else 0,
            "click_rate": (clicked / opened * 100) if opened > 0 else 0,
            "analyzed_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get comprehensive notification statistics."""
        total_notifications = len(NotificationService._notifications)
        total_templates = len(NotificationService._templates)

        # By status
        by_status = defaultdict(int)
        for notification in NotificationService._notifications.values():
            by_status[notification["status"]] += 1

        # By channel
        by_channel = defaultdict(int)
        for notification in NotificationService._notifications.values():
            by_channel[notification["channel"]] += 1

        # Recent activity (last 24 hours)
        one_day_ago = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        recent_notifications = sum(
            1 for n in NotificationService._notifications.values()
            if n["created_at"] >= one_day_ago
        )
        recent_sent = sum(
            1 for n in NotificationService._notifications.values()
            if n["created_at"] >= one_day_ago and n["status"] in [NotificationStatus.SENT, NotificationStatus.DELIVERED]
        )

        return {
            "notifications": {
                "total": total_notifications,
                "by_status": dict(by_status),
                "by_channel": dict(by_channel),
                "recent_24h": recent_notifications
            },
            "templates": {
                "total": total_templates,
                "active": sum(1 for t in NotificationService._templates.values() if t["is_active"])
            },
            "delivery": {
                "sent_count": by_status[NotificationStatus.SENT] + by_status[NotificationStatus.DELIVERED],
                "delivered_count": by_status[NotificationStatus.DELIVERED],
                "failed_count": by_status[NotificationStatus.FAILED],
                "delivery_rate": (by_status[NotificationStatus.DELIVERED] / total_notifications * 100) if total_notifications > 0 else 0,
                "recent_sent_24h": recent_sent
            },
            "engagement": {
                "opened_count": by_status[NotificationStatus.OPENED],
                "clicked_count": by_status[NotificationStatus.CLICKED],
                "open_rate": (by_status[NotificationStatus.OPENED] / by_status[NotificationStatus.DELIVERED] * 100) if by_status[NotificationStatus.DELIVERED] > 0 else 0
            },
            "batches": {
                "total": len(NotificationService._notification_batches)
            },
            "user_preferences": {
                "total": len(NotificationService._user_preferences)
            }
        }
