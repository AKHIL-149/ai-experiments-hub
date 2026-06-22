"""
Notification Digest Service
Aggregates notifications and creates digest emails/messages
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

from src.core.database import DatabaseManager, NotificationRule, EmailConfiguration
from src.services.email_service import get_email_service
from src.services.slack_service import get_slack_service
from src.services.discord_service import get_discord_service


class NotificationDigestService:
    """Service for creating and sending notification digests"""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize digest service

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager or DatabaseManager()
        self.email_service = get_email_service()
        self.slack_service = get_slack_service()
        self.discord_service = get_discord_service()

    def aggregate_notifications(
        self,
        user_id: str,
        period: str = 'daily',
        repository_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Aggregate notifications for digest

        Args:
            user_id: User ID
            period: Digest period (daily, weekly)
            repository_id: Optional repository filter

        Returns:
            Aggregated notification data
        """
        # Calculate time window
        now = datetime.now(timezone.utc)
        if period == 'daily':
            since = now - timedelta(days=1)
        elif period == 'weekly':
            since = now - timedelta(weeks=1)
        else:
            since = now - timedelta(days=1)

        # In a real implementation, this would query a notifications table
        # For now, we'll create a structure for batched notifications
        digest = {
            'period': period,
            'start_time': since.isoformat(),
            'end_time': now.isoformat(),
            'user_id': user_id,
            'repository_id': repository_id,
            'summary': {
                'total_notifications': 0,
                'critical_issues': 0,
                'prs_analyzed': 0,
                'total_issues': 0
            },
            'notifications_by_type': defaultdict(list),
            'notifications_by_severity': defaultdict(int),
            'top_issues': []
        }

        return digest

    def create_email_digest(
        self,
        user_id: str,
        period: str = 'daily',
        repository_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create email digest

        Args:
            user_id: User ID
            period: Digest period
            repository_id: Optional repository filter

        Returns:
            Result dict
        """
        digest_data = self.aggregate_notifications(user_id, period, repository_id)

        # Get email configuration
        with self.db_manager.get_session() as db:
            email_config = db.query(EmailConfiguration).filter(
                EmailConfiguration.user_id == user_id,
                EmailConfiguration.enabled == True,
                EmailConfiguration.enable_digest == True
            ).first()

            if not email_config:
                return {
                    'success': False,
                    'error': 'No email digest configuration found'
                }

            # Format notifications for email
            notifications = self._format_notifications_for_email(digest_data)

            # Send digest email
            result = self.email_service.send_digest(
                to_email=email_config.to_email,
                notifications=notifications,
                period=period
            )

            # Update last digest sent time
            if result.get('success'):
                email_config.last_digest_sent = datetime.now(timezone.utc)
                db.commit()

            return result

    def create_slack_digest(
        self,
        user_id: str,
        period: str = 'daily',
        repository_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create Slack digest

        Args:
            user_id: User ID
            period: Digest period
            repository_id: Optional repository filter

        Returns:
            Result dict
        """
        digest_data = self.aggregate_notifications(user_id, period, repository_id)

        summary = digest_data['summary']
        period_label = period.capitalize()

        # Create Slack message
        message = f"📊 *{period_label} Code Review Digest*\n\n"
        message += f"*{summary['total_notifications']}* notifications • "
        message += f"*{summary['prs_analyzed']}* PRs analyzed • "
        message += f"*{summary['total_issues']}* issues found"

        if summary['critical_issues'] > 0:
            message += f"\n⚠️ *{summary['critical_issues']} critical issues* require immediate attention"

        blocks = self._format_notifications_for_slack(digest_data)

        return self.slack_service.send_message(
            text=message,
            blocks=blocks
        )

    def create_discord_digest(
        self,
        user_id: str,
        period: str = 'daily',
        repository_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create Discord digest

        Args:
            user_id: User ID
            period: Digest period
            repository_id: Optional repository filter

        Returns:
            Result dict
        """
        digest_data = self.aggregate_notifications(user_id, period, repository_id)

        summary = digest_data['summary']
        period_label = period.capitalize()

        # Determine color based on critical issues
        if summary['critical_issues'] > 0:
            color = 0xdc2626  # red
        elif summary['total_issues'] > 10:
            color = 0xf59e0b  # orange
        else:
            color = 0x10b981  # green

        content = f"📊 **{period_label} Code Review Digest**"

        embed = {
            'title': f'{period_label} Summary',
            'color': color,
            'fields': [
                {
                    'name': 'Total Notifications',
                    'value': str(summary['total_notifications']),
                    'inline': True
                },
                {
                    'name': 'PRs Analyzed',
                    'value': str(summary['prs_analyzed']),
                    'inline': True
                },
                {
                    'name': 'Issues Found',
                    'value': str(summary['total_issues']),
                    'inline': True
                },
                {
                    'name': 'Critical Issues',
                    'value': str(summary['critical_issues']),
                    'inline': True
                }
            ],
            'footer': {
                'text': 'Code Review Assistant Digest'
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return self.discord_service.send_message(
            content=content,
            embeds=[embed]
        )

    def send_all_digests(self, period: str = 'daily') -> Dict[str, Any]:
        """
        Send digests to all users with digest enabled

        Args:
            period: Digest period

        Returns:
            Summary of sent digests
        """
        results = {
            'email': [],
            'slack': [],
            'discord': [],
            'total_sent': 0,
            'total_failed': 0
        }

        with self.db_manager.get_session() as db:
            # Get all email configs with digest enabled
            email_configs = db.query(EmailConfiguration).filter(
                EmailConfiguration.enabled == True,
                EmailConfiguration.enable_digest == True,
                EmailConfiguration.digest_frequency == period
            ).all()

            for config in email_configs:
                # Check if it's time to send (based on digest_time)
                if not self._should_send_digest(config, period):
                    continue

                result = self.create_email_digest(
                    user_id=config.user_id,
                    period=period,
                    repository_id=config.repository_id
                )

                results['email'].append({
                    'user_id': config.user_id,
                    'success': result.get('success', False)
                })

                if result.get('success'):
                    results['total_sent'] += 1
                else:
                    results['total_failed'] += 1

        return results

    def _should_send_digest(
        self,
        config: EmailConfiguration,
        period: str
    ) -> bool:
        """
        Check if digest should be sent now

        Args:
            config: Email configuration
            period: Digest period

        Returns:
            True if should send
        """
        if not config.last_digest_sent:
            return True

        now = datetime.now(timezone.utc)
        last_sent = config.last_digest_sent

        if period == 'daily':
            # Check if more than 24 hours since last sent
            return (now - last_sent).total_seconds() >= 86400
        elif period == 'weekly':
            # Check if more than 7 days since last sent
            return (now - last_sent).total_seconds() >= 604800

        return False

    def _format_notifications_for_email(
        self,
        digest_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Format digest data for email

        Args:
            digest_data: Aggregated digest data

        Returns:
            List of notification dicts for email
        """
        notifications = []

        # Group by type
        for notif_type, items in digest_data['notifications_by_type'].items():
            for item in items:
                notifications.append({
                    'type': notif_type,
                    'title': item.get('title', 'Notification'),
                    'summary': item.get('summary', '')
                })

        return notifications

    def _format_notifications_for_slack(
        self,
        digest_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Format digest data for Slack blocks

        Args:
            digest_data: Aggregated digest data

        Returns:
            List of Slack blocks
        """
        blocks = []

        # Summary section
        summary = digest_data['summary']
        blocks.append({
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': f"*Summary*\n• {summary['total_notifications']} notifications\n• {summary['prs_analyzed']} PRs analyzed\n• {summary['total_issues']} issues found"
            }
        })

        # Critical issues section
        if summary['critical_issues'] > 0:
            blocks.append({
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f"⚠️ *{summary['critical_issues']} Critical Issues*"
                }
            })

        return blocks


# Singleton instance
_digest_service = None


def get_digest_service() -> NotificationDigestService:
    """Get or create NotificationDigestService singleton"""
    global _digest_service
    if _digest_service is None:
        _digest_service = NotificationDigestService()
    return _digest_service
