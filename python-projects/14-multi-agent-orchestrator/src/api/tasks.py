"""
Task management API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from src.core.database import get_db_session
from src.core.login_gate import Caller, get_caller
from src.core.logging import logger
from src.models import Task, TaskStatus
from src.workers.task_worker import update_task_status, execute_task

router = APIRouter()


def owned(query, caller: Optional[Caller]):
    """Restrict a task query to the caller's own tasks (admins, and a gate that is off, see all)"""
    if caller is None or caller.is_admin:
        return query
    return query.filter(Task.created_by_user_id == caller.user_id)


def get_owned_task(db: Session, task_id: int, caller: Optional[Caller]) -> Task:
    """The task, or 404: a task that belongs to somebody else looks exactly like one that does not exist"""
    task = owned(db.query(Task), caller).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


# Pydantic models for request/response
class TaskCreate(BaseModel):
    title: str
    description: str
    task_type: str
    priority: int = 5
    input_data: Optional[Dict[str, Any]] = None
    parent_task_id: Optional[int] = None
    assigned_agent_id: Optional[int] = None
    auto_execute: bool = True


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    output_data: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    task_type: str
    status: str
    priority: int
    assigned_agent_id: Optional[int]
    progress_percentage: float
    created_at: str

    class Config:
        from_attributes = True


@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    caller: Optional[Caller] = Depends(get_caller),
) -> List[Dict[str, Any]]:
    """
    List your tasks (all of them for an admin) with optional filtering

    Args:
        status: Filter by task status
        limit: Maximum number of tasks to return
        offset: Number of tasks to skip
        db: Database session

    Returns:
        list: Tasks matching criteria
    """
    query = owned(db.query(Task), caller)

    if status:
        try:
            query = query.filter(Task.status == TaskStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status '{status}'")

    tasks = query.order_by(Task.created_at.desc()).limit(limit).offset(offset).all()

    return [
        {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "task_type": task.task_type,
            "status": task.status.value,
            "priority": task.priority,
            "assigned_agent_id": task.assigned_agent_id,
            "progress_percentage": task.progress_percentage,
            "created_at": task.created_at.isoformat(),
        }
        for task in tasks
    ]


@router.get("/{task_id}")
async def get_task(
    task_id: int,
    db: Session = Depends(get_db_session),
    caller: Optional[Caller] = Depends(get_caller),
) -> Dict[str, Any]:
    """
    Get task details by ID

    Args:
        task_id: Task ID
        db: Database session

    Returns:
        dict: Task details
    """
    task = get_owned_task(db, task_id, caller)

    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "task_type": task.task_type,
        "status": task.status.value,
        "priority": task.priority,
        "assigned_agent_id": task.assigned_agent_id,
        "input_data": task.input_data,
        "output_data": task.output_data,
        "error_message": task.error_message,
        "progress_percentage": task.progress_percentage,
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "parent_task_id": task.parent_task_id,
    }


@router.post("/", status_code=201)
async def create_new_task(
    task: TaskCreate,
    db: Session = Depends(get_db_session),
    caller: Optional[Caller] = Depends(get_caller),
) -> Dict[str, Any]:
    """
    Create a new task

    Args:
        task: Task creation data
        db: Database session

    Returns:
        dict: Created task information
    """
    if task.parent_task_id is not None:
        get_owned_task(db, task.parent_task_id, caller)  # 404 unless it is yours

    try:
        new_task = Task(
            created_by_user_id=caller.user_id if caller else None,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            priority=task.priority,
            status=TaskStatus.PENDING,
            input_data=task.input_data or {},
            parent_task_id=task.parent_task_id,
            assigned_agent_id=task.assigned_agent_id
        )

        db.add(new_task)
        db.commit()
        db.refresh(new_task)

        if task.auto_execute:
            try:
                execute_task.delay(new_task.id)
            except Exception as e:
                # Task row is already created; execution can be retried
                # later even if the broker is unreachable right now.
                logger.warning(f"Could not enqueue execution for task {new_task.id}: {e}")

        return {
            "id": new_task.id,
            "title": new_task.title,
            "description": new_task.description,
            "task_type": new_task.task_type,
            "status": new_task.status.value,
            "priority": new_task.priority,
            "assigned_agent_id": new_task.assigned_agent_id,
            "progress_percentage": new_task.progress_percentage,
            "created_at": new_task.created_at.isoformat(),
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")


@router.patch("/{task_id}")
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    db: Session = Depends(get_db_session),
    caller: Optional[Caller] = Depends(get_caller),
) -> Dict[str, Any]:
    """
    Update task status or output

    Args:
        task_id: Task ID
        task_update: Update data

    Returns:
        dict: Update result
    """
    get_owned_task(db, task_id, caller)

    if task_update.status:
        result = update_task_status.delay(
            task_id=task_id,
            status=task_update.status,
            output_data=task_update.output_data
        )

        update_data = result.get(timeout=5)

        if not update_data.get('success'):
            raise HTTPException(status_code=404, detail=update_data.get('error', 'Failed to update task'))

        return update_data

    raise HTTPException(status_code=400, detail="No valid update fields provided")


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db_session),
    caller: Optional[Caller] = Depends(get_caller),
):
    """
    Delete a task

    Args:
        task_id: Task ID
        db: Database session
    """
    task = get_owned_task(db, task_id, caller)

    db.delete(task)
    db.commit()

    return None


@router.get("/{task_id}/dependencies")
async def get_task_dependencies(
    task_id: int,
    db: Session = Depends(get_db_session),
    caller: Optional[Caller] = Depends(get_caller),
) -> Dict[str, Any]:
    """
    Get task dependencies

    Args:
        task_id: Task ID
        db: Database session

    Returns:
        dict: Task dependencies
    """
    task = get_owned_task(db, task_id, caller)

    dependency_ids = task.get_dependency_ids()

    return {
        "task_id": task_id,
        "dependencies": dependency_ids,
        "is_ready": task.is_ready_to_execute(),
    }
