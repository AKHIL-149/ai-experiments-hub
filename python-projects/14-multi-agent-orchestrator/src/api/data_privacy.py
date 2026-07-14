"""
Data Privacy and Compliance API

REST API endpoints for GDPR/CCPA compliance, consent management, data subject rights,
and privacy audit trails.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.data_privacy import (
    DataPrivacy,
    ConsentStatus,
    ConsentPurpose,
    DataSubjectRight,
    RequestStatus,
    DataCategory,
    AnonymizationMethod,
    BreachSeverity
)


router = APIRouter()


# Request/Response Models
class RecordConsentRequest(BaseModel):
    """Request model for recording consent"""
    consent_id: str = Field(..., description="Unique consent identifier")
    user_id: str = Field(..., description="User identifier")
    purpose: ConsentPurpose = Field(..., description="Consent purpose")
    status: ConsentStatus = Field(default=ConsentStatus.GRANTED, description="Consent status")
    expires_at: Optional[str] = Field(default=None, description="Expiration date (ISO)")
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class WithdrawConsentRequest(BaseModel):
    """Request model for withdrawing consent"""
    user_id: str = Field(..., description="User identifier")


class CheckConsentRequest(BaseModel):
    """Request model for checking consent"""
    user_id: str = Field(..., description="User identifier")
    purpose: ConsentPurpose = Field(..., description="Purpose to check")


class CreateDSRRequest(BaseModel):
    """Request model for creating data subject request"""
    request_id: str = Field(..., description="Unique request identifier")
    user_id: str = Field(..., description="User identifier")
    right_type: DataSubjectRight = Field(..., description="Type of right being exercised")
    description: Optional[str] = Field(default=None, description="Request description")
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class ProcessDSRRequest(BaseModel):
    """Request model for processing DSR"""
    response_data: Optional[Dict] = Field(default=None, description="Response data")


class CreateRetentionPolicyRequest(BaseModel):
    """Request model for creating retention policy"""
    policy_id: str = Field(..., description="Unique policy identifier")
    name: str = Field(..., description="Policy name")
    data_category: DataCategory = Field(..., description="Data category")
    retention_days: int = Field(..., description="Retention period in days", ge=1)
    description: Optional[str] = Field(default=None, description="Policy description")
    auto_delete: bool = Field(default=True, description="Auto-delete expired data")


class AnonymizeDataRequest(BaseModel):
    """Request model for data anonymization"""
    data: Dict = Field(..., description="Data to anonymize")
    fields: List[str] = Field(..., description="Fields to anonymize")
    method: AnonymizationMethod = Field(default=AnonymizationMethod.HASH, description="Anonymization method")


class ReportBreachRequest(BaseModel):
    """Request model for reporting data breach"""
    breach_id: str = Field(..., description="Unique breach identifier")
    description: str = Field(..., description="Breach description")
    severity: BreachSeverity = Field(..., description="Breach severity")
    affected_records: int = Field(..., description="Number of affected records", ge=0)
    data_categories: List[DataCategory] = Field(..., description="Affected data categories")
    discovered_at: Optional[str] = Field(default=None, description="Discovery date (ISO)")
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class UpdateBreachRequest(BaseModel):
    """Request model for updating breach status"""
    containment_actions: Optional[List[str]] = Field(default=None, description="Containment actions taken")
    authority_notified: Optional[bool] = Field(default=None, description="Authority notification status")
    users_notified: Optional[bool] = Field(default=None, description="User notification status")
    remediation_status: Optional[str] = Field(default=None, description="Remediation status")


# API Endpoints
@router.post("/consents")
def record_consent(
    request: RecordConsentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record user consent.
    Records consent for data processing purposes with GDPR compliance.
    """
    try:
        result = DataPrivacy.record_consent(
            session=session,
            consent_id=request.consent_id,
            user_id=request.user_id,
            purpose=request.purpose,
            status=request.status,
            expires_at=request.expires_at,
            metadata=request.metadata
        )
        return {
            "success": True,
            "consent": result,
            "message": f"Consent recorded: {request.purpose}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error recording consent: {str(e)}")


@router.get("/consents")
def list_consents(session: Session = Depends(get_db_session)):
    """
    List all consents.
    Returns all recorded consent records.
    """
    try:
        consents = list(DataPrivacy._consents.values())
        return {
            "success": True,
            "consents": consents,
            "count": len(consents)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing consents: {str(e)}")


@router.post("/consents/{consent_id}/withdraw")
def withdraw_consent(
    consent_id: str,
    request: WithdrawConsentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Withdraw consent.
    Allows users to withdraw previously granted consent.
    """
    try:
        result = DataPrivacy.withdraw_consent(
            session=session,
            consent_id=consent_id,
            user_id=request.user_id
        )
        return {
            "success": True,
            "consent": result,
            "message": "Consent withdrawn"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error withdrawing consent: {str(e)}")


@router.post("/consents/check")
def check_consent(
    request: CheckConsentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Check consent status.
    Verifies if user has active consent for a specific purpose.
    """
    try:
        result = DataPrivacy.check_consent(
            session=session,
            user_id=request.user_id,
            purpose=request.purpose
        )
        return {
            "success": True,
            "check": result,
            "message": "Has consent" if result["has_consent"] else "No consent"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking consent: {str(e)}")


@router.get("/consents/statistics")
def get_consent_statistics(session: Session = Depends(get_db_session)):
    """
    Get consent statistics.
    Returns analytics on consent grants and withdrawals.
    """
    try:
        stats = DataPrivacy.get_consent_statistics(session)
        return {
            "success": True,
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")


@router.post("/data-subject-requests")
def create_data_subject_request(
    request: CreateDSRRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create data subject request.
    Creates a GDPR data subject rights request (access, erasure, portability, etc.).
    """
    try:
        result = DataPrivacy.create_data_subject_request(
            session=session,
            request_id=request.request_id,
            user_id=request.user_id,
            right_type=request.right_type,
            description=request.description,
            metadata=request.metadata
        )
        return {
            "success": True,
            "request": result,
            "message": f"Data subject request created: {request.right_type}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating request: {str(e)}")


@router.get("/data-subject-requests")
def list_data_subject_requests(session: Session = Depends(get_db_session)):
    """
    List data subject requests.
    Returns all GDPR data subject rights requests.
    """
    try:
        requests = list(DataPrivacy._data_subject_requests.values())
        return {
            "success": True,
            "requests": requests,
            "count": len(requests)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing requests: {str(e)}")


@router.get("/data-subject-requests/{request_id}")
def get_data_subject_request(
    request_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get data subject request.
    Returns details of a specific data subject rights request.
    """
    try:
        request = DataPrivacy._data_subject_requests.get(request_id)
        if not request:
            raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")

        return {
            "success": True,
            "request": request
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting request: {str(e)}")


@router.post("/data-subject-requests/{request_id}/process")
def process_data_subject_request(
    request_id: str,
    request: ProcessDSRRequest,
    session: Session = Depends(get_db_session)
):
    """
    Process data subject request.
    Processes and completes a GDPR data subject rights request.
    """
    try:
        result = DataPrivacy.process_data_subject_request(
            session=session,
            request_id=request_id,
            response_data=request.response_data
        )
        return {
            "success": True,
            "request": result,
            "message": "Request processed successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")


@router.get("/data-subject-requests/statistics")
def get_dsr_statistics(session: Session = Depends(get_db_session)):
    """
    Get DSR statistics.
    Returns analytics on data subject rights requests.
    """
    try:
        stats = DataPrivacy.get_dsr_statistics(session)
        return {
            "success": True,
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")


@router.post("/retention-policies")
def create_retention_policy(
    request: CreateRetentionPolicyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create retention policy.
    Defines data retention rules for compliance.
    """
    try:
        result = DataPrivacy.create_retention_policy(
            session=session,
            policy_id=request.policy_id,
            name=request.name,
            data_category=request.data_category,
            retention_days=request.retention_days,
            description=request.description,
            auto_delete=request.auto_delete
        )
        return {
            "success": True,
            "policy": result,
            "message": f"Retention policy created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating policy: {str(e)}")


@router.get("/retention-policies")
def list_retention_policies(session: Session = Depends(get_db_session)):
    """
    List retention policies.
    Returns all data retention policies.
    """
    try:
        policies = list(DataPrivacy._retention_policies.values())
        return {
            "success": True,
            "policies": policies,
            "count": len(policies)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing policies: {str(e)}")


@router.post("/anonymize")
def anonymize_data(
    request: AnonymizeDataRequest,
    session: Session = Depends(get_db_session)
):
    """
    Anonymize data.
    Anonymizes sensitive data fields using specified method.
    """
    try:
        result = DataPrivacy.anonymize_data(
            session=session,
            data=request.data,
            fields=request.fields,
            method=request.method
        )
        return {
            "success": True,
            "result": result,
            "message": f"Data anonymized using {request.method}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error anonymizing data: {str(e)}")


@router.post("/breaches")
def report_data_breach(
    request: ReportBreachRequest,
    session: Session = Depends(get_db_session)
):
    """
    Report data breach.
    Reports a data breach incident for compliance tracking.
    """
    try:
        result = DataPrivacy.report_data_breach(
            session=session,
            breach_id=request.breach_id,
            description=request.description,
            severity=request.severity,
            affected_records=request.affected_records,
            data_categories=request.data_categories,
            discovered_at=request.discovered_at,
            metadata=request.metadata
        )
        return {
            "success": True,
            "breach": result,
            "message": f"Data breach reported: {request.severity} severity"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reporting breach: {str(e)}")


@router.get("/breaches")
def list_data_breaches(session: Session = Depends(get_db_session)):
    """
    List data breaches.
    Returns all reported data breach incidents.
    """
    try:
        breaches = list(DataPrivacy._data_breaches.values())
        return {
            "success": True,
            "breaches": breaches,
            "count": len(breaches)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing breaches: {str(e)}")


@router.put("/breaches/{breach_id}")
def update_breach_status(
    breach_id: str,
    request: UpdateBreachRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update breach status.
    Updates containment and remediation status of a data breach.
    """
    try:
        result = DataPrivacy.update_breach_status(
            session=session,
            breach_id=breach_id,
            containment_actions=request.containment_actions,
            authority_notified=request.authority_notified,
            users_notified=request.users_notified,
            remediation_status=request.remediation_status
        )
        return {
            "success": True,
            "breach": result,
            "message": "Breach status updated"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating breach: {str(e)}")


@router.get("/users/{user_id}/privacy-dashboard")
def get_user_privacy_dashboard(
    user_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get user privacy dashboard.
    Returns comprehensive privacy information for a user.
    """
    try:
        dashboard = DataPrivacy.get_user_privacy_dashboard(
            session=session,
            user_id=user_id
        )
        return {
            "success": True,
            "dashboard": dashboard
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting dashboard: {str(e)}")


@router.get("/audit-trail")
def get_audit_trail(
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    Get privacy audit trail.
    Returns recent privacy-related actions.
    """
    try:
        audits = DataPrivacy._privacy_audits[-limit:]
        return {
            "success": True,
            "audit_trail": audits,
            "count": len(audits)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting audit trail: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive privacy and compliance statistics.
    """
    try:
        stats = DataPrivacy.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
