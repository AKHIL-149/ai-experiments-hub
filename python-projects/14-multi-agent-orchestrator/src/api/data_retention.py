"""
Data Retention and Archival API

REST API endpoints for data lifecycle management and retention.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.data_retention import (
    DataRetention,
    RetentionPeriod,
    DataLifecycleStage,
    RetentionAction,
    ComplianceType
)


router = APIRouter()


# Request/Response Models
class CreateRetentionPolicyRequest(BaseModel):
    name: str = Field(..., description="Policy name")
    data_type: str = Field(..., description="Type of data")
    retention_period: str = Field(..., description="How long to retain data")
    action: str = Field(..., description="Action to take after period")
    description: Optional[str] = Field(None, description="Policy description")
    compliance_type: Optional[str] = Field(None, description="Compliance regulation")
    enabled: bool = Field(True, description="Whether policy is enabled")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class CreateLifecycleRuleRequest(BaseModel):
    name: str = Field(..., description="Rule name")
    data_type: str = Field(..., description="Type of data")
    stages: List[dict] = Field(..., description="List of lifecycle stages")
    description: Optional[str] = Field(None, description="Rule description")
    enabled: bool = Field(True, description="Whether rule is enabled")


class ArchiveDataRequest(BaseModel):
    data_type: str = Field(..., description="Type of data")
    data_id: str = Field(..., description="Data identifier")
    data: dict = Field(..., description="Data to archive")
    retention_policy_id: Optional[str] = Field(None, description="Associated retention policy")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class ApplyRetentionPolicyRequest(BaseModel):
    dry_run: bool = Field(False, description="If True, don't actually modify data")


class TransitionLifecycleRequest(BaseModel):
    to_stage: str = Field(..., description="Target lifecycle stage")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class ScheduleRetentionJobRequest(BaseModel):
    name: str = Field(..., description="Job name")
    policy_ids: List[str] = Field(..., description="Policies to apply")
    schedule_cron: str = Field(..., description="Cron schedule")
    enabled: bool = Field(True, description="Whether job is enabled")


class CreateComplianceRequirementRequest(BaseModel):
    name: str = Field(..., description="Requirement name")
    compliance_type: str = Field(..., description="Type of compliance")
    data_types: List[str] = Field(..., description="Data types covered")
    minimum_retention_days: int = Field(..., description="Minimum retention period")
    maximum_retention_days: Optional[int] = Field(None, description="Maximum retention period")
    required_actions: Optional[List[str]] = Field(None, description="Required actions")
    description: Optional[str] = Field(None, description="Requirement description")


@router.post("/policies")
def create_retention_policy(
    request: CreateRetentionPolicyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a retention policy.

    Defines rules for how long data should be retained and
    what action to take when the retention period expires.
    """
    try:
        policy = DataRetention.create_retention_policy(
            session=session,
            name=request.name,
            data_type=request.data_type,
            retention_period=request.retention_period,
            action=request.action,
            description=request.description,
            compliance_type=request.compliance_type,
            enabled=request.enabled,
            metadata=request.metadata
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


@router.post("/lifecycle-rules")
def create_lifecycle_rule(
    request: CreateLifecycleRuleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a lifecycle rule.

    Defines the stages data moves through in its lifecycle
    (active → warm → cold → archived).
    """
    try:
        rule = DataRetention.create_lifecycle_rule(
            session=session,
            name=request.name,
            data_type=request.data_type,
            stages=request.stages,
            description=request.description,
            enabled=request.enabled
        )

        return {
            "success": True,
            "rule": rule,
            "message": f"Lifecycle rule created: {rule['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/archive")
def archive_data(
    request: ArchiveDataRequest,
    session: Session = Depends(get_db_session)
):
    """
    Archive data.

    Moves data to archive storage with compression and
    retention tracking.
    """
    try:
        archive = DataRetention.archive_data(
            session=session,
            data_type=request.data_type,
            data_id=request.data_id,
            data=request.data,
            retention_policy_id=request.retention_policy_id,
            metadata=request.metadata
        )

        return {
            "success": True,
            "archive": archive,
            "message": f"Data archived: {archive['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/{archive_id}")
def retrieve_archived_data(
    archive_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Retrieve archived data.

    Returns data from archive storage with access tracking.
    """
    try:
        data = DataRetention.retrieve_archived_data(
            session=session,
            archive_id=archive_id
        )

        return {
            "success": True,
            **data
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/policies/{policy_id}/apply")
def apply_retention_policy(
    policy_id: str,
    request: ApplyRetentionPolicyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Apply a retention policy.

    Processes data according to the policy rules, archiving
    or deleting items as configured.
    """
    try:
        results = DataRetention.apply_retention_policy(
            session=session,
            policy_id=policy_id,
            dry_run=request.dry_run
        )

        return {
            "success": True,
            "results": results,
            "message": f"Policy applied: {results['items_processed']} items processed"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lifecycle/transition")
def transition_lifecycle_stage(
    data_type: str,
    data_id: str,
    request: TransitionLifecycleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Transition data to a different lifecycle stage.

    Moves data between stages (active → warm → cold → archived).
    """
    try:
        transition = DataRetention.transition_lifecycle_stage(
            session=session,
            data_type=data_type,
            data_id=data_id,
            to_stage=request.to_stage,
            metadata=request.metadata
        )

        return {
            "success": True,
            "transition": transition,
            "message": f"Data transitioned to {request.to_stage}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs")
def schedule_retention_job(
    request: ScheduleRetentionJobRequest,
    session: Session = Depends(get_db_session)
):
    """
    Schedule a retention job.

    Creates a scheduled job to automatically apply retention
    policies on a recurring basis.
    """
    try:
        job = DataRetention.schedule_retention_job(
            session=session,
            name=request.name,
            policy_ids=request.policy_ids,
            schedule_cron=request.schedule_cron,
            enabled=request.enabled
        )

        return {
            "success": True,
            "job": job,
            "message": f"Retention job scheduled: {job['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compliance")
def create_compliance_requirement(
    request: CreateComplianceRequirementRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a compliance requirement.

    Defines compliance-driven retention requirements
    (GDPR, HIPAA, SOC2, etc.).
    """
    try:
        requirement = DataRetention.create_compliance_requirement(
            session=session,
            name=request.name,
            compliance_type=request.compliance_type,
            data_types=request.data_types,
            minimum_retention_days=request.minimum_retention_days,
            maximum_retention_days=request.maximum_retention_days,
            required_actions=request.required_actions,
            description=request.description
        )

        return {
            "success": True,
            "requirement": requirement,
            "message": f"Compliance requirement created: {requirement['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies")
def list_retention_policies(
    data_type: Optional[str] = None,
    compliance_type: Optional[str] = None,
    enabled: Optional[bool] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List retention policies.

    Returns policies with optional filtering by data type,
    compliance type, and enabled status.
    """
    try:
        result = DataRetention.list_retention_policies(
            session=session,
            data_type=data_type,
            compliance_type=compliance_type,
            enabled=enabled,
            limit=limit
        )

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
    Get data retention statistics.

    Returns aggregate metrics including archived items,
    storage savings, and policy statistics.
    """
    try:
        stats = DataRetention.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/retention-periods")
def list_retention_periods():
    """
    List all retention periods.

    Returns all available retention period options.
    """
    return {
        "success": True,
        "retention_periods": [
            {"period": RetentionPeriod.DAYS_7, "description": "7 days", "days": 7},
            {"period": RetentionPeriod.DAYS_30, "description": "30 days", "days": 30},
            {"period": RetentionPeriod.DAYS_90, "description": "90 days", "days": 90},
            {"period": RetentionPeriod.DAYS_180, "description": "180 days", "days": 180},
            {"period": RetentionPeriod.YEAR_1, "description": "1 year", "days": 365},
            {"period": RetentionPeriod.YEAR_3, "description": "3 years", "days": 1095},
            {"period": RetentionPeriod.YEAR_7, "description": "7 years", "days": 2555},
            {"period": RetentionPeriod.PERMANENT, "description": "Permanent", "days": None}
        ]
    }


@router.get("/lifecycle-stages")
def list_lifecycle_stages():
    """
    List all lifecycle stages.

    Returns all available data lifecycle stages.
    """
    return {
        "success": True,
        "lifecycle_stages": [
            {"stage": DataLifecycleStage.ACTIVE, "description": "Active - frequently accessed"},
            {"stage": DataLifecycleStage.WARM, "description": "Warm - occasionally accessed"},
            {"stage": DataLifecycleStage.COLD, "description": "Cold - rarely accessed"},
            {"stage": DataLifecycleStage.ARCHIVED, "description": "Archived - long-term storage"},
            {"stage": DataLifecycleStage.DELETED, "description": "Deleted - removed"}
        ]
    }


@router.get("/actions")
def list_retention_actions():
    """
    List all retention actions.

    Returns all available retention policy actions.
    """
    return {
        "success": True,
        "retention_actions": [
            {"action": RetentionAction.ARCHIVE, "description": "Archive data to cold storage"},
            {"action": RetentionAction.DELETE, "description": "Permanently delete data"},
            {"action": RetentionAction.COMPRESS, "description": "Compress data"},
            {"action": RetentionAction.ENCRYPT, "description": "Encrypt data"},
            {"action": RetentionAction.MOVE_TO_COLD, "description": "Move to cold storage"}
        ]
    }


@router.get("/compliance-types")
def list_compliance_types():
    """
    List all compliance types.

    Returns all supported compliance regulation types.
    """
    return {
        "success": True,
        "compliance_types": [
            {"type": ComplianceType.GDPR, "description": "General Data Protection Regulation"},
            {"type": ComplianceType.HIPAA, "description": "Health Insurance Portability and Accountability Act"},
            {"type": ComplianceType.SOC2, "description": "Service Organization Control 2"},
            {"type": ComplianceType.PCI_DSS, "description": "Payment Card Industry Data Security Standard"},
            {"type": ComplianceType.CCPA, "description": "California Consumer Privacy Act"},
            {"type": ComplianceType.CUSTOM, "description": "Custom compliance requirement"}
        ]
    }
