"""
Human Approval Gate API

REST API endpoints for managing human-in-the-loop approval gates.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.human_approval import (
    HumanApproval,
    ApprovalType,
    ApprovalStatus,
    ApprovalPriority
)


router = APIRouter()


# Request/Response Models
class CreateApprovalRequest(BaseModel):
    workflow_id: str = Field(..., description="Workflow ID")
    agent_id: int = Field(..., description="Agent ID requesting approval")
    approval_type: str = Field(..., description="Type of approval")
    title: str = Field(..., description="Approval title")
    description: str = Field(..., description="Detailed description")
    context: dict = Field(..., description="Context information")
    priority: str = Field(ApprovalPriority.MEDIUM, description="Priority level")
    required_approvers: Optional[List[str]] = Field(None, description="Required approver user IDs")
    timeout_minutes: int = Field(60, description="Timeout in minutes")
    auto_approve_conditions: Optional[dict] = Field(None, description="Auto-approve conditions")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class ApproveRequestModel(BaseModel):
    approver_user_id: str = Field(..., description="Approver user ID")
    approver_name: str = Field(..., description="Approver name")
    comments: Optional[str] = Field(None, description="Approval comments")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RejectRequestModel(BaseModel):
    rejector_user_id: str = Field(..., description="Rejector user ID")
    rejector_name: str = Field(..., description="Rejector name")
    reason: str = Field(..., description="Rejection reason")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class CancelRequestModel(BaseModel):
    cancelled_by: str = Field(..., description="User/system cancelling")
    reason: str = Field(..., description="Cancellation reason")


@router.post("/requests")
def create_approval_request(
    request: CreateApprovalRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create approval request.

    Creates a new human approval gate that pauses workflow execution
    until a human reviews and approves or rejects the request.
    """
    try:
        approval_request = HumanApproval.create_approval_request(
            session=session,
            workflow_id=request.workflow_id,
            agent_id=request.agent_id,
            approval_type=request.approval_type,
            title=request.title,
            description=request.description,
            context=request.context,
            priority=request.priority,
            required_approvers=request.required_approvers,
            timeout_minutes=request.timeout_minutes,
            auto_approve_conditions=request.auto_approve_conditions,
            metadata=request.metadata
        )

        return {
            "success": True,
            "approval_request": approval_request,
            "message": f"Approval request created: {approval_request['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/requests/{request_id}/approve")
def approve_request(
    request_id: str,
    request: ApproveRequestModel,
    session: Session = Depends(get_db_session)
):
    """
    Approve approval request.

    Marks the request as approved and allows the workflow to continue.
    If multiple approvers are required, tracks individual approvals.
    """
    try:
        approval_request = HumanApproval.approve_request(
            session=session,
            request_id=request_id,
            approver_user_id=request.approver_user_id,
            approver_name=request.approver_name,
            comments=request.comments,
            metadata=request.metadata
        )

        return {
            "success": True,
            "approval_request": approval_request,
            "message": f"Request approved by {request.approver_name}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/requests/{request_id}/reject")
def reject_request(
    request_id: str,
    request: RejectRequestModel,
    session: Session = Depends(get_db_session)
):
    """
    Reject approval request.

    Marks the request as rejected and prevents the workflow from continuing.
    Workflow will need to handle the rejection appropriately.
    """
    try:
        approval_request = HumanApproval.reject_request(
            session=session,
            request_id=request_id,
            rejector_user_id=request.rejector_user_id,
            rejector_name=request.rejector_name,
            reason=request.reason,
            metadata=request.metadata
        )

        return {
            "success": True,
            "approval_request": approval_request,
            "message": f"Request rejected by {request.rejector_name}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/requests/{request_id}/cancel")
def cancel_request(
    request_id: str,
    request: CancelRequestModel,
    session: Session = Depends(get_db_session)
):
    """
    Cancel approval request.

    Allows workflow or system to cancel a pending approval request
    when it's no longer needed.
    """
    try:
        approval_request = HumanApproval.cancel_request(
            session=session,
            request_id=request_id,
            cancelled_by=request.cancelled_by,
            reason=request.reason
        )

        return {
            "success": True,
            "approval_request": approval_request,
            "message": "Request cancelled"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/requests/{request_id}")
def get_approval_request(
    request_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get approval request details.

    Returns complete information about an approval request including
    status, approvals, rejections, and context.
    """
    try:
        approval_request = HumanApproval.get_approval_request(
            session=session,
            request_id=request_id
        )

        return {
            "success": True,
            "approval_request": approval_request
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/requests")
def list_approval_requests(
    status: Optional[str] = None,
    approval_type: Optional[str] = None,
    priority: Optional[str] = None,
    workflow_id: Optional[str] = None,
    agent_id: Optional[int] = None,
    session: Session = Depends(get_db_session)
):
    """
    List approval requests.

    Returns approval requests with optional filtering by status,
    type, priority, workflow, or agent.
    """
    try:
        result = HumanApproval.list_approval_requests(
            session=session,
            status=status,
            approval_type=approval_type,
            priority=priority,
            workflow_id=workflow_id,
            agent_id=agent_id
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending")
def get_pending_approvals(
    approver_user_id: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get pending approval requests.

    Returns all pending requests, optionally filtered by approver.
    Sorted by priority (critical first) and creation time.
    """
    try:
        result = HumanApproval.get_pending_approvals(
            session=session,
            approver_user_id=approver_user_id
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/history")
def get_user_history(
    user_id: str,
    limit: int = 20,
    session: Session = Depends(get_db_session)
):
    """
    Get user's approval history.

    Returns all approvals and rejections by a specific user
    with statistics and performance metrics.
    """
    try:
        result = HumanApproval.get_user_approval_history(
            session=session,
            user_id=user_id,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}/approvals")
def get_workflow_approvals(
    workflow_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get workflow approval requests.

    Returns all approval requests for a specific workflow with
    complete approval history and statistics.
    """
    try:
        result = HumanApproval.get_workflow_approvals(
            session=session,
            workflow_id=workflow_id
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/expired/check")
def check_expired_requests(
    session: Session = Depends(get_db_session)
):
    """
    Check for expired requests.

    Finds and marks all expired approval requests.
    Returns list of newly expired requests.
    """
    try:
        expired = HumanApproval.check_expired_requests(session=session)

        return {
            "success": True,
            "expired_requests": expired,
            "count": len(expired)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get approval system statistics.

    Returns aggregate metrics including approval rates, response times,
    status distribution, and type distribution.
    """
    try:
        stats = HumanApproval.get_approval_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approval-types")
def list_approval_types():
    """
    List all approval types.

    Returns all available approval types and their descriptions.
    """
    return {
        "success": True,
        "approval_types": [
            {"type": ApprovalType.EXECUTE_TASK, "description": "Execute a task or operation"},
            {"type": ApprovalType.DEPLOY_CODE, "description": "Deploy code to production"},
            {"type": ApprovalType.SPEND_BUDGET, "description": "Spend budget or incur costs"},
            {"type": ApprovalType.DATA_ACCESS, "description": "Access sensitive data"},
            {"type": ApprovalType.EXTERNAL_API, "description": "Call external API"},
            {"type": ApprovalType.DELETE_DATA, "description": "Delete data or resources"},
            {"type": ApprovalType.MODIFY_CONFIG, "description": "Modify system configuration"},
            {"type": ApprovalType.ESCALATE_ISSUE, "description": "Escalate an issue"},
            {"type": ApprovalType.GENERAL, "description": "General approval request"}
        ]
    }


@router.get("/statuses")
def list_approval_statuses():
    """
    List all approval statuses.

    Returns all possible approval request statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": ApprovalStatus.PENDING, "description": "Waiting for approval"},
            {"status": ApprovalStatus.APPROVED, "description": "Approved and completed"},
            {"status": ApprovalStatus.REJECTED, "description": "Rejected by approver"},
            {"status": ApprovalStatus.EXPIRED, "description": "Expired before approval"},
            {"status": ApprovalStatus.CANCELLED, "description": "Cancelled by workflow"}
        ]
    }


@router.get("/priorities")
def list_approval_priorities():
    """
    List all approval priorities.

    Returns all priority levels for approval requests.
    """
    return {
        "success": True,
        "priorities": [
            {"priority": ApprovalPriority.CRITICAL, "description": "Critical - requires immediate attention"},
            {"priority": ApprovalPriority.HIGH, "description": "High priority"},
            {"priority": ApprovalPriority.MEDIUM, "description": "Medium priority (default)"},
            {"priority": ApprovalPriority.LOW, "description": "Low priority"}
        ]
    }
