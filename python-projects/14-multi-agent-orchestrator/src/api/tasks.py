"""
Task management API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from src.core.database import get_db_session
from src.models import Task, TaskStatus
from src.workers.task_worker import create_task, update_task_status

router = APIRouter()


# Pydantic models for request/response
class TaskCreate(BaseModel):
    title: str
    description: str
    task_type: str
    priority: int = 5
    input_data: Optional[Dict[str, Any]] = None
    parent_task_id: Optional[int] = None


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
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    """
    List all tasks with optional filtering

    Args:
        status: Filter by task status
        limit: Maximum number of tasks to return
        offset: Number of tasks to skip
        db: Database session

    Returns:
        list: Tasks matching criteria
    """
    query = db.query(Task)

    if status:
        query = query.filter(Task.status == TaskStatus(status))

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
async def get_task(task_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Get task details by ID

    Args:
        task_id: Task ID
        db: Database session

    Returns:
        dict: Task details
    """
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

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
async def create_new_task(task: TaskCreate) -> Dict[str, Any]:
    """
    Create a new task

    Args:
        task: Task creation data

    Returns:
        dict: Created task information
    """
    result = create_task.delay(
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        priority=task.priority,
        input_data=task.input_data,
        parent_task_id=task.parent_task_id
    )

    # Wait for task creation (should be fast)
    task_data = result.get(timeout=5)

    if not task_data.get('success'):
        raise HTTPException(status_code=500, detail=task_data.get('error', 'Failed to create task'))

    return task_data


@router.patch("/{task_id}")
async def update_task(task_id: int, task_update: TaskUpdate) -> Dict[str, Any]:
    """
    Update task status or output

    Args:
        task_id: Task ID
        task_update: Update data

    Returns:
        dict: Update result
    """
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
async def delete_task(task_id: int, db: Session = Depends(get_db_session)):
    """
    Delete a task

    Args:
        task_id: Task ID
        db: Database session
    """
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    db.delete(task)
    db.commit()

    return None


@router.get("/{task_id}/dependencies")
async def get_task_dependencies(task_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Get task dependencies

    Args:
        task_id: Task ID
        db: Database session

    Returns:
        dict: Task dependencies
    """
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    dependency_ids = task.get_dependency_ids()

    return {
        "task_id": task_id,
        "dependencies": dependency_ids,
        "is_ready": task.is_ready_to_execute(),
    }
