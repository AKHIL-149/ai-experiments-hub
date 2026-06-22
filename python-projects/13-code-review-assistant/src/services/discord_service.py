"""
Discord Integration Service
Sends notifications to Discord channels via webhooks
"""

import os
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from enum import Enum


class DiscordNotificationType(Enum):
    """Types of Discord notifications"""
    PR_ANALYSIS_COMPLETE = "pr_analysis_complete"
    PR_OPENED = "pr_opened"
    ISSUES_FOUND = "issues_found"
    CRITICAL_ISSUE = "critical_issue"
    ANALYSIS_FAILED = "analysis_failed"
    DEPLOYMENT = "deployment"


class DiscordService:
    """Service for sending notifications to Discord"""

    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize Discord service

        Args:
            webhook_url: Discord webhook URL (defaults to env variable)
        """
        self.webhook_url = webhook_url or os.getenv('DISCORD_WEBHOOK_URL', '')
        self.enabled = bool(self.webhook_url)
        self.timeout = 10  # seconds
        self.username = os.getenv('DISCORD_USERNAME', 'Code Review Assistant')
        self.avatar_url = os.getenv('DISCORD_AVATAR_URL', '')

    def is_configured(self) -> bool:
        """Check if Discord is configured"""
        return self.enabled and bool(self.webhook_url)

    def send_message(
        self,
        content: str,
        embeds: Optional[List[Dict[str, Any]]] = None,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a message to Discord

        Args:
            content: Message content (up to 2000 chars)
            embeds: Discord embeds for rich formatting
            username: Override bot username
            avatar_url: Override bot avatar

        Returns:
            Dict with success status and response
        """
        if not self.is_configured():
            return {
                'success': False,
                'error': 'Discord not configured'
            }

        payload = {
            'content': content[:2000],  # Discord limit
            'username': username or self.username
        }

        if avatar_url or self.avatar_url:
            payload['avatar_url'] = avatar_url or self.avatar_url

        if embeds:
            payload['embeds'] = embeds[:10]  # Discord limit of 10 embeds

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code in [200, 204]:
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
        analysis_url: str
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

        Returns:
            Response dict
        """
        # Determine severity color
        if critical_count > 0:
            color = 0xdc2626  # red
            emoji = '🔴'
            title = 'PR Analysis Complete - Critical Issues Found'
        elif issues_count > 5:
            color = 0xf59e0b  # orange
            emoji = '🟠'
            title = 'PR Analysis Complete - Issues Found'
        elif issues_count > 0:
            color = 0x3b82f6  # blue
            emoji = '🔵'
            title = 'PR Analysis Complete - Minor Issues'
        else:
            color = 0x10b981  # green
            emoji = '✅'
            title = 'PR Analysis Complete - All Clear'

        content = f"{emoji} **PR #{pr_number}** analysis complete for **{repository}**"

        embed = {
            'title': title,
            'description': f'Analysis results are ready for PR #{pr_number}',
            'color': color,
            'fields': [
                {
                    'name': 'Repository',
                    'value': repository,
                    'inline': True
                },
                {
                    'name': 'PR Number',
                    'value': f'#{pr_number}',
                    'inline': True
                },
                {
                    'name': 'Total Issues',
                    'value': str(issues_count),
                    'inline': True
                },
                {
                    'name': 'Critical Issues',
                    'value': str(critical_count),
                    'inline': True
                },
                {
                    'name': 'Links',
                    'value': f'[View Analysis]({analysis_url}) • [View PR]({pr_url})',
                    'inline': False
                }
            ],
            'footer': {
                'text': 'Code Review Assistant'
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return self.send_message(
            content=content,
            embeds=[embed]
        )

    def notify_critical_issue(
        self,
        issue_type: str,
        severity: str,
        file_path: str,
        line_number: int,
        description: str,
        pr_number: Optional[int] = None,
        pr_url: Optional[str] = None
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

        Returns:
            Response dict
        """
        content = f"🚨 **Critical Issue Detected: {issue_type}**"

        pr_info = ''
        if pr_number and pr_url:
            pr_info = f' in [PR #{pr_number}]({pr_url})'

        embed = {
            'title': f'🚨 {issue_type}',
            'description': f'{description}{pr_info}',
            'color': 0xdc2626,  # red
            'fields': [
                {
                    'name': 'File',
                    'value': f'`{file_path}:{line_number}`',
                    'inline': True
                },
                {
                    'name': 'Severity',
                    'value': f'**{severity.upper()}**',
                    'inline': True
                }
            ],
            'footer': {
                'text': 'Code Review Assistant - Action Required'
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return self.send_message(
            content=content,
            embeds=[embed]
        )

    def notify_analysis_failed(
        self,
        pr_number: int,
        repository: str,
        error_message: str,
        pr_url: str
    ) -> Dict[str, Any]:
        """
        Notify that analysis failed

        Args:
            pr_number: PR number
            repository: Repository name
            error_message: Error message
            pr_url: PR URL

        Returns:
            Response dict
        """
        content = f"❌ **Analysis Failed** for PR #{pr_number} in {repository}"

        embed = {
            'title': '❌ Analysis Failed',
            'description': f'The automated code analysis encountered an error',
            'color': 0xdc2626,  # red
            'fields': [
                {
                    'name': 'Repository',
                    'value': repository,
                    'inline': True
                },
                {
                    'name': 'PR Number',
                    'value': f'[#{pr_number}]({pr_url})',
                    'inline': True
                },
                {
                    'name': 'Error',
                    'value': f'```{error_message[:1000]}```',
                    'inline': False
                }
            ],
            'footer': {
                'text': 'Code Review Assistant'
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return self.send_message(
            content=content,
            embeds=[embed]
        )

    def notify_pr_opened(
        self,
        pr_number: int,
        repository: str,
        title: str,
        author: str,
        pr_url: str,
        auto_analyze: bool = True
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

        Returns:
            Response dict
        """
        status = '🔍 Analysis queued' if auto_analyze else '⏳ Waiting for manual trigger'
        content = f"📝 **New Pull Request** in {repository}"

        embed = {
            'title': '📝 New Pull Request',
            'description': f'[{title}]({pr_url})',
            'color': 0x3b82f6,  # blue
            'fields': [
                {
                    'name': 'Repository',
                    'value': repository,
                    'inline': True
                },
                {
                    'name': 'Author',
                    'value': author,
                    'inline': True
                },
                {
                    'name': 'PR Number',
                    'value': f'#{pr_number}',
                    'inline': True
                },
                {
                    'name': 'Status',
                    'value': status,
                    'inline': False
                }
            ],
            'footer': {
                'text': 'Code Review Assistant'
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return self.send_message(
            content=content,
            embeds=[embed]
        )

    def format_issue_summary(
        self,
        issues: List[Dict[str, Any]],
        max_issues: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Format issues for Discord embeds

        Args:
            issues: List of issue dicts
            max_issues: Maximum issues to show

        Returns:
            List of Discord embeds
        """
        embeds = []

        for i, issue in enumerate(issues[:max_issues]):
            severity_emoji = {
                'critical': '🔴',
                'error': '🟠',
                'warning': '🟡',
                'info': '🔵'
            }.get(issue.get('severity', 'info').lower(), '⚪')

            severity_color = {
                'critical': 0xdc2626,
                'error': 0xf59e0b,
                'warning': 0xfbbf24,
                'info': 0x3b82f6
            }.get(issue.get('severity', 'info').lower(), 0x6b7280)

            embed = {
                'title': f'{severity_emoji} {issue.get("type", "Unknown")}',
                'description': issue.get("message", "No description"),
                'color': severity_color,
                'fields': [
                    {
                        'name': 'File',
                        'value': f'`{issue.get("file", "unknown")}:{issue.get("line", 0)}`',
                        'inline': True
                    },
                    {
                        'name': 'Severity',
                        'value': issue.get('severity', 'info').upper(),
                        'inline': True
                    }
                ]
            }
            embeds.append(embed)

        if len(issues) > max_issues:
            embeds.append({
                'description': f'_And {len(issues) - max_issues} more issues..._',
                'color': 0x6b7280
            })

        return embeds


# Singleton instance
_discord_service = None


def get_discord_service() -> DiscordService:
    """Get or create Discord service singleton"""
    global _discord_service
    if _discord_service is None:
        _discord_service = DiscordService()
    return _discord_service
