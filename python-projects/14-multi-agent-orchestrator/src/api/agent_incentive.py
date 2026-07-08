"""
Agent Incentive API

REST API endpoints for agent incentives, rewards, and economic system.
"""

from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_incentive import (
    AgentIncentive,
    ContributionType,
    RewardType,
    RewardStatus
)


router = APIRouter()


# Request/Response Models
class InitializeAgentRequest(BaseModel):
    agent_id: int = Field(..., description="Agent ID")
    initial_balance: float = Field(0.0, description="Initial balance")


class RecordContributionRequest(BaseModel):
    contribution_type: str = Field(..., description="Contribution type")
    value: float = Field(..., description="Contribution value/weight")
    description: str = Field("", description="Contribution description")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class CalculateTaskRewardRequest(BaseModel):
    task_id: int = Field(..., description="Task ID")
    completion_time_hours: float = Field(..., description="Time taken to complete")
    quality_score: float = Field(1.0, description="Quality rating (0-1)")
    difficulty_multiplier: float = Field(1.0, description="Task difficulty multiplier")


class AwardRewardRequest(BaseModel):
    reward_type: str = Field(..., description="Type of reward")
    amount: float = Field(..., description="Reward amount")
    reason: str = Field("", description="Reason for reward")
    metadata: Optional[dict] = Field(None, description="Additional metadata")
    auto_approve: bool = Field(True, description="Auto-approve and distribute")


class TransferBalanceRequest(BaseModel):
    to_agent_id: int = Field(..., description="Receiver agent ID")
    amount: float = Field(..., description="Transfer amount")
    reason: str = Field("", description="Transfer reason")


class CreateRewardPoolRequest(BaseModel):
    pool_name: str = Field(..., description="Pool name")
    total_amount: float = Field(..., description="Total pool amount")
    distribution_criteria: dict = Field(..., description="Distribution criteria")
    deadline_hours: Optional[int] = Field(None, description="Deadline in hours")


class DistributeFromPoolRequest(BaseModel):
    agent_rewards: Dict[int, float] = Field(..., description="Mapping of agent_id to amount")


@router.post("/agents/initialize")
def initialize_agent(
    request: InitializeAgentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Initialize incentive tracking for an agent.

    Creates a balance and tracking for contributions and rewards.
    All agents must be initialized before receiving rewards.
    """
    try:
        agent_data = AgentIncentive.initialize_agent(
            session=session,
            agent_id=request.agent_id,
            initial_balance=request.initial_balance
        )

        return {
            "success": True,
            "agent": agent_data,
            "message": f"Agent initialized with balance {request.initial_balance}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/contributions")
def record_contribution(
    agent_id: int,
    request: RecordContributionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record a contribution from an agent.

    Tracks agent contributions for transparency and future reward calculations.
    Contributions can be tasks, collaborations, innovations, etc.
    """
    try:
        contribution = AgentIncentive.record_contribution(
            session=session,
            agent_id=agent_id,
            contribution_type=request.contribution_type,
            value=request.value,
            description=request.description,
            metadata=request.metadata
        )

        return {
            "success": True,
            "contribution": contribution,
            "message": f"Contribution recorded: {request.contribution_type}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/calculate-task-reward")
def calculate_task_reward(
    agent_id: int,
    request: CalculateTaskRewardRequest,
    session: Session = Depends(get_db_session)
):
    """
    Calculate reward for task completion.

    Computes base reward plus quality and speed bonuses.
    Does not automatically award - use award-reward endpoint to distribute.
    """
    try:
        calculation = AgentIncentive.calculate_task_reward(
            session=session,
            agent_id=agent_id,
            task_id=request.task_id,
            completion_time_hours=request.completion_time_hours,
            quality_score=request.quality_score,
            difficulty_multiplier=request.difficulty_multiplier
        )

        return {
            "success": True,
            "calculation": calculation,
            "message": f"Calculated reward: {calculation['total_reward']:.2f}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/rewards")
def award_reward(
    agent_id: int,
    request: AwardRewardRequest,
    session: Session = Depends(get_db_session)
):
    """
    Award a reward to an agent.

    Creates a reward and optionally auto-approves and distributes it
    to the agent's balance immediately.
    """
    try:
        reward = AgentIncentive.award_reward(
            session=session,
            agent_id=agent_id,
            reward_type=request.reward_type,
            amount=request.amount,
            reason=request.reason,
            metadata=request.metadata,
            auto_approve=request.auto_approve
        )

        return {
            "success": True,
            "reward": reward,
            "message": f"Reward of {request.amount:.2f} awarded"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/transfer")
def transfer_balance(
    agent_id: int,
    request: TransferBalanceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Transfer balance between agents.

    Allows agents to share rewards or pay each other for services.
    Sender must have sufficient balance.
    """
    try:
        transfer = AgentIncentive.transfer_balance(
            session=session,
            from_agent_id=agent_id,
            to_agent_id=request.to_agent_id,
            amount=request.amount,
            reason=request.reason
        )

        return {
            "success": True,
            "transfer": transfer,
            "message": f"Transferred {request.amount:.2f} to agent {request.to_agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pools")
def create_reward_pool(
    request: CreateRewardPoolRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a reward pool for distribution.

    Pools allow bulk distribution of rewards based on criteria
    like performance, milestones, or competition results.
    """
    try:
        from datetime import datetime, timedelta

        deadline = None
        if request.deadline_hours:
            deadline = datetime.utcnow() + timedelta(hours=request.deadline_hours)

        pool = AgentIncentive.create_reward_pool(
            session=session,
            pool_name=request.pool_name,
            total_amount=request.total_amount,
            distribution_criteria=request.distribution_criteria,
            deadline=deadline
        )

        return {
            "success": True,
            "pool": pool,
            "message": f"Pool created with {request.total_amount:.2f}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pools/{pool_id}/distribute")
def distribute_from_pool(
    pool_id: str,
    request: DistributeFromPoolRequest,
    session: Session = Depends(get_db_session)
):
    """
    Distribute rewards from a pool to multiple agents.

    Divides the pool among specified agents and updates their balances.
    Total distribution cannot exceed remaining pool amount.
    """
    try:
        result = AgentIncentive.distribute_from_pool(
            session=session,
            pool_id=pool_id,
            agent_rewards=request.agent_rewards
        )

        return {
            "success": True,
            **result,
            "message": f"Distributed to {result['agents_rewarded']} agents"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/balance")
def get_agent_balance(
    agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get agent's current balance and summary.

    Returns balance, total rewards received, pending rewards,
    and contribution statistics.
    """
    try:
        balance = AgentIncentive.get_agent_balance(
            session=session,
            agent_id=agent_id
        )

        return {
            "success": True,
            **balance
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/history")
def get_agent_history(
    agent_id: int,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get agent's contribution and reward history.

    Returns recent contributions, rewards, and transactions
    ordered by timestamp.
    """
    try:
        history = AgentIncentive.get_agent_history(
            session=session,
            agent_id=agent_id,
            limit=limit
        )

        return {
            "success": True,
            **history
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard")
def get_leaderboard(
    metric: str = "balance",
    limit: int = 10,
    session: Session = Depends(get_db_session)
):
    """
    Get leaderboard of top agents.

    Rankings based on balance, contributions, or total rewards.
    Shows top performers in the system.
    """
    try:
        leaderboard = AgentIncentive.get_leaderboard(
            session=session,
            metric=metric,
            limit=limit
        )

        return {
            "success": True,
            **leaderboard
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get incentive system statistics.

    Returns aggregate data including total balances, rewards distributed,
    contributions, and active pools.
    """
    try:
        stats = AgentIncentive.get_incentive_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contribution-types")
def list_contribution_types():
    """
    List all contribution types.

    Returns all types of contributions that can be recorded.
    """
    return {
        "success": True,
        "contribution_types": [
            {"type": ContributionType.TASK_COMPLETION, "description": "Completed a task"},
            {"type": ContributionType.COLLABORATION, "description": "Collaborated with other agents"},
            {"type": ContributionType.ENDORSEMENT_RECEIVED, "description": "Received endorsement from peer"},
            {"type": ContributionType.HELP_PROVIDED, "description": "Helped another agent"},
            {"type": ContributionType.INNOVATION, "description": "Introduced innovation or improvement"},
            {"type": ContributionType.QUALITY_WORK, "description": "High-quality work delivered"}
        ]
    }


@router.get("/reward-types")
def list_reward_types():
    """
    List all reward types.

    Returns all types of rewards that can be awarded.
    """
    return {
        "success": True,
        "reward_types": [
            {"type": RewardType.BASE_REWARD, "description": "Standard task completion reward"},
            {"type": RewardType.PERFORMANCE_BONUS, "description": "Bonus for exceptional performance"},
            {"type": RewardType.QUALITY_BONUS, "description": "Bonus for high-quality work"},
            {"type": RewardType.COLLABORATION_BONUS, "description": "Bonus for collaborative work"},
            {"type": RewardType.STREAK_BONUS, "description": "Bonus for consistent performance"},
            {"type": RewardType.MILESTONE_REWARD, "description": "Reward for reaching milestone"}
        ]
    }


@router.get("/reward-statuses")
def list_reward_statuses():
    """
    List all reward statuses.

    Returns all possible statuses a reward can have.
    """
    return {
        "success": True,
        "reward_statuses": [
            {"status": RewardStatus.PENDING, "description": "Reward pending approval"},
            {"status": RewardStatus.APPROVED, "description": "Reward approved, awaiting distribution"},
            {"status": RewardStatus.DISTRIBUTED, "description": "Reward distributed to agent"},
            {"status": RewardStatus.REJECTED, "description": "Reward rejected"}
        ]
    }
