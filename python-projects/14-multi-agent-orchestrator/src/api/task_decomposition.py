"""
Task Decomposition API endpoints
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.task_decomposition import TaskDecomposition, DecompositionStrategy, TaskComplexity
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class SubtaskDefinition(BaseModel):
    """Subtask definition model"""
    title: str = Field(..., description="Subtask title")
    description: str = Field("", description="Subtask description")
    type: Optional[str] = Field(None, description="Agent type")
    complexity: str = Field(TaskComplexity.MODERATE, description="Task complexity")
    estimated_duration_minutes: int = Field(30, ge=1, description="Estimated duration")
    required_capabilities: List[str] = Field(default=[], description="Required capabilities")
    depends_on: List[int] = Field(default=[], description="Subtask indices this depends on")


class DecomposeTaskRequest(BaseModel):
    """Request model for task decomposition"""
    task_id: int = Field(..., description="Parent task ID")
    strategy: str = Field(DecompositionStrategy.PARALLEL, description="Decomposition strategy")
    subtask_definitions: Optional[List[SubtaskDefinition]] = Field(None, description="Subtask definitions")
    auto_generate: bool = Field(False, description="Auto-generate subtasks")


# Endpoints

@router.post("/decompose")
async def decompose_task(
    request: DecomposeTaskRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Decompose a task into subtasks.

    Strategies:
    - **sequential**: Subtasks execute one after another
    - **parallel**: Subtasks execute simultaneously
    - **hierarchical**: Root task followed by dependent subtasks
    - **pipeline**: Data flows through processing stages
    - **map_reduce**: Parallel processing followed by aggregation

    Can provide custom subtask definitions or use auto_generate mode.
    Auto-generate mode uses task type and description to create subtasks.
    """
    try:
        # Convert Pydantic models to dicts
        subtask_defs = None
        if request.subtask_definitions:
            subtask_defs = [st.dict() for st in request.subtask_definitions]

        result = TaskDecomposition.decompose_task(
            session=db,
            task_id=request.task_id,
            strategy=request.strategy,
            subtask_definitions=subtask_defs,
            auto_generate=request.auto_generate
        )

        return {
            "success": True,
            **result,
            "message": f"Task decomposed into {result['subtask_count']} subtasks"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to decompose task: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{parent_task_id}/subtasks")
async def get_subtasks(
    parent_task_id: int,
    include_status: bool = Query(True, description="Include execution status"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get all subtasks for a parent task.

    Returns:
    - List of subtasks
    - Decomposition strategy used
    - Progress statistics (if include_status=true)
    """
    try:
        result = TaskDecomposition.get_subtasks(
            session=db,
            parent_task_id=parent_task_id,
            include_status=include_status
        )

        return {
            "success": True,
            **result,
            "message": f"Retrieved {result.get('total_subtasks', 0)} subtasks"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get subtasks: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{task_id}/complexity")
async def estimate_complexity(
    task_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Estimate task complexity.

    Analyzes task description and characteristics to estimate:
    - Complexity level (simple/moderate/complex/very_complex)
    - Recommended number of subtasks
    - Recommended decomposition strategy

    Useful for planning before decomposition.
    """
    try:
        result = TaskDecomposition.estimate_complexity(
            session=db,
            task_id=task_id
        )

        return {
            "success": True,
            **result,
            "message": f"Task complexity: {result['complexity']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to estimate complexity: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{parent_task_id}/merge")
async def merge_subtask_results(
    parent_task_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Merge results from completed subtasks.

    Aggregates results from all subtasks and updates parent task status.
    If all subtasks are completed, marks parent task as completed.

    Returns merged results from all subtasks.
    """
    try:
        result = TaskDecomposition.merge_subtask_results(
            session=db,
            parent_task_id=parent_task_id
        )

        return {
            "success": True,
            **result,
            "message": "Subtask results merged" if result.get("all_subtasks_completed") else "Some subtasks still pending"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to merge results: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{subtask_id}/recommend-agents")
async def recommend_agents(
    subtask_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Recommend agents for a subtask.

    Analyzes subtask requirements and agent capabilities to recommend
    the best-suited agents.

    Returns agents ranked by match score based on:
    - Required capabilities
    - Agent availability
    - Agent expertise
    """
    try:
        result = TaskDecomposition.recommend_agents(
            session=db,
            subtask_id=subtask_id
        )

        return {
            "success": True,
            **result,
            "message": f"Found {len(result['recommendations'])} agent recommendations"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to recommend agents: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/strategies")
async def list_strategies() -> Dict[str, Any]:
    """
    List all decomposition strategies.

    Returns available strategies with descriptions and use cases.

    Strategies:
    - **sequential**: For ordered task execution
    - **parallel**: For independent task execution
    - **hierarchical**: For dependent task hierarchies
    - **pipeline**: For data transformation workflows
    - **map_reduce**: For parallel processing with aggregation
    """
    try:
        result = TaskDecomposition.list_strategies()

        return {
            "success": True,
            **result,
            "message": "List of all decomposition strategies"
        }

    except Exception as e:
        logger.error(f"Failed to list strategies: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/complexity-levels")
async def list_complexity_levels() -> Dict[str, Any]:
    """
    List all complexity levels.

    Returns complexity levels with descriptions and characteristics.
    """
    levels = [
        {
            "level": TaskComplexity.SIMPLE,
            "description": "Simple, straightforward task",
            "typical_subtasks": 1,
            "estimated_duration": "< 30 minutes"
        },
        {
            "level": TaskComplexity.MODERATE,
            "description": "Moderate complexity requiring some planning",
            "typical_subtasks": "2-3",
            "estimated_duration": "30 minutes - 2 hours"
        },
        {
            "level": TaskComplexity.COMPLEX,
            "description": "Complex task requiring decomposition",
            "typical_subtasks": "4-6",
            "estimated_duration": "2-8 hours"
        },
        {
            "level": TaskComplexity.VERY_COMPLEX,
            "description": "Very complex task requiring careful planning",
            "typical_subtasks": "7+",
            "estimated_duration": "> 8 hours"
        }
    ]

    return {
        "success": True,
        "total_levels": len(levels),
        "levels": levels,
        "message": "List of all complexity levels"
    }
