"""
Notification Worker
Celery tasks for batch notification processing and digest generation
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import logging

from celery_app import celery_app
from src.core.database import DatabaseManager
from src.services.notification_digest_service import get_digest_service
from src.services.notification_rules_engine import get_rules_engine

logger = logging.getLogger(__name__)


@celery_app.task(name='notification_worker.process_batch_notifications')
def process_batch_notifications(
    notifications: List[Dict[str, Any]],
    batch_interval_minutes: int = 60
) -> Dict[str, Any]:
    """
    Process batch notifications

    Args:
        notifications: List of notification dicts
        batch_interval_minutes: Batch interval in minutes

    Returns:
        Processing result
    """
    try:
        logger.info(f"Processing batch of {len(notifications)} notifications")

        # Group notifications by user and channel
        batches = _group_notifications_by_user_and_channel(notifications)

        results = {
            'total_batches': len(batches),
            'successful': 0,
            'failed': 0,
            'details': []
        }

        # Process each batch
        for batch_key, batch_notifications in batches.items():
            try:
                user_id, channel_type, config_id = batch_key

                # Send batched notification
                result = _send_batched_notification(
                    user_id=user_id,
                    channel_type=channel_type,
                    config_id=config_id,
                    notifications=batch_notifications
                )

                if result.get('success'):
                    results['successful'] += 1
                else:
                    results['failed'] += 1

                results['details'].append({
                    'batch_key': batch_key,
                    'count': len(batch_notifications),
                    'result': result
                })

            except Exception as e:
                logger.error(f"Error processing batch {batch_key}: {str(e)}")
                results['failed'] += 1
                results['details'].append({
                    'batch_key': batch_key,
                    'error': str(e)
                })

        logger.info(f"Batch processing complete: {results['successful']} successful, {results['failed']} failed")
        return results

    except Exception as e:
        logger.error(f"Error in batch notification processing: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


@celery_app.task(name='notification_worker.send_daily_digests')
def send_daily_digests() -> Dict[str, Any]:
    """
    Send daily notification digests

    Returns:
        Result summary
    """
    try:
        logger.info("Starting daily digest sending")
        digest_service = get_digest_service()

        results = digest_service.send_all_digests(period='daily')

        logger.info(f"Daily digests sent: {results['total_sent']} successful, {results['total_failed']} failed")
        return results

    except Exception as e:
        logger.error(f"Error sending daily digests: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


@celery_app.task(name='notification_worker.send_weekly_digests')
def send_weekly_digests() -> Dict[str, Any]:
    """
    Send weekly notification digests

    Returns:
        Result summary
    """
    try:
        logger.info("Starting weekly digest sending")
        digest_service = get_digest_service()

        results = digest_service.send_all_digests(period='weekly')

        logger.info(f"Weekly digests sent: {results['total_sent']} successful, {results['total_failed']} failed")
        return results

    except Exception as e:
        logger.error(f"Error sending weekly digests: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


@celery_app.task(name='notification_worker.send_user_digest')
def send_user_digest(
    user_id: str,
    period: str = 'daily',
    repository_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send digest for specific user

    Args:
        user_id: User ID
        period: Digest period (daily, weekly)
        repository_id: Optional repository filter

    Returns:
        Result dict
    """
    try:
        logger.info(f"Sending {period} digest for user {user_id}")
        digest_service = get_digest_service()

        result = digest_service.create_email_digest(
            user_id=user_id,
            period=period,
            repository_id=repository_id
        )

        return result

    except Exception as e:
        logger.error(f"Error sending user digest: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


@celery_app.task(name='notification_worker.queue_notification')
def queue_notification(
    issue: Dict[str, Any],
    pr_info: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    repository_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Queue a notification for processing

    Args:
        issue: Issue dict
        pr_info: PR information
        user_id: User ID
        repository_id: Repository ID
        context: Additional context

    Returns:
        Result dict
    """
    try:
        logger.info(f"Queuing notification for issue: {issue.get('type', 'unknown')}")
        rules_engine = get_rules_engine()

        # Evaluate rules
        actions = rules_engine.evaluate_issue(
            issue=issue,
            pr_info=pr_info,
            user_id=user_id,
            repository_id=repository_id
        )

        # Separate immediate and batched notifications
        immediate_actions = []
        batched_actions = []

        for action in actions:
            if action.get('batch', False):
                batched_actions.append(action)
            else:
                immediate_actions.append(action)

        # Execute immediate notifications
        immediate_results = []
        for action in immediate_actions:
            result = rules_engine.execute_action(action, context)
            immediate_results.append(result)

        # Queue batched notifications for later processing
        if batched_actions:
            batch_interval = batched_actions[0].get('batch_interval', 60)
            # Schedule batch processing
            process_batch_notifications.apply_async(
                args=[batched_actions, batch_interval],
                countdown=batch_interval * 60  # Convert to seconds
            )

        return {
            'success': True,
            'immediate_count': len(immediate_actions),
            'batched_count': len(batched_actions),
            'immediate_results': immediate_results
        }

    except Exception as e:
        logger.error(f"Error queuing notification: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


def _group_notifications_by_user_and_channel(
    notifications: List[Dict[str, Any]]
) -> Dict[tuple, List[Dict[str, Any]]]:
    """
    Group notifications by user and channel

    Args:
        notifications: List of notification dicts

    Returns:
        Dict mapping (user_id, channel_type, config_id) to list of notifications
    """
    batches = {}

    for notification in notifications:
        for channel in notification.get('channels', []):
            # Extract user ID from notification (would be set by rules engine)
            user_id = notification.get('user_id', 'unknown')
            channel_type = channel['type']
            config_id = channel['config_id']

            batch_key = (user_id, channel_type, config_id)

            if batch_key not in batches:
                batches[batch_key] = []

            batches[batch_key].append(notification)

    return batches


def _send_batched_notification(
    user_id: str,
    channel_type: str,
    config_id: str,
    notifications: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Send batched notification to specific channel

    Args:
        user_id: User ID
        channel_type: Channel type (slack, email, discord)
        config_id: Configuration ID
        notifications: List of notifications to batch

    Returns:
        Result dict
    """
    from src.services.slack_service import SlackService
    from src.services.email_service import EmailService
    from src.services.discord_service import DiscordService
    from src.core.database import (
        SlackConfiguration,
        EmailConfiguration,
        DiscordConfiguration,
        DatabaseManager
    )

    db_manager = DatabaseManager()

    try:
        with db_manager.get_session() as db:
            if channel_type == 'slack':
                config = db.query(SlackConfiguration).filter(
                    SlackConfiguration.id == config_id
                ).first()

                if not config:
                    return {'success': False, 'error': 'Slack config not found'}

                slack = SlackService(webhook_url=config.webhook_url)

                # Create summary message
                message = f"📦 *Batched Notifications* ({len(notifications)} items)\n\n"
                for notif in notifications[:5]:  # Show first 5
                    issue = notif['issue']
                    message += f"• {issue.get('type', 'Unknown')} in `{issue.get('file', 'unknown')}`\n"

                if len(notifications) > 5:
                    message += f"\n_...and {len(notifications) - 5} more_"

                return slack.send_message(text=message, channel=config.channel)

            elif channel_type == 'email':
                config = db.query(EmailConfiguration).filter(
                    EmailConfiguration.id == config_id
                ).first()

                if not config:
                    return {'success': False, 'error': 'Email config not found'}

                email = EmailService(
                    smtp_host=config.smtp_host,
                    smtp_port=config.smtp_port,
                    smtp_username=config.smtp_username,
                    smtp_password=config.smtp_password,
                    smtp_use_tls=config.smtp_use_tls,
                    from_email=config.from_email
                )

                # Format notifications for email
                formatted_notifications = []
                for notif in notifications:
                    issue = notif['issue']
                    formatted_notifications.append({
                        'type': issue.get('type', 'Unknown'),
                        'title': f"{issue.get('type', 'Unknown')} in {issue.get('file', 'unknown')}",
                        'summary': issue.get('message', '')
                    })

                html_body = _create_batch_email_html(formatted_notifications)

                return email.send_email(
                    to_email=config.to_email,
                    subject=f"Batched Code Review Notifications ({len(notifications)} items)",
                    html_body=html_body
                )

            elif channel_type == 'discord':
                config = db.query(DiscordConfiguration).filter(
                    DiscordConfiguration.id == config_id
                ).first()

                if not config:
                    return {'success': False, 'error': 'Discord config not found'}

                discord = DiscordService(webhook_url=config.webhook_url)

                content = f"📦 **Batched Notifications** ({len(notifications)} items)"

                embed = {
                    'title': 'Batched Code Review Notifications',
                    'description': f'{len(notifications)} notifications batched together',
                    'color': 0x3b82f6,
                    'fields': [],
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }

                # Add first 10 notifications as fields
                for i, notif in enumerate(notifications[:10]):
                    issue = notif['issue']
                    embed['fields'].append({
                        'name': f"{i+1}. {issue.get('type', 'Unknown')}",
                        'value': f"`{issue.get('file', 'unknown')}:{issue.get('line', 0)}`",
                        'inline': False
                    })

                if len(notifications) > 10:
                    embed['fields'].append({
                        'name': 'More Items',
                        'value': f'_...and {len(notifications) - 10} more notifications_',
                        'inline': False
                    })

                return discord.send_message(content=content, embeds=[embed])

            else:
                return {'success': False, 'error': f'Unknown channel type: {channel_type}'}

    except Exception as e:
        logger.error(f"Error sending batched notification: {str(e)}")
        return {'success': False, 'error': str(e)}


def _create_batch_email_html(notifications: List[Dict[str, Any]]) -> str:
    """
    Create HTML for batch email

    Args:
        notifications: List of formatted notification dicts

    Returns:
        HTML string
    """
    html = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .header { background-color: #3b82f6; color: white; padding: 20px; text-align: center; }
            .content { padding: 20px; }
            .notification { border-left: 4px solid #3b82f6; padding: 10px; margin: 10px 0; background-color: #f9fafb; }
            .notification-title { font-weight: bold; color: #1f2937; }
            .notification-summary { color: #6b7280; margin-top: 5px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h2>Batched Code Review Notifications</h2>
            <p>""" + str(len(notifications)) + """ notifications</p>
        </div>
        <div class="content">
    """

    for notif in notifications:
        html += f"""
            <div class="notification">
                <div class="notification-title">{notif.get('title', 'Notification')}</div>
                <div class="notification-summary">{notif.get('summary', '')}</div>
            </div>
        """

    html += """
        </div>
    </body>
    </html>
    """

    return html
