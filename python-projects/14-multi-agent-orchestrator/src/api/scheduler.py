"""
Agent Scheduler API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_scheduler import AgentScheduler, SchedulingStrategy
from src.models.agent import AgentRole
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class ScheduleTaskRequest(BaseModel):
    """Request model for scheduling a single task"""
    task_id: int = Field(..., description="Task ID to schedule")
    strategy: str = Field(
        default=SchedulingStrategy.LEAST_LOADED,
        description="Scheduling strategy to use"
    )
    required_capabilities: Optional[List[str]] = Field(
        default=None,
        description="Required agent capabilities"
    )
    preferred_role: Optional[str] = Field(
        default=None,
        description="Preferred agent role"
    )


class BatchScheduleRequest(BaseModel):
    """Request model for batch scheduling"""
    task_ids: List[int] = Field(..., description="List of task IDs to schedule")
    strategy: str = Field(
        default=SchedulingStrategy.LEAST_LOADED,
        description="Scheduling strategy to use"
    )
    balance_load: bool = Field(
        default=True,
        description="Whether to balance load across agents"
    )


class RebalanceRequest(BaseModel):
    """Request model for load rebalancing"""
    threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Rebalance if load difference exceeds this factor"
    )


# Endpoints

@router.post("/schedule")
async def schedule_task(
    request: ScheduleTaskRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Schedule a single task to an appropriate agent.

    Uses the specified scheduling strategy to select the best agent
    for the given task based on availability, capabilities, and load.
    """
    try:
        # Validate strategy
        valid_strategies = [
            SchedulingStrategy.ROUND_ROBIN,
            SchedulingStrategy.LEAST_LOADED,
            SchedulingStrategy.CAPABILITY_BASED,
            SchedulingStrategy.PERFORMANCE_BASED,
            SchedulingStrategy.RANDOM,
            SchedulingStrategy.PRIORITY_QUEUE
        ]

        if request.strategy not in valid_strategies:
            raise ValueError(
                f"Invalid strategy '{request.strategy}'. "
                f"Valid strategies: {', '.join(valid_strategies)}"
            )

        # Convert role string to enum if provided
        preferred_role = None
        if request.preferred_role:
            try:
                preferred_role = AgentRole(request.preferred_role)
            except ValueError:
                raise ValueError(f"Invalid role: {request.preferred_role}")

        # Schedule task
        agent = AgentScheduler.schedule_task(
            session=db,
            task_id=request.task_id,
            strategy=request.strategy,
            required_capabilities=request.required_capabilities,
            preferred_role=preferred_role
        )

        if not agent:
            return {
                "success": False,
                "task_id": request.task_id,
                "agent_id": None,
                "message": "No suitable agent found for this task",
                "strategy": request.strategy
            }

        db.commit()

        return {
            "success": True,
            "task_id": request.task_id,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "agent_role": agent.role.value,
            "agent_status": agent.status.value,
            "strategy": request.strategy,
            "message": f"Task {request.task_id} scheduled to agent {agent.name}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to schedule task: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/batch-schedule")
async def batch_schedule(
    request: BatchScheduleRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Schedule multiple tasks to agents in batch.

    When balance_load is True, the scheduler will distribute tasks
    evenly across available agents to maintain balanced workload.
    """
    try:
        if not request.task_ids:
            raise ValueError("Task IDs list cannot be empty")

        if len(request.task_ids) > 1000:
            raise ValueError("Maximum 1000 tasks allowed per batch")

        # Validate strategy
        valid_strategies = [
            SchedulingStrategy.ROUND_ROBIN,
            SchedulingStrategy.LEAST_LOADED,
            SchedulingStrategy.CAPABILITY_BASED,
            SchedulingStrategy.PERFORMANCE_BASED,
            SchedulingStrategy.RANDOM,
            SchedulingStrategy.PRIORITY_QUEUE
        ]

        if request.strategy not in valid_strategies:
            raise ValueError(
                f"Invalid strategy '{request.strategy}'. "
                f"Valid strategies: {', '.join(valid_strategies)}"
            )

        # Batch schedule tasks
        assignments = AgentScheduler.batch_schedule(
            session=db,
            task_ids=request.task_ids,
            strategy=request.strategy,
            balance_load=request.balance_load
        )

        db.commit()

        # Calculate statistics
        assigned = sum(1 for agent_id in assignments.values() if agent_id is not None)
        unassigned = sum(1 for agent_id in assignments.values() if agent_id is None)

        # Group by agent
        agent_task_counts = {}
        for task_id, agent_id in assignments.items():
            if agent_id:
                agent_task_counts[agent_id] = agent_task_counts.get(agent_id, 0) + 1

        return {
            "success": True,
            "total_tasks": len(request.task_ids),
            "assigned": assigned,
            "unassigned": unassigned,
            "assignment_rate": assigned / len(request.task_ids) if request.task_ids else 0,
            "strategy": request.strategy,
            "balance_load": request.balance_load,
            "assignments": assignments,
            "agent_task_counts": agent_task_counts,
            "message": f"Scheduled {assigned}/{len(request.task_ids)} tasks successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to batch schedule tasks: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/load-distribution")
async def get_load_distribution(
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get current load distribution across all agents.

    Returns detailed information about each agent's current load,
    queued tasks, and a balance score indicating how well the
    load is distributed (1.0 = perfectly balanced).
    """
    try:
        distribution = AgentScheduler.get_load_distribution(session=db)

        return {
            "success": True,
            "distribution": distribution,
            "message": f"Load distribution for {distribution['total_agents']} agents"
        }

    except Exception as e:
        logger.error(f"Failed to get load distribution: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/rebalance")
async def rebalance_load(
    request: RebalanceRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Rebalance load by moving queued tasks from overloaded to underloaded agents.

    The threshold parameter determines when rebalancing is triggered.
    A threshold of 0.3 means rebalancing occurs when an agent's load
    differs from the average by more than 30%.
    """
    try:
        result = AgentScheduler.rebalance_load(
            session=db,
            threshold=request.threshold
        )

        db.commit()

        return {
            "success": result["rebalanced"],
            "result": result,
            "message": (
                f"Rebalanced {result.get('tasks_moved', 0)} tasks"
                if result["rebalanced"]
                else result.get("reason", "No rebalancing needed")
            )
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to rebalance load: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/strategies")
async def list_strategies() -> Dict[str, Any]:
    """
    List all available scheduling strategies.

    Each strategy has different characteristics and use cases:
    - ROUND_ROBIN: Fair distribution in rotation
    - LEAST_LOADED: Assigns to agent with lowest current load
    - CAPABILITY_BASED: Matches task requirements to agent capabilities
    - PERFORMANCE_BASED: Selects based on success rate and response time
    - RANDOM: Random assignment for testing/experimentation
    - PRIORITY_QUEUE: Respects task priority ordering
    """
    strategies = [
        {
            "name": SchedulingStrategy.ROUND_ROBIN,
            "description": "Distributes tasks evenly in rotation across all available agents",
            "use_case": "Simple fair distribution when all agents are equivalent",
            "pros": ["Fair distribution", "Simple", "Predictable"],
            "cons": ["Ignores agent load", "Ignores agent capabilities"]
        },
        {
            "name": SchedulingStrategy.LEAST_LOADED,
            "description": "Assigns tasks to the agent with the lowest current load",
            "use_case": "Load balancing when agents have similar capabilities",
            "pros": ["Balances load", "Maximizes throughput", "Reduces wait times"],
            "cons": ["May overload slow agents", "Doesn't consider capabilities"]
        },
        {
            "name": SchedulingStrategy.CAPABILITY_BASED,
            "description": "Matches task requirements to agent capabilities",
            "use_case": "When tasks require specific skills or capabilities",
            "pros": ["Best capability match", "Task-agent alignment"],
            "cons": ["May create imbalanced load", "Requires capability metadata"]
        },
        {
            "name": SchedulingStrategy.PERFORMANCE_BASED,
            "description": "Selects agents based on historical success rate and response time",
            "use_case": "Optimize for quality and speed",
            "pros": ["High success rate", "Fast execution", "Quality-focused"],
            "cons": ["May underutilize new agents", "Requires historical data"]
        },
        {
            "name": SchedulingStrategy.RANDOM,
            "description": "Randomly assigns tasks to available agents",
            "use_case": "Testing, experimentation, or when no optimization needed",
            "pros": ["Unpredictable (good for testing)", "No overhead"],
            "cons": ["No optimization", "Unpredictable results"]
        },
        {
            "name": SchedulingStrategy.PRIORITY_QUEUE,
            "description": "Respects task priority ordering",
            "use_case": "When task priority is critical",
            "pros": ["Honors priorities", "Important tasks first"],
            "cons": ["May starve low-priority tasks", "Requires priority metadata"]
        }
    ]

    return {
        "success": True,
        "total_strategies": len(strategies),
        "default_strategy": SchedulingStrategy.LEAST_LOADED,
        "strategies": strategies,
        "message": "List of all available scheduling strategies"
    }


@router.get("/agent-load/{agent_id}")
async def get_agent_load(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get current load information for a specific agent.

    Returns the number of running, queued, and assigned tasks
    for the specified agent.
    """
    try:
        from src.models.agent import Agent

        # Check if agent exists
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found"
            )

        # Get load metrics
        current_load = AgentScheduler._get_agent_load(db, agent_id)
        queued_count = AgentScheduler._get_queued_count(db, agent_id)

        return {
            "success": True,
            "agent_id": agent_id,
            "agent_name": agent.name,
            "agent_role": agent.role.value,
            "agent_status": agent.status.value,
            "current_load": current_load,
            "queued_tasks": queued_count,
            "running_tasks": current_load - queued_count,
            "message": f"Load information for agent {agent.name}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent load: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/scheduling-stats")
async def get_scheduling_stats(
    time_range_hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get scheduling statistics for the specified time range.

    Provides insights into scheduling patterns, agent utilization,
    and load distribution trends.
    """
    try:
        from datetime import datetime, timedelta
        from src.models.agent_execution import AgentExecution, ExecutionStatus
        from src.models.agent import Agent

        time_threshold = datetime.utcnow() - timedelta(hours=time_range_hours)

        # Get all executions in time range
        executions = db.query(AgentExecution).filter(
            AgentExecution.created_at >= time_threshold
        ).all()

        # Calculate statistics
        total_executions = len(executions)

        status_counts = {}
        for execution in executions:
            status = execution.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        # Agent distribution
        agent_execution_counts = {}
        for execution in executions:
            agent_id = execution.agent_id
            agent_execution_counts[agent_id] = agent_execution_counts.get(agent_id, 0) + 1

        # Get current distribution
        distribution = AgentScheduler.get_load_distribution(session=db)

        # Calculate utilization
        total_agents = db.query(Agent).count()
        active_agents = len(set(e.agent_id for e in executions))

        return {
            "success": True,
            "time_range_hours": time_range_hours,
            "total_executions": total_executions,
            "status_distribution": status_counts,
            "agent_execution_counts": agent_execution_counts,
            "total_agents": total_agents,
            "active_agents": active_agents,
            "agent_utilization_rate": active_agents / total_agents if total_agents > 0 else 0,
            "current_load_balance_score": distribution["balance_score"],
            "average_executions_per_agent": total_executions / active_agents if active_agents > 0 else 0,
            "message": f"Scheduling statistics for last {time_range_hours} hours"
        }

    except Exception as e:
        logger.error(f"Failed to get scheduling stats: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
