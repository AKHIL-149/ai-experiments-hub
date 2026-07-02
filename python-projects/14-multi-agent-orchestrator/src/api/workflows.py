"""
Workflow API endpoints
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.services.workflow_service import workflow_service
from src.workflows import get_workflow_template, list_workflow_templates
from src.core.database import get_db_session
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


# LangGraph Workflow Template Endpoints

class WorkflowTemplateExecuteRequest(BaseModel):
    """Request model for executing a workflow template"""
    input_data: Dict[str, Any]
    task_id: Optional[int] = None
    workflow_id: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "input_data": {
                    "topic": "microservices architecture",
                    "depth": "deep"
                },
                "task_id": 123,
                "workflow_id": "wf_001"
            }
        }


class WorkflowTemplateResponse(BaseModel):
    """Response model for workflow template execution"""
    workflow_id: str
    template_name: str
    status: str
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]]
    agent_results: Dict[str, Any]
    total_cost: float
    total_tokens: int
    execution_time_seconds: Optional[float]
    started_at: str
    completed_at: Optional[str]
    error: Optional[str] = None


@router.get("/templates")
async def list_templates():
    """
    List all available workflow templates

    Returns:
        dict: Available workflow templates with descriptions
    """
    try:
        templates = list_workflow_templates()
        return {
            "templates": templates,
            "count": len(templates)
        }
    except Exception as e:
        logger.error(f"Failed to list workflow templates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/templates/{template_name}")
async def get_template_info(template_name: str):
    """
    Get information about a specific workflow template

    Args:
        template_name: Name of the workflow template

    Returns:
        dict: Template information including description and example usage
    """
    try:
        workflow = get_workflow_template(template_name)

        return {
            "name": workflow.config.name,
            "description": workflow.config.description,
            "version": workflow.config.version,
            "timeout_seconds": workflow.config.timeout_seconds,
            "max_retries": workflow.config.max_retries,
            "parallel_execution": workflow.config.parallel_execution,
            "template_id": template_name,
            "examples": _get_template_example(template_name)
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get template info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/templates/{template_name}/execute")
async def execute_template(
    template_name: str,
    request: WorkflowTemplateExecuteRequest,
    db: Session = Depends(get_db_session)
):
    """
    Execute a workflow template

    Args:
        template_name: Name of the workflow template to execute
        request: Execution request with input data
        db: Database session

    Returns:
        WorkflowTemplateResponse: Workflow execution result
    """
    try:
        logger.info(f"Executing workflow template: {template_name}")

        # Get workflow template
        workflow = get_workflow_template(template_name)

        # Execute workflow
        result = await workflow.execute(
            input_data=request.input_data,
            workflow_id=request.workflow_id,
            task_id=request.task_id
        )

        return {
            "workflow_id": result.workflow_id,
            "template_name": template_name,
            "status": result.status.value,
            "input_data": result.input_data,
            "output_data": result.output_data,
            "agent_results": result.agent_results,
            "total_cost": result.total_cost,
            "total_tokens": result.total_tokens,
            "execution_time_seconds": result.execution_time_seconds,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "error": result.error
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Workflow template execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def _get_template_example(template_name: str) -> Dict[str, Any]:
    """Get example input data for a template"""
    examples = {
        "research_write": {
            "description": "Research a topic and write content about it",
            "input_data": {
                "topic": "advantages of microservices architecture",
                "depth": "deep",
                "focus_areas": ["scalability", "maintainability", "deployment"],
                "content_type": "blog_post",
                "style": "professional",
                "audience": "software engineers"
            }
        },
        "code_review": {
            "description": "Generate code, review it, and apply fixes if needed",
            "input_data": {
                "task_type": "generate",
                "language": "python",
                "requirements": """
                Create a REST API endpoint for user authentication
                with JWT tokens, rate limiting, and input validation.
                Include error handling and logging.
                """
            }
        },
        "analysis_planning": {
            "description": "Analyze data, create a plan, and execute based on complexity",
            "input_data": {
                "goal": "Build a scalable chat application",
                "data": {
                    "expected_users": 100000,
                    "concurrent_connections": 5000,
                    "message_volume": "1M messages/day",
                    "budget": "$50,000"
                },
                "constraints": [
                    "Must support real-time messaging",
                    "Should scale horizontally",
                    "Need 99.9% uptime"
                ]
            }
        }
    }

    return examples.get(template_name, {
        "description": "No example available",
        "input_data": {}
    })
