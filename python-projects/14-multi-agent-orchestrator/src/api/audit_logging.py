"""
Audit Logging API

REST API endpoints for audit logging and compliance tracking.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.audit_logging import (
    AuditLogging,
    AuditEventType,
    AuditCategory,
    AuditSeverity
)


router = APIRouter()


# Request/Response Models
class LogEventRequest(BaseModel):
    event_type: str = Field(..., description="Type of event")
    category: str = Field(..., description="Event category")
    actor: str = Field(..., description="User/system performing action")
    action: str = Field(..., description="Description of action")
    resource_type: Optional[str] = Field(None, description="Type of resource affected")
    resource_id: Optional[str] = Field(None, description="ID of resource affected")
    details: Optional[dict] = Field(None, description="Event details")
    changes: Optional[dict] = Field(None, description="Before/after changes")
    severity: str = Field(AuditSeverity.INFO, description="Event severity")
    ip_address: Optional[str] = Field(None, description="IP address of actor")
    user_agent: Optional[str] = Field(None, description="User agent string")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class LogAuthenticationRequest(BaseModel):
    actor: str = Field(..., description="User attempting authentication")
    success: bool = Field(..., description="Whether authentication succeeded")
    method: str = Field(..., description="Authentication method")
    ip_address: Optional[str] = Field(None, description="IP address")
    failure_reason: Optional[str] = Field(None, description="Reason for failure")


class LogDataAccessRequest(BaseModel):
    actor: str = Field(..., description="User accessing data")
    resource_type: str = Field(..., description="Type of resource")
    resource_id: str = Field(..., description="Resource ID")
    operation: str = Field(..., description="Operation performed")
    ip_address: Optional[str] = Field(None, description="IP address")


class LogConfigChangeRequest(BaseModel):
    actor: str = Field(..., description="User changing configuration")
    config_key: str = Field(..., description="Configuration key")
    old_value: Optional[str] = Field(None, description="Old value")
    new_value: Optional[str] = Field(None, description="New value")
    ip_address: Optional[str] = Field(None, description="IP address")


class CreateRetentionPolicyRequest(BaseModel):
    name: str = Field(..., description="Policy name")
    category: Optional[str] = Field(None, description="Category to apply to")
    severity: Optional[str] = Field(None, description="Severity to apply to")
    retention_days: int = Field(90, description="Days to retain logs")
    enabled: bool = Field(True, description="Whether policy is enabled")


@router.post("/logs")
def log_event(
    request: LogEventRequest,
    session: Session = Depends(get_db_session)
):
    """
    Log an audit event.

    Creates an audit log entry with tamper-proof hash chaining
    for compliance and security tracking.
    """
    try:
        log = AuditLogging.log_event(
            session=session,
            event_type=request.event_type,
            category=request.category,
            actor=request.actor,
            action=request.action,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            details=request.details,
            changes=request.changes,
            severity=request.severity,
            ip_address=request.ip_address,
            user_agent=request.user_agent,
            metadata=request.metadata
        )

        return {
            "success": True,
            "log": log,
            "message": "Audit event logged"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logs/authentication")
def log_authentication(
    request: LogAuthenticationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Log authentication event.

    Tracks authentication attempts for security monitoring.
    """
    try:
        log = AuditLogging.log_authentication(
            session=session,
            actor=request.actor,
            success=request.success,
            method=request.method,
            ip_address=request.ip_address,
            failure_reason=request.failure_reason
        )

        return {
            "success": True,
            "log": log,
            "message": "Authentication event logged"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logs/data-access")
def log_data_access(
    request: LogDataAccessRequest,
    session: Session = Depends(get_db_session)
):
    """
    Log data access event.

    Tracks data access for compliance and privacy requirements.
    """
    try:
        log = AuditLogging.log_data_access(
            session=session,
            actor=request.actor,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            operation=request.operation,
            ip_address=request.ip_address
        )

        return {
            "success": True,
            "log": log,
            "message": "Data access event logged"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logs/config-change")
def log_config_change(
    request: LogConfigChangeRequest,
    session: Session = Depends(get_db_session)
):
    """
    Log configuration change.

    Tracks configuration changes for audit trail.
    """
    try:
        log = AuditLogging.log_configuration_change(
            session=session,
            actor=request.actor,
            config_key=request.config_key,
            old_value=request.old_value,
            new_value=request.new_value,
            ip_address=request.ip_address
        )

        return {
            "success": True,
            "log": log,
            "message": "Configuration change logged"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
def query_logs(
    event_type: Optional[str] = None,
    category: Optional[str] = None,
    actor: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    severity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    Query audit logs.

    Returns audit logs with optional filtering by event type,
    category, actor, resource, severity, and date range.
    """
    try:
        result = AuditLogging.query_logs(
            session=session,
            event_type=event_type,
            category=category,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            severity=severity,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actors/{actor}/activity")
def get_actor_activity(
    actor: str,
    time_window_hours: int = 24,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get actor activity.

    Returns activity and statistics for a specific actor
    within a time window.
    """
    try:
        result = AuditLogging.get_actor_activity(
            session=session,
            actor=actor,
            time_window_hours=time_window_hours,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources/{resource_type}/{resource_id}/history")
def get_resource_history(
    resource_type: str,
    resource_id: str,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get resource history.

    Returns complete audit trail for a specific resource
    including all changes and access events.
    """
    try:
        result = AuditLogging.get_resource_history(
            session=session,
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retention-policies")
def create_retention_policy(
    request: CreateRetentionPolicyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create retention policy.

    Defines how long audit logs should be retained based
    on category and severity.
    """
    try:
        policy = AuditLogging.create_retention_policy(
            session=session,
            name=request.name,
            category=request.category,
            severity=request.severity,
            retention_days=request.retention_days,
            enabled=request.enabled
        )

        return {
            "success": True,
            "policy": policy,
            "message": f"Retention policy created: {policy['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export")
def export_logs(
    format: str = "json",
    event_type: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Export audit logs.

    Exports audit logs in JSON or CSV format for compliance
    reporting and analysis.
    """
    try:
        export = AuditLogging.export_logs(
            session=session,
            format=format,
            event_type=event_type,
            category=category,
            start_date=start_date,
            end_date=end_date
        )

        return {
            "success": True,
            "export": export,
            "message": f"Exported {export['log_count']} audit logs"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verify-integrity")
def verify_integrity(
    session: Session = Depends(get_db_session)
):
    """
    Verify audit log integrity.

    Verifies the hash chain integrity of audit logs to
    detect tampering or corruption.
    """
    try:
        result = AuditLogging.verify_integrity(session=session)

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get audit logging statistics.

    Returns aggregate metrics including log counts, distributions,
    and top actors.
    """
    try:
        stats = AuditLogging.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/event-types")
def list_event_types():
    """
    List all event types.

    Returns all available audit event types and their descriptions.
    """
    return {
        "success": True,
        "event_types": [
            {"type": AuditEventType.CREATE, "description": "Resource creation"},
            {"type": AuditEventType.UPDATE, "description": "Resource update"},
            {"type": AuditEventType.DELETE, "description": "Resource deletion"},
            {"type": AuditEventType.ACCESS, "description": "Resource access"},
            {"type": AuditEventType.EXECUTE, "description": "Action execution"},
            {"type": AuditEventType.AUTHENTICATE, "description": "Authentication attempt"},
            {"type": AuditEventType.AUTHORIZE, "description": "Authorization check"},
            {"type": AuditEventType.EXPORT, "description": "Data export"},
            {"type": AuditEventType.IMPORT, "description": "Data import"},
            {"type": AuditEventType.CONFIGURE, "description": "Configuration change"}
        ]
    }


@router.get("/categories")
def list_categories():
    """
    List all categories.

    Returns all audit log categories and their descriptions.
    """
    return {
        "success": True,
        "categories": [
            {"category": AuditCategory.USER, "description": "User actions"},
            {"category": AuditCategory.AGENT, "description": "Agent actions"},
            {"category": AuditCategory.WORKFLOW, "description": "Workflow actions"},
            {"category": AuditCategory.TASK, "description": "Task actions"},
            {"category": AuditCategory.SYSTEM, "description": "System actions"},
            {"category": AuditCategory.SECURITY, "description": "Security events"},
            {"category": AuditCategory.DATA, "description": "Data access events"},
            {"category": AuditCategory.CONFIG, "description": "Configuration changes"},
            {"category": AuditCategory.COST, "description": "Cost-related events"},
            {"category": AuditCategory.APPROVAL, "description": "Approval events"}
        ]
    }


@router.get("/severities")
def list_severities():
    """
    List all severity levels.

    Returns all audit log severity levels.
    """
    return {
        "success": True,
        "severities": [
            {"severity": AuditSeverity.INFO, "description": "Informational event"},
            {"severity": AuditSeverity.WARNING, "description": "Warning event"},
            {"severity": AuditSeverity.ERROR, "description": "Error event"},
            {"severity": AuditSeverity.CRITICAL, "description": "Critical event"}
        ]
    }
