"""
Slack Integration Service
Sends notifications to Slack channels via webhooks
"""

import os
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class SlackNotificationType(Enum):
    """Types of Slack notifications"""
    PR_ANALYSIS_COMPLETE = "pr_analysis_complete"
    PR_OPENED = "pr_opened"
    ISSUES_FOUND = "issues_found"
    CRITICAL_ISSUE = "critical_issue"
    ANALYSIS_FAILED = "analysis_failed"
    DEPLOYMENT = "deployment"


class SlackService:
    """Service for sending notifications to Slack"""

    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize Slack service

        Args:
            webhook_url: Slack webhook URL (defaults to env variable)
        """
        self.webhook_url = webhook_url or os.getenv('SLACK_WEBHOOK_URL', '')
        self.default_channel = os.getenv('SLACK_DEFAULT_CHANNEL', '')
        self.enabled = bool(self.webhook_url)
        self.timeout = 10  # seconds

    def is_configured(self) -> bool:
        """Check if Slack is configured"""
        return self.enabled and bool(self.webhook_url)

    def send_message(
        self,
        text: str,
        blocks: Optional[List[Dict[str, Any]]] = None,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
        username: Optional[str] = None,
        icon_emoji: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a message to Slack

        Args:
            text: Plain text message (fallback)
            blocks: Slack blocks for rich formatting
            channel: Channel to post to (overrides default)
            thread_ts: Thread timestamp for replies
            username: Bot username
            icon_emoji: Bot icon emoji

        Returns:
            Dict with success status and response
        """
        if not self.is_configured():
            return {
                'success': False,
                'error': 'Slack not configured'
            }

        payload = {
            'text': text
        }

        if blocks:
            payload['blocks'] = blocks

        if channel or self.default_channel:
            payload['channel'] = channel or self.default_channel

        if thread_ts:
            payload['thread_ts'] = thread_ts

        if username:
            payload['username'] = username or 'Code Review Assistant'

        if icon_emoji:
            payload['icon_emoji'] = icon_emoji or ':robot_face:'

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 200:
                return {
                    'success': True,
                    'response': response.text
                }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text}'
                }

        except requests.RequestException as e:
            return {
                'success': False,
                'error': str(e)
            }

    def notify_pr_analysis_complete(
        self,
        pr_number: int,
        repository: str,
        issues_count: int,
        critical_count: int,
        pr_url: str,
        analysis_url: str,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Notify that PR analysis is complete

        Args:
            pr_number: Pull request number
            repository: Repository name
            issues_count: Total issues found
            critical_count: Critical issues count
            pr_url: URL to the PR
            analysis_url: URL to analysis results
            channel: Slack channel
            thread_ts: Thread timestamp

        Returns:
            Response dict
        """
        # Determine severity color
        if critical_count > 0:
            color = '#dc2626'  # red
            emoji = ':x:'
        elif issues_count > 5:
            color = '#f59e0b'  # orange
            emoji = ':warning:'
        elif issues_count > 0:
            color = '#3b82f6'  # blue
            emoji = ':information_source:'
        else:
            color = '#10b981'  # green
            emoji = ':white_check_mark:'

        text = f"PR #{pr_number} analysis complete for {repository}"

        blocks = [
            {
                'type': 'header',
                'text': {
                    'type': 'plain_text',
                    'text': f'{emoji} PR Analysis Complete',
                    'emoji': True
                }
            },
            {
                'type': 'section',
                'fields': [
                    {
                        'type': 'mrkdwn',
                        'text': f'*Repository:*\n{repository}'
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f'*PR:*\n<{pr_url}|#{pr_number}>'
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f'*Issues Found:*\n{issues_count}'
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f'*Critical Issues:*\n{critical_count}'
                    }
                ]
            },
            {
                'type': 'actions',
                'elements': [
                    {
                        'type': 'button',
                        'text': {
                            'type': 'plain_text',
                            'text': 'View Analysis',
                            'emoji': True
                        },
                        'url': analysis_url,
                        'style': 'primary'
                    },
                    {
                        'type': 'button',
                        'text': {
                            'type': 'plain_text',
                            'text': 'View PR',
                            'emoji': True
                        },
                        'url': pr_url
                    }
                ]
            }
        ]

        return self.send_message(
            text=text,
            blocks=blocks,
            channel=channel,
            thread_ts=thread_ts
        )

    def notify_critical_issue(
        self,
        issue_type: str,
        severity: str,
        file_path: str,
        line_number: int,
        description: str,
        pr_number: Optional[int] = None,
        pr_url: Optional[str] = None,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Notify about a critical issue found

        Args:
            issue_type: Type of issue
            severity: Severity level
            file_path: File path
            line_number: Line number
            description: Issue description
            pr_number: PR number (optional)
            pr_url: PR URL (optional)
            channel: Slack channel
            thread_ts: Thread timestamp

        Returns:
            Response dict
        """
        text = f"Critical issue found: {issue_type}"

        pr_info = ''
        if pr_number and pr_url:
            pr_info = f' in <{pr_url}|PR #{pr_number}>'

        blocks = [
            {
                'type': 'header',
                'text': {
                    'type': 'plain_text',
                    'text': ':rotating_light: Critical Issue Detected',
                    'emoji': True
                }
            },
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f'*{issue_type}*{pr_info}\n{description}'
                }
            },
            {
                'type': 'section',
                'fields': [
                    {
                        'type': 'mrkdwn',
                        'text': f'*File:*\n`{file_path}:{line_number}`'
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f'*Severity:*\n{severity.upper()}'
                    }
                ]
            }
        ]

        return self.send_message(
            text=text,
            blocks=blocks,
            channel=channel,
            thread_ts=thread_ts
        )

    def notify_analysis_failed(
        self,
        pr_number: int,
        repository: str,
        error_message: str,
        pr_url: str,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Notify that analysis failed

        Args:
            pr_number: PR number
            repository: Repository name
            error_message: Error message
            pr_url: PR URL
            channel: Slack channel
            thread_ts: Thread timestamp

        Returns:
            Response dict
        """
        text = f"Analysis failed for PR #{pr_number} in {repository}"

        blocks = [
            {
                'type': 'header',
                'text': {
                    'type': 'plain_text',
                    'text': ':x: Analysis Failed',
                    'emoji': True
                }
            },
            {
                'type': 'section',
                'fields': [
                    {
                        'type': 'mrkdwn',
                        'text': f'*Repository:*\n{repository}'
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f'*PR:*\n<{pr_url}|#{pr_number}>'
                    }
                ]
            },
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f'*Error:*\n```{error_message}```'
                }
            }
        ]

        return self.send_message(
            text=text,
            blocks=blocks,
            channel=channel,
            thread_ts=thread_ts
        )

    def notify_pr_opened(
        self,
        pr_number: int,
        repository: str,
        title: str,
        author: str,
        pr_url: str,
        auto_analyze: bool = True,
        channel: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Notify that a new PR was opened

        Args:
            pr_number: PR number
            repository: Repository name
            title: PR title
            author: PR author
            pr_url: PR URL
            auto_analyze: Whether auto-analysis is enabled
            channel: Slack channel

        Returns:
            Response dict with thread_ts for future replies
        """
        text = f"New PR #{pr_number} opened in {repository}"

        status_text = ':mag: Analysis queued...' if auto_analyze else ':hourglass: Waiting for manual trigger'

        blocks = [
            {
                'type': 'header',
                'text': {
                    'type': 'plain_text',
                    'text': ':new: New Pull Request',
                    'emoji': True
                }
            },
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f'*<{pr_url}|{title}>*\n{status_text}'
                }
            },
            {
                'type': 'section',
                'fields': [
                    {
                        'type': 'mrkdwn',
                        'text': f'*Repository:*\n{repository}'
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f'*Author:*\n{author}'
                    },
                    {
                        'type': 'mrkdwn',
                        'text': f'*PR Number:*\n#{pr_number}'
                    }
                ]
            }
        ]

        return self.send_message(
            text=text,
            blocks=blocks,
            channel=channel
        )

    def format_issue_summary(
        self,
        issues: List[Dict[str, Any]],
        max_issues: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Format issues for Slack blocks

        Args:
            issues: List of issue dicts
            max_issues: Maximum issues to show

        Returns:
            List of Slack blocks
        """
        blocks = []

        for i, issue in enumerate(issues[:max_issues]):
            severity_emoji = {
                'critical': ':red_circle:',
                'error': ':orange_circle:',
                'warning': ':yellow_circle:',
                'info': ':large_blue_circle:'
            }.get(issue.get('severity', 'info').lower(), ':white_circle:')

            blocks.append({
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f'{severity_emoji} *{issue.get("type", "Unknown")}* in `{issue.get("file", "unknown")}:{issue.get("line", 0)}`\n{issue.get("message", "No description")}'
                }
            })

        if len(issues) > max_issues:
            blocks.append({
                'type': 'context',
                'elements': [
                    {
                        'type': 'mrkdwn',
                        'text': f'_And {len(issues) - max_issues} more issues..._'
                    }
                ]
            })

        return blocks


# Singleton instance
_slack_service = None


def get_slack_service() -> SlackService:
    """Get or create Slack service singleton"""
    global _slack_service
    if _slack_service is None:
        _slack_service = SlackService()
    return _slack_service
