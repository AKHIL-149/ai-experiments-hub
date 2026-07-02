"""
Agent management API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from src.core.database import get_db_session
from src.models import Agent, AgentRole, AgentStatus, AgentExecution, ExecutionStatus
from src.services.agent_service import AgentService
from src.workers.agent_worker import create_agent, update_agent_status, get_available_agents

router = APIRouter()


# Pydantic models for request/response
class AgentCreate(BaseModel):
    name: str
    role: str
    description: Optional[str] = None
    llm_provider: str = "openai"
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None


class AgentUpdate(BaseModel):
    status: Optional[str] = None
    current_task_id: Optional[int] = None


class AgentResponse(BaseModel):
    id: int
    name: str
    role: str
    status: str
    current_task_id: Optional[int]
    tasks_completed: int
    tasks_failed: int

    class Config:
        from_attributes = True


@router.get("/", response_model=List[AgentResponse])
async def list_agents(
    role: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    """
    List all agents with optional filtering

    Args:
        role: Filter by agent role
        status: Filter by agent status
        db: Database session

    Returns:
        list: Agents matching criteria
    """
    query = db.query(Agent)

    if role:
        query = query.filter(Agent.role == AgentRole(role))

    if status:
        query = query.filter(Agent.status == AgentStatus(status))

    agents = query.all()

    return [
        {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role.value,
            "status": agent.status.value,
            "current_task_id": agent.current_task_id,
            "tasks_completed": agent.tasks_completed,
            "tasks_failed": agent.tasks_failed,
        }
        for agent in agents
    ]


@router.get("/available")
async def list_available_agents(role: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get available (idle) agents

    Args:
        role: Optional role filter

    Returns:
        list: Available agents
    """
    result = get_available_agents.delay(role=role)
    agents = result.get(timeout=5)

    return agents


@router.get("/{agent_id}")
async def get_agent(agent_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Get agent details by ID

    Args:
        agent_id: Agent ID
        db: Database session

    Returns:
        dict: Agent details
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role.value,
        "description": agent.description,
        "status": agent.status.value,
        "current_task_id": agent.current_task_id,
        "llm_provider": agent.llm_provider,
        "llm_model": agent.llm_model,
        "tasks_completed": agent.tasks_completed,
        "tasks_failed": agent.tasks_failed,
        "total_cost": agent.total_cost,
        "average_task_duration_seconds": agent.average_task_duration_seconds,
        "created_at": agent.created_at.isoformat(),
        "last_active_at": agent.last_active_at.isoformat() if agent.last_active_at else None,
    }


@router.post("/", status_code=201)
async def create_new_agent(agent: AgentCreate) -> Dict[str, Any]:
    """
    Create a new agent

    Args:
        agent: Agent creation data

    Returns:
        dict: Created agent information
    """
    result = create_agent.delay(
        name=agent.name,
        role=agent.role,
        description=agent.description,
        llm_provider=agent.llm_provider,
        llm_model=agent.llm_model,
        system_prompt=agent.system_prompt
    )

    agent_data = result.get(timeout=5)

    if not agent_data.get('success'):
        raise HTTPException(status_code=400, detail=agent_data.get('error', 'Failed to create agent'))

    return agent_data


@router.patch("/{agent_id}")
async def update_agent(agent_id: int, agent_update: AgentUpdate) -> Dict[str, Any]:
    """
    Update agent status or current task

    Args:
        agent_id: Agent ID
        agent_update: Update data

    Returns:
        dict: Update result
    """
    if agent_update.status:
        result = update_agent_status.delay(
            agent_id=agent_id,
            status=agent_update.status,
            current_task_id=agent_update.current_task_id
        )

        update_data = result.get(timeout=5)

        if not update_data.get('success'):
            raise HTTPException(status_code=404, detail=update_data.get('error', 'Failed to update agent'))

        return update_data

    raise HTTPException(status_code=400, detail="No valid update fields provided")


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: int, db: Session = Depends(get_db_session)):
    """
    Delete an agent

    Args:
        agent_id: Agent ID
        db: Database session
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Don't delete if agent is currently working
    if agent.status == AgentStatus.BUSY:
        raise HTTPException(status_code=400, detail="Cannot delete agent while busy")

    db.delete(agent)
    db.commit()

    return None


@router.get("/{agent_id}/metrics")
async def get_agent_metrics(agent_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Get agent performance metrics

    Args:
        agent_id: Agent ID
        db: Database session

    Returns:
        dict: Agent metrics
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    total_tasks = agent.tasks_completed + agent.tasks_failed
    success_rate = (agent.tasks_completed / total_tasks * 100) if total_tasks > 0 else 0

    return {
        "agent_id": agent_id,
        "name": agent.name,
        "role": agent.role.value,
        "tasks_completed": agent.tasks_completed,
        "tasks_failed": agent.tasks_failed,
        "total_tasks": total_tasks,
        "success_rate": round(success_rate, 2),
        "average_duration_seconds": agent.average_task_duration_seconds,
        "total_cost": agent.total_cost,
        "total_tokens_used": agent.total_tokens_used,
    }


# Agent Execution Endpoints

class AgentExecutionRequest(BaseModel):
    """Request model for executing an agent"""
    input_data: Dict[str, Any]
    task_id: Optional[int] = None
    workflow_id: Optional[str] = None
    agent_type: Optional[str] = None


class AgentExecutionResponse(BaseModel):
    """Response model for agent execution"""
    id: int
    agent_id: int
    task_id: Optional[int]
    workflow_id: Optional[str]
    status: str
    output_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    execution_time_seconds: Optional[float]
    tokens_used: Optional[int]
    cost: Optional[float]
    created_at: str
    completed_at: Optional[str]

    class Config:
        from_attributes = True


@router.post("/{agent_id}/execute")
async def execute_agent(
    agent_id: int,
    execution_request: AgentExecutionRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Execute an agent with given input

    Args:
        agent_id: Agent ID
        execution_request: Execution request data
        db: Database session

    Returns:
        dict: Execution result
    """
    try:
        execution = await AgentService.execute_agent(
            session=db,
            agent_id=agent_id,
            input_data=execution_request.input_data,
            task_id=execution_request.task_id,
            workflow_id=execution_request.workflow_id,
            agent_type=execution_request.agent_type
        )

        db.commit()

        return {
            "id": execution.id,
            "agent_id": execution.agent_id,
            "task_id": execution.task_id,
            "workflow_id": execution.workflow_id,
            "status": execution.status.value,
            "output_data": execution.output_data,
            "error_message": execution.error_message,
            "execution_time_seconds": execution.execution_time_seconds,
            "tokens_used": execution.tokens_used,
            "cost": execution.cost,
            "created_at": execution.created_at.isoformat(),
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


@router.get("/{agent_id}/executions")
async def get_agent_executions(
    agent_id: int,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    """
    Get execution history for an agent

    Args:
        agent_id: Agent ID
        status: Filter by status
        limit: Result limit
        offset: Result offset
        db: Database session

    Returns:
        list: Agent executions
    """
    execution_status = ExecutionStatus(status) if status else None

    executions = AgentService.get_agent_executions(
        session=db,
        agent_id=agent_id,
        status=execution_status,
        limit=limit,
        offset=offset
    )

    return [
        {
            "id": exec.id,
            "task_id": exec.task_id,
            "workflow_id": exec.workflow_id,
            "status": exec.status.value,
            "input_data": exec.input_data,
            "output_data": exec.output_data,
            "error_message": exec.error_message,
            "execution_time_seconds": exec.execution_time_seconds,
            "tokens_used": exec.tokens_used,
            "cost": exec.cost,
            "created_at": exec.created_at.isoformat(),
            "completed_at": exec.completed_at.isoformat() if exec.completed_at else None
        }
        for exec in executions
    ]


@router.get("/{agent_id}/statistics")
async def get_agent_statistics(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get comprehensive agent statistics

    Args:
        agent_id: Agent ID
        db: Database session

    Returns:
        dict: Agent statistics including execution metrics
    """
    try:
        stats = AgentService.get_agent_statistics(session=db, agent_id=agent_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/executions/{execution_id}")
async def get_execution_details(
    execution_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get execution details by ID

    Args:
        execution_id: Execution ID
        db: Database session

    Returns:
        dict: Execution details
    """
    execution = AgentService.get_execution_by_id(session=db, execution_id=execution_id)

    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    return execution.to_dict()
