"""
Task Dependency API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.task_dependency import TaskDependency, DependencyType
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class AddDependencyRequest(BaseModel):
    """Request model for adding a dependency"""
    task_id: int = Field(..., description="Task that has the dependency")
    depends_on_task_id: int = Field(..., description="Task that must complete first")
    dependency_type: str = Field(
        default=DependencyType.BLOCKS,
        description="Type of dependency (blocks/requires/related)"
    )


class AddChainRequest(BaseModel):
    """Request model for adding a dependency chain"""
    task_ids: List[int] = Field(
        ...,
        min_items=2,
        description="Task IDs in execution order"
    )


class RemoveDependencyRequest(BaseModel):
    """Request model for removing a dependency"""
    task_id: int = Field(..., description="Task that has the dependency")
    depends_on_task_id: int = Field(..., description="Dependency to remove")


class ValidateGraphRequest(BaseModel):
    """Request model for graph validation"""
    task_ids: Optional[List[int]] = Field(
        default=None,
        description="Optional list of task IDs to validate"
    )


# Endpoints

@router.post("/add")
async def add_dependency(
    request: AddDependencyRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Add a dependency between two tasks.

    Creates a dependency relationship where one task must complete
    before another can start. Automatically validates for cycles.
    """
    try:
        result = TaskDependency.add_dependency(
            session=db,
            task_id=request.task_id,
            depends_on_task_id=request.depends_on_task_id,
            dependency_type=request.dependency_type
        )

        return {
            "success": True,
            "dependency": result,
            "message": f"Dependency added: task {request.task_id} depends on {request.depends_on_task_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add dependency: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/add-chain")
async def add_dependency_chain(
    request: AddChainRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Add dependencies in a chain (A -> B -> C -> D).

    Creates a sequential dependency chain where each task depends
    on the previous task completing. Useful for workflows with
    strict ordering requirements.
    """
    try:
        dependencies = TaskDependency.add_dependency_chain(
            session=db,
            task_ids=request.task_ids
        )

        return {
            "success": True,
            "total_dependencies": len(dependencies),
            "dependencies": dependencies,
            "message": f"Created dependency chain of {len(request.task_ids)} tasks"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add dependency chain: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/remove")
async def remove_dependency(
    request: RemoveDependencyRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Remove a dependency between two tasks.

    Removes the dependency relationship, allowing the dependent
    task to execute without waiting for the other task.
    """
    try:
        removed = TaskDependency.remove_dependency(
            session=db,
            task_id=request.task_id,
            depends_on_task_id=request.depends_on_task_id
        )

        if not removed:
            return {
                "success": False,
                "message": f"Dependency not found: task {request.task_id} -> {request.depends_on_task_id}"
            }

        return {
            "success": True,
            "message": f"Dependency removed: task {request.task_id} -> {request.depends_on_task_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to remove dependency: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/task/{task_id}")
async def get_task_dependencies(
    task_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get all dependencies for a task.

    Returns both:
    - Tasks that this task depends on (prerequisites)
    - Tasks that depend on this task (dependents)
    """
    try:
        dependencies = TaskDependency.get_task_dependencies(
            session=db,
            task_id=task_id
        )

        return {
            "success": True,
            "dependencies": dependencies,
            "message": f"Retrieved dependencies for task {task_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get task dependencies: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/task/{task_id}/ready")
async def is_task_ready(
    task_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Check if a task is ready to execute.

    A task is ready when all its dependencies have been completed.
    Returns blocking tasks if any exist.
    """
    try:
        readiness = TaskDependency.is_task_ready(
            session=db,
            task_id=task_id
        )

        return {
            "success": True,
            "readiness": readiness,
            "message": readiness["message"]
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to check task readiness: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/execution-order")
async def get_execution_order(
    task_ids: Optional[List[int]] = Query(None, description="Optional task IDs to order"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get topological execution order for tasks.

    Returns tasks grouped by execution level. Tasks in the same level
    can execute in parallel since they don't depend on each other.

    Uses topological sort (Kahn's algorithm).
    """
    try:
        execution_order = TaskDependency.get_execution_order(
            session=db,
            task_ids=task_ids
        )

        # Calculate some statistics
        total_tasks = sum(len(level) for level in execution_order)
        max_parallelism = max(len(level) for level in execution_order) if execution_order else 0

        return {
            "success": True,
            "execution_order": execution_order,
            "total_levels": len(execution_order),
            "total_tasks": total_tasks,
            "max_parallelism": max_parallelism,
            "message": f"Execution order with {len(execution_order)} levels"
        }

    except Exception as e:
        logger.error(f"Failed to get execution order: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/validate")
async def validate_dependency_graph(
    request: ValidateGraphRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Validate the dependency graph.

    Checks for:
    - Circular dependencies (cycles)
    - Orphaned dependencies (references to non-existent tasks)
    - Long dependency chains (warning)

    Returns validation errors and warnings.
    """
    try:
        validation = TaskDependency.validate_dependency_graph(
            session=db,
            task_ids=request.task_ids
        )

        return {
            "success": True,
            "validation": validation,
            "message": "Valid dependency graph" if validation["valid"] else "Validation errors found"
        }

    except Exception as e:
        logger.error(f"Failed to validate dependency graph: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/graph")
async def get_dependency_graph(
    task_ids: Optional[List[int]] = Query(None, description="Optional task IDs to include"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get dependency graph data for visualization.

    Returns nodes and edges in a format suitable for graph
    visualization libraries (e.g., vis.js, d3.js, cytoscape).
    """
    try:
        graph = TaskDependency.get_dependency_graph(
            session=db,
            task_ids=task_ids
        )

        return {
            "success": True,
            "graph": graph,
            "message": f"Dependency graph with {graph['total_nodes']} nodes and {graph['total_edges']} edges"
        }

    except Exception as e:
        logger.error(f"Failed to get dependency graph: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/ready-tasks")
async def get_ready_tasks(
    task_ids: Optional[List[int]] = Query(None, description="Optional task IDs to check"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get all tasks that are ready to execute.

    Returns tasks where all dependencies have been completed.
    Useful for schedulers to find next tasks to assign.
    """
    try:
        ready_tasks = TaskDependency.get_ready_tasks(
            session=db,
            task_ids=task_ids
        )

        return {
            "success": True,
            "total_ready": len(ready_tasks),
            "ready_tasks": ready_tasks,
            "message": f"Found {len(ready_tasks)} ready tasks"
        }

    except Exception as e:
        logger.error(f"Failed to get ready tasks: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/types")
async def list_dependency_types() -> Dict[str, Any]:
    """
    List all dependency relationship types.

    Returns the available types of dependencies that can be
    created between tasks.
    """
    types = [
        {
            "type": DependencyType.BLOCKS,
            "description": "Task A blocks task B - A must complete before B starts",
            "example": "Build must complete before Deploy"
        },
        {
            "type": DependencyType.REQUIRES,
            "description": "Task B requires task A - same as blocks, reverse direction",
            "example": "Deploy requires Build (same as Build blocks Deploy)"
        },
        {
            "type": DependencyType.RELATED,
            "description": "Tasks are related but not blocking",
            "example": "Documentation update related to feature implementation"
        }
    ]

    return {
        "success": True,
        "total_types": len(types),
        "types": types,
        "default_type": DependencyType.BLOCKS,
        "message": "List of all dependency types"
    }
