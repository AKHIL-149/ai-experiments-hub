"""
Agent Learning API

REST API endpoints for agent learning, experience tracking, and skill development.
"""

from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_learning import (
    AgentLearning,
    ExperienceType,
    LearningStrategy,
    SkillLevel
)


router = APIRouter()


# Request/Response Models
class InitializeLearningRequest(BaseModel):
    agent_id: int = Field(..., description="Agent ID")
    initial_skills: Optional[Dict[str, float]] = Field(None, description="Initial skill proficiencies")


class RecordExperienceRequest(BaseModel):
    experience_type: str = Field(..., description="Type of experience")
    outcome: str = Field(..., description="Outcome (success/failure/neutral)")
    context: dict = Field(..., description="Experience context and details")
    learning_value: float = Field(1.0, description="Learning value (0-1)")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class UpdateSkillRequest(BaseModel):
    skill_name: str = Field(..., description="Skill name")
    proficiency_delta: float = Field(..., description="Change in proficiency (-100 to +100)")
    reason: str = Field("", description="Reason for update")


class LearnStrategyRequest(BaseModel):
    strategy_name: str = Field(..., description="Strategy name")
    strategy_details: dict = Field(..., description="Strategy details and parameters")
    effectiveness: float = Field(..., description="Effectiveness (0-1)")
    learning_strategy: str = Field(LearningStrategy.REINFORCEMENT, description="How it was learned")


class ApplyStrategyRequest(BaseModel):
    strategy_name: str = Field(..., description="Strategy name")
    success: bool = Field(..., description="Whether application was successful")


class GetRecommendationsRequest(BaseModel):
    task_context: dict = Field(..., description="Task context for recommendations")


@router.post("/agents/initialize")
def initialize_learning(
    request: InitializeLearningRequest,
    session: Session = Depends(get_db_session)
):
    """
    Initialize learning tracking for an agent.

    Creates learning profile with optional initial skills.
    Agents must be initialized before recording experiences.
    """
    try:
        profile = AgentLearning.initialize_learning(
            session=session,
            agent_id=request.agent_id,
            initial_skills=request.initial_skills
        )

        return {
            "success": True,
            "profile": profile,
            "message": "Learning initialized successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/experiences")
def record_experience(
    agent_id: int,
    request: RecordExperienceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record a learning experience for an agent.

    Tracks experiences to build knowledge base and recognize patterns.
    Triggers automatic pattern recognition after every 10 experiences.
    """
    try:
        experience = AgentLearning.record_experience(
            session=session,
            agent_id=agent_id,
            experience_type=request.experience_type,
            outcome=request.outcome,
            context=request.context,
            learning_value=request.learning_value,
            metadata=request.metadata
        )

        return {
            "success": True,
            "experience": experience,
            "message": f"Experience recorded: {request.experience_type} ({request.outcome})"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/skills")
def update_skill_proficiency(
    agent_id: int,
    request: UpdateSkillRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update agent's skill proficiency.

    Increases or decreases proficiency based on performance.
    Proficiency ranges from 0 (novice) to 100 (expert).
    """
    try:
        skill = AgentLearning.update_skill_proficiency(
            session=session,
            agent_id=agent_id,
            skill_name=request.skill_name,
            proficiency_delta=request.proficiency_delta,
            reason=request.reason
        )

        return {
            "success": True,
            "skill": skill,
            "message": f"Skill '{request.skill_name}' updated to {skill['proficiency']:.1f}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/strategies")
def learn_strategy(
    agent_id: int,
    request: LearnStrategyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record a learned strategy.

    Stores strategies discovered through experience for future use.
    Tracks effectiveness and usage statistics.
    """
    try:
        strategy = AgentLearning.learn_strategy(
            session=session,
            agent_id=agent_id,
            strategy_name=request.strategy_name,
            strategy_details=request.strategy_details,
            effectiveness=request.effectiveness,
            learning_strategy=request.learning_strategy
        )

        return {
            "success": True,
            "strategy": strategy,
            "message": f"Strategy '{request.strategy_name}' learned"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/strategies/apply")
def apply_strategy(
    agent_id: int,
    request: ApplyStrategyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record application of a learned strategy.

    Updates strategy statistics and recalculates effectiveness
    based on success/failure outcomes.
    """
    try:
        strategy = AgentLearning.apply_strategy(
            session=session,
            agent_id=agent_id,
            strategy_name=request.strategy_name,
            success=request.success
        )

        return {
            "success": True,
            "strategy": strategy,
            "message": f"Strategy applied: {'success' if request.success else 'failure'}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/recommendations")
def get_recommendations(
    agent_id: int,
    request: GetRecommendationsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Get learning-based recommendations for a task.

    Analyzes past experiences to recommend strategies, identify
    skills to improve, and estimate success probability.
    """
    try:
        recommendations = AgentLearning.get_recommendations(
            session=session,
            agent_id=agent_id,
            task_context=request.task_context
        )

        return {
            "success": True,
            **recommendations
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/progress")
def get_learning_progress(
    agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get agent's learning progress over time.

    Returns learning curve, success rates, skill development,
    and pattern recognition statistics.
    """
    try:
        progress = AgentLearning.get_learning_progress(
            session=session,
            agent_id=agent_id
        )

        return {
            "success": True,
            **progress
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get learning system statistics.

    Returns aggregate data on experiences, skills, strategies,
    and overall learning effectiveness across all agents.
    """
    try:
        stats = AgentLearning.get_learning_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/experience-types")
def list_experience_types():
    """
    List all experience types.

    Returns all types of experiences that can be recorded.
    """
    return {
        "success": True,
        "experience_types": [
            {"type": ExperienceType.TASK_SUCCESS, "description": "Successfully completed task"},
            {"type": ExperienceType.TASK_FAILURE, "description": "Failed to complete task"},
            {"type": ExperienceType.COLLABORATION_SUCCESS, "description": "Successful collaboration"},
            {"type": ExperienceType.COLLABORATION_FAILURE, "description": "Failed collaboration"},
            {"type": ExperienceType.CONFLICT_RESOLUTION, "description": "Resolved conflict"},
            {"type": ExperienceType.NEGOTIATION_SUCCESS, "description": "Successful negotiation"},
            {"type": ExperienceType.NEGOTIATION_FAILURE, "description": "Failed negotiation"}
        ]
    }


@router.get("/learning-strategies")
def list_learning_strategies():
    """
    List all learning strategies.

    Returns all methods agents can use to learn.
    """
    return {
        "success": True,
        "learning_strategies": [
            {"strategy": LearningStrategy.REINFORCEMENT, "description": "Learn from rewards and outcomes"},
            {"strategy": LearningStrategy.SUPERVISED, "description": "Learn from labeled examples"},
            {"strategy": LearningStrategy.IMITATION, "description": "Learn by observing others"},
            {"strategy": LearningStrategy.ADAPTIVE, "description": "Adapt strategies based on context"}
        ]
    }


@router.get("/skill-levels")
def list_skill_levels():
    """
    List all skill proficiency levels.

    Returns skill level classifications based on proficiency scores.
    """
    return {
        "success": True,
        "skill_levels": [
            {"level": SkillLevel.NOVICE, "proficiency_range": "0-20", "description": "Just starting out"},
            {"level": SkillLevel.BEGINNER, "proficiency_range": "21-40", "description": "Basic understanding"},
            {"level": SkillLevel.INTERMEDIATE, "proficiency_range": "41-60", "description": "Solid competence"},
            {"level": SkillLevel.ADVANCED, "proficiency_range": "61-80", "description": "High proficiency"},
            {"level": SkillLevel.EXPERT, "proficiency_range": "81-100", "description": "Mastery level"}
        ]
    }
