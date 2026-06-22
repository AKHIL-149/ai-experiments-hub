"""
Email Notification Service
Sends email notifications via SMTP with HTML templates
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from enum import Enum


class EmailNotificationType(Enum):
    """Types of email notifications"""
    PR_ANALYSIS_COMPLETE = "pr_analysis_complete"
    PR_OPENED = "pr_opened"
    CRITICAL_ISSUE = "critical_issue"
    ANALYSIS_FAILED = "analysis_failed"
    DIGEST = "digest"
    WEEKLY_SUMMARY = "weekly_summary"


class EmailService:
    """Service for sending email notifications via SMTP"""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_username: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_use_tls: Optional[bool] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None
    ):
        """
        Initialize Email service

        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port
            smtp_username: SMTP username
            smtp_password: SMTP password
            smtp_use_tls: Use TLS encryption
            from_email: Sender email address
            from_name: Sender display name
        """
        self.smtp_host = smtp_host or os.getenv('SMTP_HOST', '')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = smtp_username or os.getenv('SMTP_USERNAME', '')
        self.smtp_password = smtp_password or os.getenv('SMTP_PASSWORD', '')
        self.smtp_use_tls = smtp_use_tls if smtp_use_tls is not None else os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
        self.from_email = from_email or os.getenv('EMAIL_FROM', 'noreply@codereview.local')
        self.from_name = from_name or os.getenv('EMAIL_FROM_NAME', 'Code Review Assistant')
        self.timeout = 30  # seconds

    def is_configured(self) -> bool:
        """Check if email is configured"""
        return bool(self.smtp_host and self.smtp_username and self.smtp_password)

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an email

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text fallback
            reply_to: Reply-to address

        Returns:
            Dict with success status and response
        """
        if not self.is_configured():
            return {
                'success': False,
                'error': 'Email not configured'
            }

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email

            if reply_to:
                msg['Reply-To'] = reply_to

            # Add text and HTML parts
            if text_body:
                msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            # Connect to SMTP server
            if self.smtp_use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=self.timeout)

            # Login and send
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()

            return {
                'success': True,
                'message': f'Email sent to {to_email}'
            }

        except smtplib.SMTPException as e:
            return {
                'success': False,
                'error': f'SMTP error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def notify_pr_analysis_complete(
        self,
        to_email: str,
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
            to_email: Recipient email
            pr_number: Pull request number
            repository: Repository name
            issues_count: Total issues found
            critical_count: Critical issues count
            pr_url: URL to the PR
            analysis_url: URL to analysis results

        Returns:
            Response dict
        """
        subject = f"PR #{pr_number} Analysis Complete - {repository}"

        # Determine severity color
        if critical_count > 0:
            color = '#dc2626'  # red
            status = 'Critical Issues Found'
            emoji = '🔴'
        elif issues_count > 5:
            color = '#f59e0b'  # orange
            status = 'Issues Found'
            emoji = '🟠'
        elif issues_count > 0:
            color = '#3b82f6'  # blue
            status = 'Minor Issues'
            emoji = '🔵'
        else:
            color = '#10b981'  # green
            status = 'All Clear'
            emoji = '✅'

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: {color}; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb; border-top: none; }}
        .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat {{ flex: 1; background: white; padding: 15px; border-radius: 6px; text-align: center; }}
        .stat-value {{ font-size: 32px; font-weight: bold; color: {color}; }}
        .stat-label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; }}
        .button {{ display: inline-block; background: {color}; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 10px 5px; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{emoji} PR Analysis Complete</h1>
            <p style="margin: 0; opacity: 0.9;">Status: {status}</p>
        </div>
        <div class="content">
            <p>The analysis for <strong>PR #{pr_number}</strong> in <strong>{repository}</strong> has been completed.</p>

            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{issues_count}</div>
                    <div class="stat-label">Total Issues</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{critical_count}</div>
                    <div class="stat-label">Critical</div>
                </div>
            </div>

            <p>
                <a href="{analysis_url}" class="button">View Full Analysis</a>
                <a href="{pr_url}" class="button" style="background: #6b7280;">View Pull Request</a>
            </p>

            <div class="footer">
                <p>This is an automated notification from Code Review Assistant.</p>
                <p>To manage your notification preferences, visit your settings.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

        text_body = f"""
PR Analysis Complete

PR #{pr_number} in {repository}

Status: {status}
Total Issues: {issues_count}
Critical Issues: {critical_count}

View Analysis: {analysis_url}
View PR: {pr_url}

---
This is an automated notification from Code Review Assistant.
"""

        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )

    def notify_critical_issue(
        self,
        to_email: str,
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
            to_email: Recipient email
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
        subject = f"🚨 Critical Issue Detected: {issue_type}"

        pr_info = ''
        if pr_number and pr_url:
            pr_info = f'<p>Found in <a href="{pr_url}">PR #{pr_number}</a></p>'

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #dc2626; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb; border-top: none; }}
        .alert {{ background: #fef2f2; border-left: 4px solid #dc2626; padding: 15px; margin: 20px 0; }}
        .code {{ background: #1f2937; color: #f9fafb; padding: 15px; border-radius: 6px; font-family: monospace; overflow-x: auto; }}
        .detail {{ margin: 10px 0; }}
        .label {{ font-weight: bold; color: #6b7280; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 Critical Issue Detected</h1>
            <p style="margin: 0; opacity: 0.9;">{issue_type}</p>
        </div>
        <div class="content">
            {pr_info}

            <div class="alert">
                <strong>{issue_type}</strong>
                <p>{description}</p>
            </div>

            <div class="detail">
                <span class="label">File:</span> <code>{file_path}:{line_number}</code>
            </div>
            <div class="detail">
                <span class="label">Severity:</span> <span style="color: #dc2626; font-weight: bold;">{severity.upper()}</span>
            </div>

            <div class="footer">
                <p><strong>Action Required:</strong> Please review and address this issue immediately.</p>
                <p>This is an automated notification from Code Review Assistant.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

        text_body = f"""
Critical Issue Detected

{issue_type}

{description}

File: {file_path}:{line_number}
Severity: {severity.upper()}

Action Required: Please review and address this issue immediately.

---
This is an automated notification from Code Review Assistant.
"""

        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )

    def notify_analysis_failed(
        self,
        to_email: str,
        pr_number: int,
        repository: str,
        error_message: str,
        pr_url: str
    ) -> Dict[str, Any]:
        """
        Notify that analysis failed

        Args:
            to_email: Recipient email
            pr_number: PR number
            repository: Repository name
            error_message: Error message
            pr_url: PR URL

        Returns:
            Response dict
        """
        subject = f"Analysis Failed - PR #{pr_number} in {repository}"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #dc2626; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb; border-top: none; }}
        .error {{ background: #fef2f2; border: 1px solid #fecaca; padding: 15px; border-radius: 6px; margin: 20px 0; }}
        .button {{ display: inline-block; background: #6b7280; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 10px 0; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>❌ Analysis Failed</h1>
            <p style="margin: 0; opacity: 0.9;">PR #{pr_number} in {repository}</p>
        </div>
        <div class="content">
            <p>The automated code analysis for PR #{pr_number} in <strong>{repository}</strong> has failed.</p>

            <div class="error">
                <strong>Error:</strong>
                <pre style="margin: 10px 0; white-space: pre-wrap;">{error_message}</pre>
            </div>

            <p>
                <a href="{pr_url}" class="button">View Pull Request</a>
            </p>

            <div class="footer">
                <p>Please check the error message above and try again, or contact support if the issue persists.</p>
                <p>This is an automated notification from Code Review Assistant.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

        text_body = f"""
Analysis Failed

PR #{pr_number} in {repository}

Error:
{error_message}

View PR: {pr_url}

Please check the error message above and try again, or contact support if the issue persists.

---
This is an automated notification from Code Review Assistant.
"""

        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )

    def notify_pr_opened(
        self,
        to_email: str,
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
            to_email: Recipient email
            pr_number: PR number
            repository: Repository name
            title: PR title
            author: PR author
            pr_url: PR URL
            auto_analyze: Whether auto-analysis is enabled

        Returns:
            Response dict
        """
        subject = f"New PR #{pr_number} - {repository}"

        status_text = '🔍 Analysis queued' if auto_analyze else '⏳ Waiting for manual trigger'

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #3b82f6; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb; border-top: none; }}
        .detail {{ margin: 10px 0; }}
        .label {{ font-weight: bold; color: #6b7280; }}
        .button {{ display: inline-block; background: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 10px 0; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📝 New Pull Request</h1>
            <p style="margin: 0; opacity: 0.9;">{status_text}</p>
        </div>
        <div class="content">
            <h2 style="margin-top: 0;">{title}</h2>

            <div class="detail">
                <span class="label">Repository:</span> {repository}
            </div>
            <div class="detail">
                <span class="label">Author:</span> {author}
            </div>
            <div class="detail">
                <span class="label">PR Number:</span> #{pr_number}
            </div>

            <p>
                <a href="{pr_url}" class="button">View Pull Request</a>
            </p>

            <div class="footer">
                <p>This is an automated notification from Code Review Assistant.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

        text_body = f"""
New Pull Request

{title}

Repository: {repository}
Author: {author}
PR Number: #{pr_number}

Status: {status_text}

View PR: {pr_url}

---
This is an automated notification from Code Review Assistant.
"""

        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )

    def send_digest(
        self,
        to_email: str,
        notifications: List[Dict[str, Any]],
        period: str = 'daily'
    ) -> Dict[str, Any]:
        """
        Send a digest of multiple notifications

        Args:
            to_email: Recipient email
            notifications: List of notification dicts
            period: Digest period (daily, weekly)

        Returns:
            Response dict
        """
        subject = f"Code Review Digest - {period.capitalize()}"

        # Group by type
        pr_opened = [n for n in notifications if n.get('type') == 'pr_opened']
        pr_complete = [n for n in notifications if n.get('type') == 'pr_analysis_complete']
        critical = [n for n in notifications if n.get('type') == 'critical_issue']
        failed = [n for n in notifications if n.get('type') == 'analysis_failed']

        stats_html = f"""
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{len(pr_opened)}</div>
                    <div class="stat-label">PRs Opened</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{len(pr_complete)}</div>
                    <div class="stat-label">Analyses Complete</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{len(critical)}</div>
                    <div class="stat-label">Critical Issues</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{len(failed)}</div>
                    <div class="stat-label">Failures</div>
                </div>
            </div>
"""

        items_html = ""
        for notification in notifications[:20]:  # Limit to 20 items
            items_html += f"""
            <div class="digest-item">
                <strong>{notification.get('title', 'Notification')}</strong>
                <p style="margin: 5px 0; color: #6b7280; font-size: 14px;">{notification.get('summary', '')}</p>
            </div>
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #6366f1; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb; border-top: none; }}
        .stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0; }}
        .stat {{ background: white; padding: 15px; border-radius: 6px; text-align: center; }}
        .stat-value {{ font-size: 32px; font-weight: bold; color: #6366f1; }}
        .stat-label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; }}
        .digest-item {{ background: white; padding: 15px; border-left: 3px solid #6366f1; margin: 10px 0; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 {period.capitalize()} Digest</h1>
            <p style="margin: 0; opacity: 0.9;">Your code review summary</p>
        </div>
        <div class="content">
            <p>Here's your {period} summary of code review activity:</p>

            {stats_html}

            <h3>Recent Activity</h3>
            {items_html}

            <div class="footer">
                <p>This is an automated digest from Code Review Assistant.</p>
                <p>To manage your notification preferences, visit your settings.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body
        )


# Singleton instance
_email_service = None


def get_email_service() -> EmailService:
    """Get or create Email service singleton"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
