"""
Agent management API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from src.core.database import get_db_session
from src.models import Agent, AgentRole, AgentStatus
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
