"""
Alert Management Service

Manages alerts, notifications, and escalations across the multi-agent system.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid


class AlertType:
    """Alert type constants"""
    PERFORMANCE = "performance"
    COST = "cost"
    SYSTEM = "system"
    WORKFLOW = "workflow"
    AGENT = "agent"
    SECURITY = "security"
    RESOURCE = "resource"
    CUSTOM = "custom"


class AlertSeverity:
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus:
    """Alert status"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SILENCED = "silenced"
    EXPIRED = "expired"


class NotificationChannel:
    """Notification channel types"""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    SMS = "sms"
    PAGERDUTY = "pagerduty"
    IN_APP = "in_app"


class AlertManagement:
    """Alert Management service for notifications and escalations"""

    # In-memory storage
    _alerts = {}
    _alert_rules = {}
    _notification_channels = {}
    _escalation_policies = {}
    _silences = {}
    _alert_history = defaultdict(list)
    _notification_history = defaultdict(list)

    @staticmethod
    def create_alert(
        session,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        source: Optional[str] = None,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        details: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a new alert.

        Args:
            session: Database session
            alert_type: Type of alert
            severity: Alert severity level
            title: Alert title
            description: Detailed description
            source: Alert source system
            agent_id: Related agent ID
            workflow_id: Related workflow ID
            details: Alert details and context
            metadata: Additional metadata

        Returns:
            Created alert
        """
        alert_id = f"alert_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        alert = {
            "id": alert_id,
            "alert_type": alert_type,
            "severity": severity,
            "status": AlertStatus.ACTIVE,
            "title": title,
            "description": description,
            "source": source,
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "details": details or {},
            "metadata": metadata or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "acknowledged_at": None,
            "acknowledged_by": None,
            "resolved_at": None,
            "resolved_by": None,
            "notification_sent": False,
            "notification_count": 0,
            "escalation_level": 0
        }

        AlertManagement._alerts[alert_id] = alert
        AlertManagement._alert_history[alert_id].append({
            "timestamp": now.isoformat(),
            "action": "created",
            "details": {"severity": severity, "status": AlertStatus.ACTIVE}
        })

        # Check if alert should be sent based on rules
        AlertManagement._process_alert_rules(session, alert)

        # Check if alert should be silenced
        if AlertManagement._is_silenced(alert):
            alert["status"] = AlertStatus.SILENCED

        # Send notifications if not silenced
        if alert["status"] != AlertStatus.SILENCED:
            AlertManagement._send_notifications(session, alert)

        return alert

    @staticmethod
    def acknowledge_alert(
        session,
        alert_id: str,
        acknowledged_by: str,
        notes: Optional[str] = None
    ) -> dict:
        """
        Acknowledge an alert.

        Args:
            session: Database session
            alert_id: Alert ID
            acknowledged_by: User/system acknowledging
            notes: Optional acknowledgment notes

        Returns:
            Updated alert
        """
        alert = AlertManagement._alerts.get(alert_id)
        if not alert:
            raise ValueError(f"Alert not found: {alert_id}")

        if alert["status"] not in [AlertStatus.ACTIVE]:
            raise ValueError(f"Cannot acknowledge alert in status: {alert['status']}")

        now = datetime.utcnow()
        alert["status"] = AlertStatus.ACKNOWLEDGED
        alert["acknowledged_at"] = now.isoformat()
        alert["acknowledged_by"] = acknowledged_by
        alert["updated_at"] = now.isoformat()

        if notes:
            alert["metadata"]["acknowledgment_notes"] = notes

        AlertManagement._alert_history[alert_id].append({
            "timestamp": now.isoformat(),
            "action": "acknowledged",
            "details": {"acknowledged_by": acknowledged_by, "notes": notes}
        })

        return alert

    @staticmethod
    def resolve_alert(
        session,
        alert_id: str,
        resolved_by: str,
        resolution_notes: Optional[str] = None
    ) -> dict:
        """
        Resolve an alert.

        Args:
            session: Database session
            alert_id: Alert ID
            resolved_by: User/system resolving
            resolution_notes: Resolution notes

        Returns:
            Updated alert
        """
        alert = AlertManagement._alerts.get(alert_id)
        if not alert:
            raise ValueError(f"Alert not found: {alert_id}")

        now = datetime.utcnow()
        alert["status"] = AlertStatus.RESOLVED
        alert["resolved_at"] = now.isoformat()
        alert["resolved_by"] = resolved_by
        alert["updated_at"] = now.isoformat()

        if resolution_notes:
            alert["metadata"]["resolution_notes"] = resolution_notes

        AlertManagement._alert_history[alert_id].append({
            "timestamp": now.isoformat(),
            "action": "resolved",
            "details": {"resolved_by": resolved_by, "notes": resolution_notes}
        })

        return alert

    @staticmethod
    def create_alert_rule(
        session,
        name: str,
        alert_type: str,
        condition: dict,
        severity: str,
        notification_channels: List[str],
        description: Optional[str] = None,
        enabled: bool = True,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create an alert rule.

        Args:
            session: Database session
            name: Rule name
            alert_type: Type of alert to trigger
            condition: Rule condition/threshold
            severity: Alert severity
            notification_channels: Channels to notify
            description: Rule description
            enabled: Whether rule is enabled
            metadata: Additional metadata

        Returns:
            Created alert rule
        """
        rule_id = f"rule_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        rule = {
            "id": rule_id,
            "name": name,
            "alert_type": alert_type,
            "condition": condition,
            "severity": severity,
            "notification_channels": notification_channels,
            "description": description,
            "enabled": enabled,
            "metadata": metadata or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "triggered_count": 0,
            "last_triggered_at": None
        }

        AlertManagement._alert_rules[rule_id] = rule
        return rule

    @staticmethod
    def create_notification_channel(
        session,
        name: str,
        channel_type: str,
        config: dict,
        enabled: bool = True,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a notification channel.

        Args:
            session: Database session
            name: Channel name
            channel_type: Type of channel (email, slack, etc.)
            config: Channel configuration
            enabled: Whether channel is enabled
            metadata: Additional metadata

        Returns:
            Created notification channel
        """
        channel_id = f"channel_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        channel = {
            "id": channel_id,
            "name": name,
            "channel_type": channel_type,
            "config": config,
            "enabled": enabled,
            "metadata": metadata or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "notification_count": 0,
            "last_notification_at": None
        }

        AlertManagement._notification_channels[channel_id] = channel
        return channel

    @staticmethod
    def create_escalation_policy(
        session,
        name: str,
        alert_type: str,
        severity: str,
        escalation_steps: List[dict],
        description: Optional[str] = None,
        enabled: bool = True
    ) -> dict:
        """
        Create an escalation policy.

        Args:
            session: Database session
            name: Policy name
            alert_type: Alert type to apply to
            severity: Minimum severity level
            escalation_steps: List of escalation steps
            description: Policy description
            enabled: Whether policy is enabled

        Returns:
            Created escalation policy
        """
        policy_id = f"policy_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        policy = {
            "id": policy_id,
            "name": name,
            "alert_type": alert_type,
            "severity": severity,
            "escalation_steps": escalation_steps,
            "description": description,
            "enabled": enabled,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "triggered_count": 0
        }

        AlertManagement._escalation_policies[policy_id] = policy
        return policy

    @staticmethod
    def create_silence(
        session,
        alert_type: Optional[str] = None,
        severity: Optional[str] = None,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        duration_minutes: int = 60,
        reason: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> dict:
        """
        Create an alert silence.

        Args:
            session: Database session
            alert_type: Alert type to silence
            severity: Severity level to silence
            agent_id: Agent ID to silence
            workflow_id: Workflow ID to silence
            duration_minutes: Silence duration
            reason: Reason for silence
            created_by: User creating silence

        Returns:
            Created silence
        """
        silence_id = f"silence_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=duration_minutes)

        silence = {
            "id": silence_id,
            "alert_type": alert_type,
            "severity": severity,
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "duration_minutes": duration_minutes,
            "reason": reason,
            "created_by": created_by,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "is_active": True,
            "silenced_count": 0
        }

        AlertManagement._silences[silence_id] = silence
        return silence

    @staticmethod
    def get_alert(session, alert_id: str) -> dict:
        """Get alert details"""
        alert = AlertManagement._alerts.get(alert_id)
        if not alert:
            raise ValueError(f"Alert not found: {alert_id}")

        # Include history
        alert["history"] = AlertManagement._alert_history.get(alert_id, [])
        return alert

    @staticmethod
    def list_alerts(
        session,
        alert_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """
        List alerts with filtering.

        Args:
            session: Database session
            alert_type: Filter by alert type
            severity: Filter by severity
            status: Filter by status
            agent_id: Filter by agent
            workflow_id: Filter by workflow
            limit: Maximum alerts to return

        Returns:
            Filtered alerts and statistics
        """
        alerts = list(AlertManagement._alerts.values())

        # Apply filters
        if alert_type:
            alerts = [a for a in alerts if a["alert_type"] == alert_type]
        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]
        if status:
            alerts = [a for a in alerts if a["status"] == status]
        if agent_id is not None:
            alerts = [a for a in alerts if a["agent_id"] == agent_id]
        if workflow_id:
            alerts = [a for a in alerts if a["workflow_id"] == workflow_id]

        # Sort by created_at descending
        alerts.sort(key=lambda x: x["created_at"], reverse=True)

        # Apply limit
        alerts = alerts[:limit]

        # Calculate statistics
        total_alerts = len(AlertManagement._alerts)
        active_alerts = len([a for a in AlertManagement._alerts.values() if a["status"] == AlertStatus.ACTIVE])
        critical_alerts = len([a for a in AlertManagement._alerts.values() if a["severity"] == AlertSeverity.CRITICAL])

        return {
            "alerts": alerts,
            "total_alerts": total_alerts,
            "active_alerts": active_alerts,
            "critical_alerts": critical_alerts,
            "returned_count": len(alerts)
        }

    @staticmethod
    def get_active_alerts(session) -> dict:
        """Get all active alerts"""
        return AlertManagement.list_alerts(
            session=session,
            status=AlertStatus.ACTIVE,
            limit=100
        )

    @staticmethod
    def get_alert_statistics(session) -> dict:
        """Get alert system statistics"""
        alerts = list(AlertManagement._alerts.values())

        # Status distribution
        status_dist = defaultdict(int)
        for alert in alerts:
            status_dist[alert["status"]] += 1

        # Severity distribution
        severity_dist = defaultdict(int)
        for alert in alerts:
            severity_dist[alert["severity"]] += 1

        # Type distribution
        type_dist = defaultdict(int)
        for alert in alerts:
            type_dist[alert["alert_type"]] += 1

        # Recent alerts (last 24 hours)
        now = datetime.utcnow()
        recent_cutoff = now - timedelta(hours=24)
        recent_alerts = [
            a for a in alerts
            if datetime.fromisoformat(a["created_at"]) > recent_cutoff
        ]

        return {
            "total_alerts": len(alerts),
            "active_alerts": status_dist.get(AlertStatus.ACTIVE, 0),
            "acknowledged_alerts": status_dist.get(AlertStatus.ACKNOWLEDGED, 0),
            "resolved_alerts": status_dist.get(AlertStatus.RESOLVED, 0),
            "silenced_alerts": status_dist.get(AlertStatus.SILENCED, 0),
            "critical_alerts": severity_dist.get(AlertSeverity.CRITICAL, 0),
            "error_alerts": severity_dist.get(AlertSeverity.ERROR, 0),
            "warning_alerts": severity_dist.get(AlertSeverity.WARNING, 0),
            "info_alerts": severity_dist.get(AlertSeverity.INFO, 0),
            "status_distribution": dict(status_dist),
            "severity_distribution": dict(severity_dist),
            "type_distribution": dict(type_dist),
            "recent_alerts_24h": len(recent_alerts),
            "total_alert_rules": len(AlertManagement._alert_rules),
            "total_notification_channels": len(AlertManagement._notification_channels),
            "total_escalation_policies": len(AlertManagement._escalation_policies),
            "active_silences": len([s for s in AlertManagement._silences.values() if s["is_active"]])
        }

    @staticmethod
    def _process_alert_rules(session, alert: dict):
        """Process alert rules to determine if notifications should be sent"""
        for rule in AlertManagement._alert_rules.values():
            if not rule["enabled"]:
                continue

            # Check if rule matches alert
            if rule["alert_type"] != alert["alert_type"]:
                continue

            # Check severity (only alert if meets or exceeds rule severity)
            severity_order = [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.ERROR, AlertSeverity.CRITICAL]
            if severity_order.index(alert["severity"]) < severity_order.index(rule["severity"]):
                continue

            # Rule matched
            rule["triggered_count"] += 1
            rule["last_triggered_at"] = datetime.utcnow().isoformat()

    @staticmethod
    def _is_silenced(alert: dict) -> bool:
        """Check if alert should be silenced"""
        now = datetime.utcnow()

        for silence in AlertManagement._silences.values():
            if not silence["is_active"]:
                continue

            # Check if silence has expired
            if datetime.fromisoformat(silence["expires_at"]) < now:
                silence["is_active"] = False
                continue

            # Check if silence matches alert
            matches = True
            if silence["alert_type"] and silence["alert_type"] != alert["alert_type"]:
                matches = False
            if silence["severity"] and silence["severity"] != alert["severity"]:
                matches = False
            if silence["agent_id"] is not None and silence["agent_id"] != alert["agent_id"]:
                matches = False
            if silence["workflow_id"] and silence["workflow_id"] != alert["workflow_id"]:
                matches = False

            if matches:
                silence["silenced_count"] += 1
                return True

        return False

    @staticmethod
    def _send_notifications(session, alert: dict):
        """Send notifications for alert"""
        now = datetime.utcnow()

        # Find matching notification channels
        for channel in AlertManagement._notification_channels.values():
            if not channel["enabled"]:
                continue

            # Send notification (simulated)
            notification = {
                "id": f"notif_{uuid.uuid4().hex[:12]}",
                "alert_id": alert["id"],
                "channel_id": channel["id"],
                "channel_type": channel["channel_type"],
                "sent_at": now.isoformat(),
                "status": "sent",
                "alert_title": alert["title"],
                "alert_severity": alert["severity"]
            }

            AlertManagement._notification_history[alert["id"]].append(notification)
            channel["notification_count"] += 1
            channel["last_notification_at"] = now.isoformat()

        alert["notification_sent"] = True
        alert["notification_count"] += 1
