"""
Workflow API endpoints
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.services.workflow_service import workflow_service
from src.core.logging import logger


router = APIRouter()


# Pydantic models

class WorkflowExecuteRequest(BaseModel):
    """Workflow execution request"""
    task_id: int
    task_title: str
    task_description: str
    task_type: str = "general"
    priority: int = Field(5, ge=1, le=10)
    input_data: Optional[Dict[str, Any]] = None
    workflow_type: str = "simple"


class CustomWorkflowRequest(BaseModel):
    """Custom workflow execution request"""
    task_id: int
    task_title: str
    task_description: str
    nodes: List[str]
    edges: List[tuple]
    input_data: Optional[Dict[str, Any]] = None


class WorkflowResponse(BaseModel):
    """Workflow execution response"""
    task_id: int
    status: str
    progress: int
    workflow_path: List[str]
    total_tokens: int
    total_cost: float
    execution_time: Optional[float]
    messages: List[Dict[str, str]]
    outputs: Dict[str, Any]


# Endpoints

@router.post("/execute", response_model=WorkflowResponse)
def execute_workflow(request: WorkflowExecuteRequest):
    """
    Execute a workflow

    Args:
        request: Workflow execution request

    Returns:
        WorkflowResponse: Workflow execution result
    """
    try:
        logger.info(f"Executing workflow for task {request.task_id}")

        # Execute workflow
        final_state = workflow_service.execute_workflow(
            task_id=request.task_id,
            task_title=request.task_title,
            task_description=request.task_description,
            task_type=request.task_type,
            priority=request.priority,
            input_data=request.input_data,
            workflow_type=request.workflow_type
        )

        # Build response
        return WorkflowResponse(
            task_id=final_state["task_id"],
            status=final_state["status"],
            progress=final_state["progress"],
            workflow_path=final_state["workflow_path"],
            total_tokens=final_state["total_tokens"],
            total_cost=final_state["total_cost"],
            execution_time=final_state.get("execution_time"),
            messages=final_state["messages"],
            outputs={
                "research": final_state.get("research_output"),
                "code": final_state.get("code_output"),
                "review": final_state.get("review_output"),
                "test": final_state.get("test_output"),
                "document": final_state.get("document_output")
            }
        )

    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/execute/custom", response_model=WorkflowResponse)
def execute_custom_workflow(request: CustomWorkflowRequest):
    """
    Execute a custom workflow

    Args:
        request: Custom workflow request

    Returns:
        WorkflowResponse: Workflow execution result
    """
    try:
        logger.info(f"Executing custom workflow for task {request.task_id}")

        # Execute custom workflow
        final_state = workflow_service.execute_custom_workflow(
            task_id=request.task_id,
            task_title=request.task_title,
            task_description=request.task_description,
            nodes=request.nodes,
            edges=request.edges,
            input_data=request.input_data
        )

        # Build response
        return WorkflowResponse(
            task_id=final_state["task_id"],
            status=final_state["status"],
            progress=final_state["progress"],
            workflow_path=final_state["workflow_path"],
            total_tokens=final_state["total_tokens"],
            total_cost=final_state["total_cost"],
            execution_time=final_state.get("execution_time"),
            messages=final_state["messages"],
            outputs={
                "research": final_state.get("research_output"),
                "code": final_state.get("code_output"),
                "review": final_state.get("review_output"),
                "test": final_state.get("test_output"),
                "document": final_state.get("document_output")
            }
        )

    except Exception as e:
        logger.error(f"Custom workflow execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/workflows")
def list_workflows():
    """
    List available workflows

    Returns:
        list: Available workflows
    """
    return workflow_service.list_workflows()


@router.get("/workflows/{workflow_type}")
def get_workflow_info(workflow_type: str):
    """
    Get workflow information

    Args:
        workflow_type: Workflow type

    Returns:
        dict: Workflow information
    """
    return workflow_service.get_workflow_info(workflow_type)


@router.get("/example")
def get_workflow_example():
    """
    Get workflow execution example

    Returns:
        dict: Example workflow request
    """
    return {
        "description": "Example workflow execution",
        "simple_workflow": {
            "task_id": 1,
            "task_title": "Build REST API",
            "task_description": "Build a REST API with FastAPI",
            "task_type": "coding",
            "priority": 7,
            "workflow_type": "simple",
            "input_data": {
                "framework": "FastAPI",
                "database": "PostgreSQL"
            }
        },
        "custom_workflow": {
            "task_id": 2,
            "task_title": "Custom Task",
            "task_description": "Execute custom workflow",
            "nodes": ["research", "code", "test"],
            "edges": [
                ["research", "code"],
                ["code", "test"],
                ["test", "END"]
            ]
        }
    }
