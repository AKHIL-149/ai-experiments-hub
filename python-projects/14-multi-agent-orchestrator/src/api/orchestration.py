"""
Agent Orchestration API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.orchestration_service import AgentOrchestrationService, OrchestrationPattern
from src.models.agent import AgentRole, AgentStatus
from src.models.agent_message import MessagePriority
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class AgentDiscoveryRequest(BaseModel):
    """Request model for agent discovery"""
    role: Optional[str] = None
    capabilities: Optional[List[str]] = None
    status: str = "idle"
    limit: int = 10


class AgentDiscoveryResponse(BaseModel):
    """Response model for agent discovery"""
    id: int
    name: str
    role: str
    status: str
    capabilities: List[str]
    successful_tasks: int
    average_response_time: Optional[float]


class TaskAssignmentRequest(BaseModel):
    """Request model for task assignment"""
    task_id: int
    agent_id: int
    priority: str = "normal"
    context: Optional[Dict[str, Any]] = None


class OrchestrationRequest(BaseModel):
    """Request model for orchestration"""
    task_ids: List[int]
    pattern: str  # sequential, parallel, hierarchical
    workflow_id: Optional[str] = None
    auto_assign: bool = True
    supervisor_agent_id: Optional[int] = None  # For hierarchical


class ResultAggregationRequest(BaseModel):
    """Request model for result aggregation"""
    execution_ids: List[int]
    strategy: str = "collect"  # collect, merge, vote, average


# Endpoints

@router.post("/discover")
async def discover_agents(
    request: AgentDiscoveryRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Discover available agents based on criteria"""
    try:
        # Convert string to enum
        role = AgentRole(request.role) if request.role else None
        agent_status = AgentStatus(request.status) if request.status else AgentStatus.IDLE

        agents = AgentOrchestrationService.discover_agents(
            session=db,
            role=role,
            capabilities=request.capabilities,
            status=agent_status,
            limit=request.limit
        )

        return {
            "agents": [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "role": agent.role.value,
                    "status": agent.status.value,
                    "capabilities": agent.capabilities or [],
                    "successful_tasks": agent.successful_tasks,
                    "average_response_time": agent.average_response_time
                }
                for agent in agents
            ],
            "count": len(agents)
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to discover agents: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/assign")
async def assign_task(
    request: TaskAssignmentRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Assign a task to a specific agent"""
    try:
        # Convert string to enum
        priority = MessagePriority(request.priority)

        execution, message = AgentOrchestrationService.assign_task_to_agent(
            session=db,
            task_id=request.task_id,
            agent_id=request.agent_id,
            priority=priority,
            context=request.context
        )

        db.commit()

        return {
            "execution": {
                "id": execution.id,
                "agent_id": execution.agent_id,
                "task_id": execution.task_id,
                "status": execution.status.value,
                "started_at": execution.started_at.isoformat() if execution.started_at else None
            },
            "message": {
                "id": message.id,
                "message_type": message.message_type.value,
                "priority": message.priority.value,
                "content": message.content
            }
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to assign task: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/orchestrate")
async def orchestrate_tasks(
    request: OrchestrationRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Orchestrate multiple tasks using specified pattern"""
    try:
        if request.pattern == OrchestrationPattern.SEQUENTIAL:
            executions = AgentOrchestrationService.orchestrate_sequential(
                session=db,
                task_ids=request.task_ids,
                workflow_id=request.workflow_id,
                auto_assign=request.auto_assign
            )

            db.commit()

            return {
                "pattern": OrchestrationPattern.SEQUENTIAL,
                "task_count": len(request.task_ids),
                "execution_count": len(executions),
                "executions": [
                    {
                        "id": e.id,
                        "agent_id": e.agent_id,
                        "task_id": e.task_id,
                        "status": e.status.value
                    }
                    for e in executions
                ]
            }

        elif request.pattern == OrchestrationPattern.PARALLEL:
            executions = AgentOrchestrationService.orchestrate_parallel(
                session=db,
                task_ids=request.task_ids,
                workflow_id=request.workflow_id,
                auto_assign=request.auto_assign
            )

            db.commit()

            return {
                "pattern": OrchestrationPattern.PARALLEL,
                "task_count": len(request.task_ids),
                "execution_count": len(executions),
                "executions": [
                    {
                        "id": e.id,
                        "agent_id": e.agent_id,
                        "task_id": e.task_id,
                        "status": e.status.value
                    }
                    for e in executions
                ]
            }

        elif request.pattern == OrchestrationPattern.HIERARCHICAL:
            if not request.supervisor_agent_id:
                raise ValueError("supervisor_agent_id is required for hierarchical pattern")

            result = AgentOrchestrationService.orchestrate_hierarchical(
                session=db,
                supervisor_agent_id=request.supervisor_agent_id,
                worker_task_ids=request.task_ids,
                workflow_id=request.workflow_id
            )

            db.commit()

            return {
                "pattern": OrchestrationPattern.HIERARCHICAL,
                "supervisor": {
                    "id": result["supervisor"].id,
                    "name": result["supervisor"].name,
                    "role": result["supervisor"].role.value
                },
                "worker_count": len(result["workers"]),
                "workers": [
                    {
                        "id": w.id,
                        "name": w.name,
                        "role": w.role.value
                    }
                    for w in result["workers"]
                ],
                "execution_count": len(result["executions"]),
                "executions": [
                    {
                        "id": e.id,
                        "agent_id": e.agent_id,
                        "task_id": e.task_id,
                        "status": e.status.value
                    }
                    for e in result["executions"]
                ]
            }

        else:
            raise ValueError(f"Unknown orchestration pattern: {request.pattern}")

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to orchestrate tasks: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/aggregate")
async def aggregate_results(
    request: ResultAggregationRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Aggregate results from multiple agent executions"""
    try:
        result = AgentOrchestrationService.aggregate_results(
            session=db,
            execution_ids=request.execution_ids,
            aggregation_strategy=request.strategy
        )

        return result

    except Exception as e:
        logger.error(f"Failed to aggregate results: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/status/{workflow_id}")
async def get_orchestration_status(
    workflow_id: str,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get orchestration status for a workflow"""
    try:
        status_data = AgentOrchestrationService.get_orchestration_status(
            session=db,
            workflow_id=workflow_id
        )

        return status_data

    except Exception as e:
        logger.error(f"Failed to get orchestration status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/patterns")
async def list_orchestration_patterns() -> Dict[str, Any]:
    """List available orchestration patterns"""
    return {
        "patterns": [
            {
                "name": OrchestrationPattern.SEQUENTIAL,
                "description": "Agents execute one after another in sequence"
            },
            {
                "name": OrchestrationPattern.PARALLEL,
                "description": "Agents execute simultaneously in parallel"
            },
            {
                "name": OrchestrationPattern.HIERARCHICAL,
                "description": "Supervisor agent delegates tasks to worker agents"
            },
            {
                "name": OrchestrationPattern.PIPELINE,
                "description": "Output of one agent feeds into the next agent"
            },
            {
                "name": OrchestrationPattern.BROADCAST,
                "description": "Same task distributed to all agents"
            }
        ]
    }
