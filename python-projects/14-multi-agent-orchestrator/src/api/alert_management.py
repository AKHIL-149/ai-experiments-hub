"""
Alert Management API

REST API endpoints for managing alerts, notifications, and escalations.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.alert_management import (
    AlertManagement,
    AlertType,
    AlertSeverity,
    AlertStatus,
    NotificationChannel
)


router = APIRouter()


# Request/Response Models
class CreateAlertRequest(BaseModel):
    alert_type: str = Field(..., description="Type of alert")
    severity: str = Field(..., description="Alert severity level")
    title: str = Field(..., description="Alert title")
    description: str = Field(..., description="Detailed description")
    source: Optional[str] = Field(None, description="Alert source system")
    agent_id: Optional[int] = Field(None, description="Related agent ID")
    workflow_id: Optional[str] = Field(None, description="Related workflow ID")
    details: Optional[dict] = Field(None, description="Alert details and context")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class AcknowledgeAlertRequest(BaseModel):
    acknowledged_by: str = Field(..., description="User/system acknowledging")
    notes: Optional[str] = Field(None, description="Acknowledgment notes")


class ResolveAlertRequest(BaseModel):
    resolved_by: str = Field(..., description="User/system resolving")
    resolution_notes: Optional[str] = Field(None, description="Resolution notes")


class CreateAlertRuleRequest(BaseModel):
    name: str = Field(..., description="Rule name")
    alert_type: str = Field(..., description="Type of alert to trigger")
    condition: dict = Field(..., description="Rule condition/threshold")
    severity: str = Field(..., description="Alert severity")
    notification_channels: List[str] = Field(..., description="Channels to notify")
    description: Optional[str] = Field(None, description="Rule description")
    enabled: bool = Field(True, description="Whether rule is enabled")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class CreateNotificationChannelRequest(BaseModel):
    name: str = Field(..., description="Channel name")
    channel_type: str = Field(..., description="Type of channel")
    config: dict = Field(..., description="Channel configuration")
    enabled: bool = Field(True, description="Whether channel is enabled")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class CreateEscalationPolicyRequest(BaseModel):
    name: str = Field(..., description="Policy name")
    alert_type: str = Field(..., description="Alert type to apply to")
    severity: str = Field(..., description="Minimum severity level")
    escalation_steps: List[dict] = Field(..., description="List of escalation steps")
    description: Optional[str] = Field(None, description="Policy description")
    enabled: bool = Field(True, description="Whether policy is enabled")


class CreateSilenceRequest(BaseModel):
    alert_type: Optional[str] = Field(None, description="Alert type to silence")
    severity: Optional[str] = Field(None, description="Severity level to silence")
    agent_id: Optional[int] = Field(None, description="Agent ID to silence")
    workflow_id: Optional[str] = Field(None, description="Workflow ID to silence")
    duration_minutes: int = Field(60, description="Silence duration in minutes")
    reason: Optional[str] = Field(None, description="Reason for silence")
    created_by: Optional[str] = Field(None, description="User creating silence")


@router.post("/alerts")
def create_alert(
    request: CreateAlertRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new alert.

    Creates an alert that will be evaluated against rules and silences,
    and send notifications to configured channels.
    """
    try:
        alert = AlertManagement.create_alert(
            session=session,
            alert_type=request.alert_type,
            severity=request.severity,
            title=request.title,
            description=request.description,
            source=request.source,
            agent_id=request.agent_id,
            workflow_id=request.workflow_id,
            details=request.details,
            metadata=request.metadata
        )

        return {
            "success": True,
            "alert": alert,
            "message": f"Alert created: {alert['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    request: AcknowledgeAlertRequest,
    session: Session = Depends(get_db_session)
):
    """
    Acknowledge an alert.

    Marks the alert as acknowledged, indicating that someone is
    aware of the issue and working on it.
    """
    try:
        alert = AlertManagement.acknowledge_alert(
            session=session,
            alert_id=alert_id,
            acknowledged_by=request.acknowledged_by,
            notes=request.notes
        )

        return {
            "success": True,
            "alert": alert,
            "message": f"Alert acknowledged by {request.acknowledged_by}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    request: ResolveAlertRequest,
    session: Session = Depends(get_db_session)
):
    """
    Resolve an alert.

    Marks the alert as resolved, indicating the issue has been fixed.
    """
    try:
        alert = AlertManagement.resolve_alert(
            session=session,
            alert_id=alert_id,
            resolved_by=request.resolved_by,
            resolution_notes=request.resolution_notes
        )

        return {
            "success": True,
            "alert": alert,
            "message": f"Alert resolved by {request.resolved_by}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/{alert_id}")
def get_alert(
    alert_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get alert details.

    Returns complete information about an alert including
    its history and notifications.
    """
    try:
        alert = AlertManagement.get_alert(
            session=session,
            alert_id=alert_id
        )

        return {
            "success": True,
            "alert": alert
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
def list_alerts(
    alert_type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    agent_id: Optional[int] = None,
    workflow_id: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List alerts.

    Returns alerts with optional filtering by type, severity,
    status, agent, or workflow.
    """
    try:
        result = AlertManagement.list_alerts(
            session=session,
            alert_type=alert_type,
            severity=severity,
            status=status,
            agent_id=agent_id,
            workflow_id=workflow_id,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/active")
def get_active_alerts(
    session: Session = Depends(get_db_session)
):
    """
    Get active alerts.

    Returns all alerts that are currently active and need attention.
    """
    try:
        result = AlertManagement.get_active_alerts(session=session)

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rules")
def create_alert_rule(
    request: CreateAlertRuleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create an alert rule.

    Defines conditions for automatically creating alerts
    when certain thresholds or events occur.
    """
    try:
        rule = AlertManagement.create_alert_rule(
            session=session,
            name=request.name,
            alert_type=request.alert_type,
            condition=request.condition,
            severity=request.severity,
            notification_channels=request.notification_channels,
            description=request.description,
            enabled=request.enabled,
            metadata=request.metadata
        )

        return {
            "success": True,
            "rule": rule,
            "message": f"Alert rule created: {rule['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/channels")
def create_notification_channel(
    request: CreateNotificationChannelRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a notification channel.

    Configures a channel (email, Slack, webhook, etc.) for
    sending alert notifications.
    """
    try:
        channel = AlertManagement.create_notification_channel(
            session=session,
            name=request.name,
            channel_type=request.channel_type,
            config=request.config,
            enabled=request.enabled,
            metadata=request.metadata
        )

        return {
            "success": True,
            "channel": channel,
            "message": f"Notification channel created: {channel['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/escalation-policies")
def create_escalation_policy(
    request: CreateEscalationPolicyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create an escalation policy.

    Defines how alerts should escalate over time if not
    acknowledged or resolved.
    """
    try:
        policy = AlertManagement.create_escalation_policy(
            session=session,
            name=request.name,
            alert_type=request.alert_type,
            severity=request.severity,
            escalation_steps=request.escalation_steps,
            description=request.description,
            enabled=request.enabled
        )

        return {
            "success": True,
            "policy": policy,
            "message": f"Escalation policy created: {policy['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/silences")
def create_silence(
    request: CreateSilenceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create an alert silence.

    Temporarily suppresses alerts matching specified criteria
    for a given duration.
    """
    try:
        silence = AlertManagement.create_silence(
            session=session,
            alert_type=request.alert_type,
            severity=request.severity,
            agent_id=request.agent_id,
            workflow_id=request.workflow_id,
            duration_minutes=request.duration_minutes,
            reason=request.reason,
            created_by=request.created_by
        )

        return {
            "success": True,
            "silence": silence,
            "message": f"Silence created for {request.duration_minutes} minutes"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get alert system statistics.

    Returns aggregate metrics including alert counts, status
    distribution, and notification statistics.
    """
    try:
        stats = AlertManagement.get_alert_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alert-types")
def list_alert_types():
    """
    List all alert types.

    Returns all available alert types and their descriptions.
    """
    return {
        "success": True,
        "alert_types": [
            {"type": AlertType.PERFORMANCE, "description": "Performance-related alerts"},
            {"type": AlertType.COST, "description": "Cost and budget alerts"},
            {"type": AlertType.SYSTEM, "description": "System health alerts"},
            {"type": AlertType.WORKFLOW, "description": "Workflow execution alerts"},
            {"type": AlertType.AGENT, "description": "Agent status alerts"},
            {"type": AlertType.SECURITY, "description": "Security and access alerts"},
            {"type": AlertType.RESOURCE, "description": "Resource utilization alerts"},
            {"type": AlertType.CUSTOM, "description": "Custom alerts"}
        ]
    }


@router.get("/severities")
def list_alert_severities():
    """
    List all alert severity levels.

    Returns all possible alert severity levels.
    """
    return {
        "success": True,
        "severities": [
            {"severity": AlertSeverity.INFO, "description": "Informational - no action required"},
            {"severity": AlertSeverity.WARNING, "description": "Warning - may require attention"},
            {"severity": AlertSeverity.ERROR, "description": "Error - requires action"},
            {"severity": AlertSeverity.CRITICAL, "description": "Critical - requires immediate action"}
        ]
    }


@router.get("/statuses")
def list_alert_statuses():
    """
    List all alert statuses.

    Returns all possible alert lifecycle statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": AlertStatus.ACTIVE, "description": "Active - waiting for acknowledgment"},
            {"status": AlertStatus.ACKNOWLEDGED, "description": "Acknowledged - being worked on"},
            {"status": AlertStatus.RESOLVED, "description": "Resolved - issue fixed"},
            {"status": AlertStatus.SILENCED, "description": "Silenced - notifications suppressed"},
            {"status": AlertStatus.EXPIRED, "description": "Expired - auto-expired"}
        ]
    }


@router.get("/channel-types")
def list_channel_types():
    """
    List all notification channel types.

    Returns all supported notification channel types.
    """
    return {
        "success": True,
        "channel_types": [
            {"type": NotificationChannel.EMAIL, "description": "Email notifications"},
            {"type": NotificationChannel.SLACK, "description": "Slack notifications"},
            {"type": NotificationChannel.WEBHOOK, "description": "Webhook/HTTP notifications"},
            {"type": NotificationChannel.SMS, "description": "SMS text notifications"},
            {"type": NotificationChannel.PAGERDUTY, "description": "PagerDuty integration"},
            {"type": NotificationChannel.IN_APP, "description": "In-app notifications"}
        ]
    }
