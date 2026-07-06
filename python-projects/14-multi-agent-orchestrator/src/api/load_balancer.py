"""
Agent Load Balancing API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_load_balancer import AgentLoadBalancer, LoadBalancingStrategy
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class SelectAgentRequest(BaseModel):
    """Request model for agent selection"""
    task_id: int = Field(..., description="Task ID")
    strategy: str = Field(
        default=LoadBalancingStrategy.LEAST_LOADED,
        description="Load balancing strategy"
    )
    required_role: Optional[str] = Field(default=None, description="Required agent role")
    required_capabilities: Optional[List[str]] = Field(default=None, description="Required capabilities")
    required_resources: Optional[Dict[str, float]] = Field(default=None, description="Required resources")


class RebalanceTasksRequest(BaseModel):
    """Request model for task rebalancing"""
    strategy: str = Field(
        default=LoadBalancingStrategy.LEAST_LOADED,
        description="Strategy for rebalancing"
    )
    dry_run: bool = Field(
        default=False,
        description="If true, only simulate rebalancing"
    )


# Endpoints

@router.post("/select-agent")
async def select_agent(
    request: SelectAgentRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Select the best agent for a task using load balancing.

    Uses the specified strategy to intelligently select an agent:
    - **round_robin**: Distribute evenly in sequence
    - **least_loaded**: Pick agent with lowest current load
    - **weighted**: Weighted random based on capacity
    - **random**: Random selection
    - **capability_based**: Best capability match
    - **performance_based**: Based on historical performance
    """
    try:
        selected = AgentLoadBalancer.select_agent(
            session=db,
            task_id=request.task_id,
            strategy=request.strategy,
            required_role=request.required_role,
            required_capabilities=request.required_capabilities,
            required_resources=request.required_resources
        )

        return {
            "success": True,
            "selected_agent": selected,
            "message": f"Selected agent {selected['agent_id']} using {request.strategy} strategy"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to select agent: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/distribution")
async def get_load_distribution(
    agent_ids: Optional[List[int]] = Query(None, description="Optional agent IDs to analyze"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get load distribution across agents.

    Shows how tasks are distributed across the agent cluster:
    - Running and queued tasks per agent
    - Resource utilization per agent
    - Overall balance score (0-100, higher is better)
    - Cluster-wide statistics
    """
    try:
        distribution = AgentLoadBalancer.get_load_distribution(
            session=db,
            agent_ids=agent_ids
        )

        return {
            "success": True,
            "distribution": distribution,
            "message": f"Load distribution across {distribution['total_agents']} agents"
        }

    except Exception as e:
        logger.error(f"Failed to get load distribution: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/rebalance")
async def rebalance_tasks(
    request: RebalanceTasksRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Rebalance tasks across agents.

    Moves queued tasks from overloaded agents to underloaded agents
    to achieve better load distribution.

    Set dry_run=true to preview changes without applying them.
    """
    try:
        result = AgentLoadBalancer.rebalance_tasks(
            session=db,
            strategy=request.strategy,
            dry_run=request.dry_run
        )

        if not request.dry_run and result["needed"]:
            db.commit()

        return {
            "success": True,
            "rebalance": result,
            "message": result["message"]
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to rebalance tasks: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/capacity/{agent_id}")
async def get_agent_capacity(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get agent capacity information.

    Returns detailed capacity metrics:
    - Current task load (running + queued)
    - Resource utilization
    - Overall capacity used percentage
    - Whether agent can accept more tasks
    """
    try:
        capacity = AgentLoadBalancer.get_agent_capacity(
            session=db,
            agent_id=agent_id
        )

        return {
            "success": True,
            "capacity": capacity,
            "message": f"Capacity for agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get agent capacity: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/strategies")
async def list_strategies() -> Dict[str, Any]:
    """
    List all load balancing strategies.

    Returns available strategies with descriptions and use cases.
    """
    strategies = [
        {
            "strategy": LoadBalancingStrategy.ROUND_ROBIN,
            "description": "Distribute tasks evenly in sequence",
            "use_case": "Equal distribution when agents have similar capacity",
            "pros": ["Simple", "Predictable", "Fair distribution"],
            "cons": ["Ignores current load", "Ignores agent capability differences"]
        },
        {
            "strategy": LoadBalancingStrategy.LEAST_LOADED,
            "description": "Select agent with lowest current load",
            "use_case": "Dynamic environments with varying task durations",
            "pros": ["Responsive to current state", "Good for mixed workloads", "Default strategy"],
            "cons": ["Slight overhead to calculate load"]
        },
        {
            "strategy": LoadBalancingStrategy.WEIGHTED,
            "description": "Weighted random based on available capacity",
            "use_case": "Heterogeneous agents with different capacities",
            "pros": ["Accounts for agent capacity", "Probabilistic fairness"],
            "cons": ["More complex", "May not be perfectly balanced"]
        },
        {
            "strategy": LoadBalancingStrategy.RANDOM,
            "description": "Random agent selection",
            "use_case": "Testing or when all agents are equivalent",
            "pros": ["Simplest", "No state needed"],
            "cons": ["May create uneven distribution", "Ignores all factors"]
        },
        {
            "strategy": LoadBalancingStrategy.CAPABILITY_BASED,
            "description": "Select based on capability match",
            "use_case": "Tasks requiring specific agent capabilities",
            "pros": ["Best functional match", "Optimizes capability usage"],
            "cons": ["May ignore load", "Requires capability metadata"]
        },
        {
            "strategy": LoadBalancingStrategy.PERFORMANCE_BASED,
            "description": "Select based on historical performance",
            "use_case": "When historical performance predicts future success",
            "pros": ["Learns from history", "Optimizes for success rate and speed"],
            "cons": ["Requires execution history", "May not adapt to changes quickly"]
        }
    ]

    return {
        "success": True,
        "total_strategies": len(strategies),
        "strategies": strategies,
        "default_strategy": LoadBalancingStrategy.LEAST_LOADED,
        "message": "List of all load balancing strategies"
    }


@router.get("/health")
async def check_load_balancer_health(
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Check load balancer health.

    Returns overall cluster health metrics:
    - Balance score
    - Overloaded agents count
    - Available capacity
    - Health status
    """
    try:
        distribution = AgentLoadBalancer.get_load_distribution(session=db)

        # Count overloaded agents
        overloaded_count = sum(1 for d in distribution["distribution"] if d["is_overloaded"])

        # Calculate health status
        balance_score = distribution["balance_score"]
        if balance_score >= 80 and overloaded_count == 0:
            health_status = "healthy"
        elif balance_score >= 60 and overloaded_count <= 1:
            health_status = "degraded"
        else:
            health_status = "unhealthy"

        return {
            "success": True,
            "health": {
                "status": health_status,
                "balance_score": balance_score,
                "total_agents": distribution["total_agents"],
                "overloaded_agents": overloaded_count,
                "average_load": distribution["average_load"],
                "total_running_tasks": distribution["total_running_tasks"],
                "total_queued_tasks": distribution["total_queued_tasks"]
            },
            "message": f"Load balancer status: {health_status}"
        }

    except Exception as e:
        logger.error(f"Failed to check load balancer health: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/recommendations")
async def get_recommendations(
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get load balancing recommendations.

    Analyzes current state and provides actionable recommendations
    for improving load distribution and cluster efficiency.
    """
    try:
        distribution = AgentLoadBalancer.get_load_distribution(session=db)

        recommendations = []

        # Check balance score
        if distribution["balance_score"] < 70:
            recommendations.append({
                "priority": "high",
                "type": "rebalance",
                "message": "Load distribution is uneven. Consider rebalancing tasks.",
                "action": "POST /api/load-balancer/rebalance"
            })

        # Check for overloaded agents
        overloaded = [d for d in distribution["distribution"] if d["is_overloaded"]]
        if overloaded:
            recommendations.append({
                "priority": "high",
                "type": "capacity",
                "message": f"{len(overloaded)} agents are overloaded. Increase capacity or redistribute load.",
                "affected_agents": [d["agent_id"] for d in overloaded]
            })

        # Check for idle agents
        idle = [d for d in distribution["distribution"] if d["running_tasks"] == 0 and d["queued_tasks"] == 0]
        if idle and distribution["total_queued_tasks"] > 0:
            recommendations.append({
                "priority": "medium",
                "type": "utilization",
                "message": f"{len(idle)} agents are idle while {distribution['total_queued_tasks']} tasks are queued.",
                "idle_agents": [d["agent_id"] for d in idle]
            })

        # Check average load
        if distribution["average_load"] > 10:
            recommendations.append({
                "priority": "medium",
                "type": "scaling",
                "message": "High average load detected. Consider adding more agents.",
                "current_average_load": distribution["average_load"]
            })

        if not recommendations:
            recommendations.append({
                "priority": "info",
                "type": "status",
                "message": "Load balancer is operating optimally. No actions needed."
            })

        return {
            "success": True,
            "total_recommendations": len(recommendations),
            "recommendations": recommendations,
            "balance_score": distribution["balance_score"],
            "message": f"Generated {len(recommendations)} recommendations"
        }

    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
