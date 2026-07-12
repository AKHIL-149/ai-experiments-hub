"""
SLA Management and Tracking API

REST API endpoints for service level agreement definition, monitoring, and compliance tracking.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from src.database import get_db_session
from src.services.sla_management import (
    SLAManagement,
    SLAMetricType,
    SLASeverity,
    SLAStatus
)


router = APIRouter()


# Request/Response Models
class CreateSLARequest(BaseModel):
    """Request model for creating an SLA"""
    sla_id: str = Field(..., description="Unique SLA identifier")
    name: str = Field(..., description="SLA name")
    service_name: str = Field(..., description="Service name")
    metric_type: SLAMetricType = Field(..., description="Type of metric")
    target_value: float = Field(..., description="Target value for the metric")
    measurement_window_hours: int = Field(default=24, description="Measurement window in hours", ge=1)
    warning_threshold: float = Field(default=90.0, description="Warning threshold percentage", ge=0, le=100)
    description: Optional[str] = Field(default=None, description="SLA description")
    penalty_per_violation: float = Field(default=0.0, description="Penalty amount per violation", ge=0)


class RecordMetricRequest(BaseModel):
    """Request model for recording a metric"""
    measured_value: float = Field(..., description="Measured value")
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp")
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class UpdateSLARequest(BaseModel):
    """Request model for updating an SLA"""
    target_value: Optional[float] = Field(default=None, description="New target value")
    warning_threshold: Optional[float] = Field(default=None, description="New warning threshold", ge=0, le=100)
    penalty_per_violation: Optional[float] = Field(default=None, description="New penalty amount", ge=0)
    status: Optional[SLAStatus] = Field(default=None, description="New status")


class AcknowledgeViolationRequest(BaseModel):
    """Request model for acknowledging a violation"""
    notes: Optional[str] = Field(default=None, description="Acknowledgement notes")


class ResolveViolationRequest(BaseModel):
    """Request model for resolving a violation"""
    resolution_notes: str = Field(..., description="Resolution notes")


class GenerateReportRequest(BaseModel):
    """Request model for generating a compliance report"""
    start_time: Optional[str] = Field(default=None, description="Report start time (ISO)")
    end_time: Optional[str] = Field(default=None, description="Report end time (ISO)")


# API Endpoints
@router.post("/slas")
def create_sla(
    request: CreateSLARequest,
    session: Session = Depends(get_db_session)
):
    """
    Create an SLA.
    Defines a service level agreement with target metrics and thresholds.
    """
    try:
        result = SLAManagement.create_sla(
            session=session,
            sla_id=request.sla_id,
            name=request.name,
            service_name=request.service_name,
            metric_type=request.metric_type,
            target_value=request.target_value,
            measurement_window_hours=request.measurement_window_hours,
            warning_threshold=request.warning_threshold,
            description=request.description,
            penalty_per_violation=request.penalty_per_violation
        )
        return {
            "success": True,
            "sla": result,
            "message": f"SLA created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating SLA: {str(e)}")


@router.get("/slas")
def list_slas(session: Session = Depends(get_db_session)):
    """
    List all SLAs.
    Returns all defined service level agreements.
    """
    try:
        slas = list(SLAManagement._slas.values())
        return {
            "success": True,
            "slas": slas,
            "count": len(slas)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing SLAs: {str(e)}")


@router.get("/slas/{sla_id}")
def get_sla(
    sla_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get SLA details.
    Returns detailed information about a specific SLA.
    """
    try:
        sla = SLAManagement._slas.get(sla_id)
        if not sla:
            raise HTTPException(status_code=404, detail=f"SLA not found: {sla_id}")

        return {
            "success": True,
            "sla": sla
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting SLA: {str(e)}")


@router.put("/slas/{sla_id}")
def update_sla(
    sla_id: str,
    request: UpdateSLARequest,
    session: Session = Depends(get_db_session)
):
    """
    Update an SLA.
    Modifies SLA parameters and creates a new version.
    """
    try:
        result = SLAManagement.update_sla(
            session=session,
            sla_id=sla_id,
            target_value=request.target_value,
            warning_threshold=request.warning_threshold,
            penalty_per_violation=request.penalty_per_violation,
            status=request.status
        )
        return {
            "success": True,
            "sla": result,
            "message": f"SLA updated: {result['name']}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating SLA: {str(e)}")


@router.get("/slas/{sla_id}/status")
def get_sla_status(
    sla_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get SLA status.
    Returns current status, compliance rate, and active violations.
    """
    try:
        status = SLAManagement.get_sla_status(
            session=session,
            sla_id=sla_id
        )
        return {
            "success": True,
            "status": status
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting SLA status: {str(e)}")


@router.get("/slas/{sla_id}/history")
def get_sla_history(
    sla_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get SLA version history.
    Returns all versions of an SLA with change history.
    """
    try:
        history = SLAManagement.get_sla_history(
            session=session,
            sla_id=sla_id
        )
        return {
            "success": True,
            "history": history,
            "versions": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting SLA history: {str(e)}")


@router.post("/slas/{sla_id}/metrics")
def record_metric(
    sla_id: str,
    request: RecordMetricRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record SLA metric.
    Records a metric measurement and checks for violations.
    """
    try:
        result = SLAManagement.record_metric(
            session=session,
            sla_id=sla_id,
            measured_value=request.measured_value,
            timestamp=request.timestamp,
            metadata=request.metadata
        )

        message = "Metric recorded"
        if result["is_violation"]:
            message = f"Metric recorded - VIOLATION detected ({result['deviation_percent']:.1f}% deviation)"

        return {
            "success": True,
            "metric": result,
            "message": message
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error recording metric: {str(e)}")


@router.get("/violations")
def get_violations(
    sla_id: Optional[str] = None,
    severity: Optional[SLASeverity] = None,
    resolved: Optional[bool] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get SLA violations.
    Returns violations with optional filtering by SLA, severity, or resolution status.
    """
    try:
        violations = SLAManagement.get_violations(
            session=session,
            sla_id=sla_id,
            severity=severity,
            resolved=resolved
        )
        return {
            "success": True,
            "violations": violations,
            "count": len(violations)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting violations: {str(e)}")


@router.post("/violations/{violation_id}/acknowledge")
def acknowledge_violation(
    violation_id: str,
    request: AcknowledgeViolationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Acknowledge a violation.
    Marks an SLA violation as acknowledged.
    """
    try:
        result = SLAManagement.acknowledge_violation(
            session=session,
            violation_id=violation_id,
            notes=request.notes
        )
        return {
            "success": True,
            "acknowledgement": result,
            "message": "Violation acknowledged"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error acknowledging violation: {str(e)}")


@router.post("/violations/{violation_id}/resolve")
def resolve_violation(
    violation_id: str,
    request: ResolveViolationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Resolve a violation.
    Marks an SLA violation as resolved with resolution notes.
    """
    try:
        result = SLAManagement.resolve_violation(
            session=session,
            violation_id=violation_id,
            resolution_notes=request.resolution_notes
        )
        return {
            "success": True,
            "resolution": result,
            "message": "Violation resolved"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resolving violation: {str(e)}")


@router.post("/slas/{sla_id}/reports")
def generate_compliance_report(
    sla_id: str,
    request: GenerateReportRequest,
    session: Session = Depends(get_db_session)
):
    """
    Generate compliance report.
    Creates a detailed compliance report for an SLA over a specified time period.
    """
    try:
        report = SLAManagement.generate_compliance_report(
            session=session,
            sla_id=sla_id,
            start_time=request.start_time,
            end_time=request.end_time
        )
        return {
            "success": True,
            "report": report,
            "message": f"Compliance report generated - {report['compliance_rate']:.2f}% compliant"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")


@router.get("/reports")
def list_reports(session: Session = Depends(get_db_session)):
    """
    List compliance reports.
    Returns all generated compliance reports.
    """
    try:
        reports = list(SLAManagement._compliance_reports.values())
        return {
            "success": True,
            "reports": reports,
            "count": len(reports)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing reports: {str(e)}")


@router.post("/slas/{sla_id}/error-budget/reset")
def reset_error_budget(
    sla_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Reset error budget.
    Resets the error budget for an SLA (typically done monthly).
    """
    try:
        budget = SLAManagement.reset_error_budget(
            session=session,
            sla_id=sla_id
        )
        return {
            "success": True,
            "error_budget": budget,
            "message": "Error budget reset successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting error budget: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive SLA management statistics.
    """
    try:
        stats = SLAManagement.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
