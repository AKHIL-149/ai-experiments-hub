"""
Notification Rules Engine
Evaluates rules and routes notifications based on conditions
"""

import re
from datetime import datetime, timezone, time as datetime_time
from typing import Dict, List, Optional, Any
from zoneinfo import ZoneInfo

from src.core.database import DatabaseManager, NotificationRule
from src.services.slack_service import get_slack_service
from src.services.email_service import get_email_service
from src.services.discord_service import get_discord_service


class NotificationRulesEngine:
    """Engine for evaluating and executing notification rules"""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize rules engine

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager or DatabaseManager()
        self.slack_service = get_slack_service()
        self.email_service = get_email_service()
        self.discord_service = get_discord_service()

    def evaluate_issue(
        self,
        issue: Dict[str, Any],
        pr_info: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        repository_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Evaluate an issue against all applicable rules

        Args:
            issue: Issue dict with type, severity, category, file, etc.
            pr_info: PR information (number, title, author, etc.)
            user_id: User ID to filter rules
            repository_id: Repository ID to filter rules

        Returns:
            List of actions to execute
        """
        with self.db_manager.get_session() as db:
            # Get applicable rules
            query = db.query(NotificationRule).filter(
                NotificationRule.enabled == True
            )

            if user_id:
                query = query.filter(NotificationRule.user_id == user_id)

            if repository_id:
                query = query.filter(
                    (NotificationRule.repository_id == repository_id) |
                    (NotificationRule.repository_id == None)
                )

            # Sort by priority (lower number = higher priority)
            rules = query.order_by(NotificationRule.priority.asc()).all()

            actions = []
            for rule in rules:
                if self._evaluate_rule(rule, issue, pr_info):
                    action = self._create_action(rule, issue, pr_info)
                    if action:
                        actions.append(action)

            return actions

    def _evaluate_rule(
        self,
        rule: NotificationRule,
        issue: Dict[str, Any],
        pr_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Evaluate if a rule matches the given issue

        Args:
            rule: Notification rule
            issue: Issue dict
            pr_info: PR information

        Returns:
            True if rule matches
        """
        conditions = rule.conditions or {}

        # Check quiet hours
        if rule.quiet_hours_enabled and self._is_quiet_hours(rule.quiet_hours):
            return False

        # Check rate limiting
        if rule.rate_limit_enabled and self._is_rate_limited(rule):
            return False

        # Evaluate severity
        if 'severity' in conditions and conditions['severity']:
            if issue.get('severity') not in conditions['severity']:
                return False

        # Evaluate category
        if 'category' in conditions and conditions['category']:
            if issue.get('category') not in conditions['category']:
                return False

        # Evaluate issue type
        if 'issue_types' in conditions and conditions['issue_types']:
            if issue.get('type') not in conditions['issue_types']:
                return False

        # Evaluate file patterns
        if 'file_patterns' in conditions and conditions['file_patterns']:
            file_path = issue.get('file', '')
            if not self._matches_patterns(file_path, conditions['file_patterns']):
                return False

        # Evaluate PR author
        if pr_info and 'pr_authors' in conditions and conditions['pr_authors']:
            pr_author = pr_info.get('author', '')
            if pr_author not in conditions['pr_authors']:
                return False

        # Evaluate minimum confidence
        if 'min_confidence' in conditions:
            issue_confidence = issue.get('confidence', 100)
            if issue_confidence < conditions['min_confidence']:
                return False

        # All conditions passed
        return True

    def _is_quiet_hours(self, quiet_hours: Dict[str, Any]) -> bool:
        """
        Check if current time is within quiet hours

        Args:
            quiet_hours: Quiet hours configuration

        Returns:
            True if currently in quiet hours
        """
        if not quiet_hours:
            return False

        try:
            # Get timezone
            tz_str = quiet_hours.get('timezone', 'UTC')
            tz = ZoneInfo(tz_str)

            # Get current time in specified timezone
            now = datetime.now(tz)
            current_time = now.time()
            current_day = now.weekday()  # 0=Monday, 6=Sunday

            # Check if current day is in quiet hours days
            quiet_days = quiet_hours.get('days', [0, 1, 2, 3, 4, 5, 6])
            if current_day not in quiet_days:
                return False

            # Parse start and end times
            start_str = quiet_hours.get('start', '22:00')
            end_str = quiet_hours.get('end', '08:00')

            start_hour, start_minute = map(int, start_str.split(':'))
            end_hour, end_minute = map(int, end_str.split(':'))

            start_time = datetime_time(start_hour, start_minute)
            end_time = datetime_time(end_hour, end_minute)

            # Handle overnight quiet hours (e.g., 22:00 to 08:00)
            if start_time <= end_time:
                # Same day
                return start_time <= current_time <= end_time
            else:
                # Overnight
                return current_time >= start_time or current_time <= end_time

        except Exception:
            # If any error in parsing, assume not quiet hours
            return False

    def _is_rate_limited(self, rule: NotificationRule) -> bool:
        """
        Check if rule has exceeded rate limit

        Args:
            rule: Notification rule

        Returns:
            True if rate limited
        """
        if not rule.max_notifications_per_hour:
            return False

        # Check if last triggered was within the last hour
        if not rule.last_triggered_at:
            return False

        hours_since_last = (datetime.now(timezone.utc) - rule.last_triggered_at).total_seconds() / 3600

        if hours_since_last < 1:
            # Within the last hour, check trigger count
            # Note: This is simplified - in production, would track all triggers in the hour
            return rule.trigger_count >= rule.max_notifications_per_hour

        return False

    def _matches_patterns(self, file_path: str, patterns: List[str]) -> bool:
        """
        Check if file path matches any of the given patterns

        Args:
            file_path: File path to check
            patterns: List of glob-style patterns

        Returns:
            True if matches any pattern
        """
        for pattern in patterns:
            # Convert glob pattern to regex
            regex_pattern = pattern.replace('.', '\\.').replace('*', '.*').replace('?', '.')
            if re.match(f'^{regex_pattern}$', file_path):
                return True
        return False

    def _create_action(
        self,
        rule: NotificationRule,
        issue: Dict[str, Any],
        pr_info: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create notification action from rule

        Args:
            rule: Notification rule
            issue: Issue dict
            pr_info: PR information

        Returns:
            Action dict or None
        """
        action = {
            'rule_id': rule.id,
            'rule_name': rule.name,
            'channels': [],
            'issue': issue,
            'pr_info': pr_info,
            'batch': rule.batch_notifications,
            'batch_interval': rule.batch_interval_minutes
        }

        # Add channels
        if rule.notify_slack and rule.slack_config_id:
            action['channels'].append({
                'type': 'slack',
                'config_id': rule.slack_config_id
            })

        if rule.notify_email and rule.email_config_id:
            action['channels'].append({
                'type': 'email',
                'config_id': rule.email_config_id
            })

        if rule.notify_discord and rule.discord_config_id:
            action['channels'].append({
                'type': 'discord',
                'config_id': rule.discord_config_id
            })

        return action if action['channels'] else None

    def execute_action(
        self,
        action: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute notification action

        Args:
            action: Action dict from evaluate_issue
            context: Additional context (PR URL, analysis URL, etc.)

        Returns:
            List of results from each channel
        """
        results = []
        issue = action['issue']
        pr_info = action.get('pr_info', {})
        context = context or {}

        with self.db_manager.get_session() as db:
            for channel in action['channels']:
                channel_type = channel['type']
                config_id = channel['config_id']

                try:
                    if channel_type == 'slack':
                        result = self._send_slack_notification(
                            db, config_id, issue, pr_info, context
                        )
                    elif channel_type == 'email':
                        result = self._send_email_notification(
                            db, config_id, issue, pr_info, context
                        )
                    elif channel_type == 'discord':
                        result = self._send_discord_notification(
                            db, config_id, issue, pr_info, context
                        )
                    else:
                        result = {'success': False, 'error': f'Unknown channel type: {channel_type}'}

                    results.append({
                        'channel': channel_type,
                        'result': result
                    })

                except Exception as e:
                    results.append({
                        'channel': channel_type,
                        'result': {'success': False, 'error': str(e)}
                    })

            # Update rule trigger metadata
            rule = db.query(NotificationRule).filter(
                NotificationRule.id == action['rule_id']
            ).first()

            if rule:
                rule.last_triggered_at = datetime.now(timezone.utc)
                rule.trigger_count = (rule.trigger_count or 0) + 1
                db.commit()

        return results

    def _send_slack_notification(
        self,
        db,
        config_id: str,
        issue: Dict[str, Any],
        pr_info: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send Slack notification"""
        from src.core.database import SlackConfiguration

        config = db.query(SlackConfiguration).filter(
            SlackConfiguration.id == config_id
        ).first()

        if not config:
            return {'success': False, 'error': 'Slack configuration not found'}

        from src.services.slack_service import SlackService
        slack = SlackService(webhook_url=config.webhook_url)

        # Determine notification type based on issue severity
        if issue.get('severity') == 'critical':
            return slack.notify_critical_issue(
                issue_type=issue.get('type', 'Unknown'),
                severity=issue.get('severity', 'error'),
                file_path=issue.get('file', 'unknown'),
                line_number=issue.get('line', 0),
                description=issue.get('message', ''),
                pr_number=pr_info.get('number'),
                pr_url=pr_info.get('url'),
                channel=config.channel
            )
        else:
            # Send as part of PR analysis if PR info available
            if pr_info and context.get('analysis_url'):
                return slack.notify_pr_analysis_complete(
                    pr_number=pr_info.get('number', 0),
                    repository=pr_info.get('repository', ''),
                    issues_count=context.get('issues_count', 1),
                    critical_count=context.get('critical_count', 0),
                    pr_url=pr_info.get('url', ''),
                    analysis_url=context.get('analysis_url', ''),
                    channel=config.channel
                )
            else:
                # Generic issue notification
                return slack.send_message(
                    text=f"Issue found: {issue.get('type', 'Unknown')} in {issue.get('file', 'unknown')}",
                    channel=config.channel
                )

    def _send_email_notification(
        self,
        db,
        config_id: str,
        issue: Dict[str, Any],
        pr_info: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send email notification"""
        from src.core.database import EmailConfiguration

        config = db.query(EmailConfiguration).filter(
            EmailConfiguration.id == config_id
        ).first()

        if not config:
            return {'success': False, 'error': 'Email configuration not found'}

        from src.services.email_service import EmailService
        email = EmailService(
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_username=config.smtp_username,
            smtp_password=config.smtp_password,
            smtp_use_tls=config.smtp_use_tls,
            from_email=config.from_email,
            from_name=config.from_name
        )

        if issue.get('severity') == 'critical':
            return email.notify_critical_issue(
                to_email=config.to_email,
                issue_type=issue.get('type', 'Unknown'),
                severity=issue.get('severity', 'error'),
                file_path=issue.get('file', 'unknown'),
                line_number=issue.get('line', 0),
                description=issue.get('message', ''),
                pr_number=pr_info.get('number'),
                pr_url=pr_info.get('url')
            )
        else:
            if pr_info and context.get('analysis_url'):
                return email.notify_pr_analysis_complete(
                    to_email=config.to_email,
                    pr_number=pr_info.get('number', 0),
                    repository=pr_info.get('repository', ''),
                    issues_count=context.get('issues_count', 1),
                    critical_count=context.get('critical_count', 0),
                    pr_url=pr_info.get('url', ''),
                    analysis_url=context.get('analysis_url', '')
                )
            else:
                # Generic email
                html_body = f"""
                <html>
                <body>
                    <h2>Code Issue Detected</h2>
                    <p><strong>Type:</strong> {issue.get('type', 'Unknown')}</p>
                    <p><strong>Severity:</strong> {issue.get('severity', 'unknown')}</p>
                    <p><strong>File:</strong> {issue.get('file', 'unknown')}:{issue.get('line', 0)}</p>
                    <p><strong>Message:</strong> {issue.get('message', '')}</p>
                </body>
                </html>
                """
                return email.send_email(
                    to_email=config.to_email,
                    subject=f"Code Issue: {issue.get('type', 'Unknown')}",
                    html_body=html_body
                )

    def _send_discord_notification(
        self,
        db,
        config_id: str,
        issue: Dict[str, Any],
        pr_info: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send Discord notification"""
        from src.core.database import DiscordConfiguration

        config = db.query(DiscordConfiguration).filter(
            DiscordConfiguration.id == config_id
        ).first()

        if not config:
            return {'success': False, 'error': 'Discord configuration not found'}

        from src.services.discord_service import DiscordService
        discord = DiscordService(webhook_url=config.webhook_url)

        if issue.get('severity') == 'critical':
            return discord.notify_critical_issue(
                issue_type=issue.get('type', 'Unknown'),
                severity=issue.get('severity', 'error'),
                file_path=issue.get('file', 'unknown'),
                line_number=issue.get('line', 0),
                description=issue.get('message', ''),
                pr_number=pr_info.get('number'),
                pr_url=pr_info.get('url')
            )
        else:
            if pr_info and context.get('analysis_url'):
                return discord.notify_pr_analysis_complete(
                    pr_number=pr_info.get('number', 0),
                    repository=pr_info.get('repository', ''),
                    issues_count=context.get('issues_count', 1),
                    critical_count=context.get('critical_count', 0),
                    pr_url=pr_info.get('url', ''),
                    analysis_url=context.get('analysis_url', '')
                )
            else:
                # Generic Discord message
                return discord.send_message(
                    content=f"🔍 Issue found: {issue.get('type', 'Unknown')} in `{issue.get('file', 'unknown')}`"
                )


# Singleton instance
_rules_engine = None


def get_rules_engine() -> NotificationRulesEngine:
    """Get or create NotificationRulesEngine singleton"""
    global _rules_engine
    if _rules_engine is None:
        _rules_engine = NotificationRulesEngine()
    return _rules_engine
