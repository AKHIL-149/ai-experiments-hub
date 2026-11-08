"""
Workflow tracker API: progress of your workflows and the result of every step's task.

Starting, cancelling and deleting still go through /api/workflow-engine/workflows; this is the read side.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.workflow_engine import workflow_access
from src.core.database import get_db_session
from src.core.login_gate import Caller, get_caller
from src.models.workflow import WorkflowStatus
from src.services import workflow_tracker

router = APIRouter()

VALID_STATUSES = {s.value for s in WorkflowStatus}


@router.get("")
def list_tracked_workflows(
    status_filter: Optional[str] = Query(None, alias="status", description="pending, running, paused, completed, failed or cancelled"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    caller: Optional[Caller] = Depends(get_caller),
) -> Dict[str, Any]:
    """Your workflows, newest first, each with step progress (admins see everyone's)"""
    if status_filter and status_filter not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"status must be one of {', '.join(sorted(VALID_STATUSES))}",
        )
    return workflow_tracker.list_workflows(
        db,
        owner_id=None if caller is None or caller.is_admin else caller.user_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/{workflow_id}", dependencies=[Depends(workflow_access)])
def get_tracked_workflow(workflow_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """One workflow with every step: which agent ran it, how long it took and what it produced"""
    detail = workflow_tracker.workflow_detail(db, workflow_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} not found")
    return detail
