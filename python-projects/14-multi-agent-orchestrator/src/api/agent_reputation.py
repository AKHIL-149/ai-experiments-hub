"""
Agent Reputation API

REST API endpoints for agent reputation and trust management.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_reputation import (
    AgentReputation,
    ReputationCategory,
    FeedbackType,
    TrustLevel
)


router = APIRouter()


# Request/Response Models
class InitializeReputationRequest(BaseModel):
    agent_id: int = Field(..., description="Agent ID")
    initial_score: float = Field(50.0, description="Initial reputation score (0-100)")


class UpdateScoreRequest(BaseModel):
    category: str = Field(..., description="Reputation category")
    score_delta: float = Field(..., description="Score change (-100 to +100)")
    reason: str = Field("", description="Reason for update")


class RecordTaskRequest(BaseModel):
    success: bool = Field(..., description="Task success status")
    rating: Optional[float] = Field(None, description="Task rating (0-5)")


class AddEndorsementRequest(BaseModel):
    endorser_agent_id: int = Field(..., description="Agent giving endorsement")
    category: str = Field(..., description="Category being endorsed")
    comment: str = Field("", description="Endorsement comment")


class AddFeedbackRequest(BaseModel):
    from_agent_id: int = Field(..., description="Agent giving feedback")
    feedback_type: str = Field(..., description="Feedback type (positive/neutral/negative)")
    category: str = Field(..., description="Feedback category")
    comment: str = Field("", description="Feedback comment")


class EstablishTrustRequest(BaseModel):
    trusted_agent_id: int = Field(..., description="Agent being trusted")
    trust_score: float = Field(..., description="Trust score (0-100)")
    reason: str = Field("", description="Reason for trust")


class ApplyDecayRequest(BaseModel):
    decay_factor: float = Field(0.01, description="Decay percentage (0-1)")


@router.post("/reputations")
def initialize_reputation(
    request: InitializeReputationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Initialize reputation for an agent.

    Creates a new reputation record with initial scores across all categories.
    All categories start at the same initial score (default 50).
    """
    try:
        reputation = AgentReputation.initialize_reputation(
            session=session,
            agent_id=request.agent_id,
            initial_score=request.initial_score
        )

        return {
            "success": True,
            "reputation": reputation,
            "message": f"Reputation initialized with score {request.initial_score}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reputations/{agent_id}/update")
def update_reputation_score(
    agent_id: int,
    request: UpdateScoreRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update agent reputation score in a specific category.

    Adjusts the score by the specified delta (positive or negative).
    Also updates the overall score and trust level.
    """
    try:
        reputation = AgentReputation.update_reputation_score(
            session=session,
            agent_id=agent_id,
            category=request.category,
            score_delta=request.score_delta,
            reason=request.reason
        )

        return {
            "success": True,
            "reputation": reputation,
            "message": f"Score updated: {request.category} ({request.score_delta:+.1f})"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reputations/{agent_id}/tasks")
def record_task_completion(
    agent_id: int,
    request: RecordTaskRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record task completion and update reputation.

    Automatically adjusts reputation based on success/failure.
    Optional rating provides additional reputation adjustment.
    """
    try:
        reputation = AgentReputation.record_task_completion(
            session=session,
            agent_id=agent_id,
            success=request.success,
            rating=request.rating
        )

        return {
            "success": True,
            "reputation": reputation,
            "message": f"Task {'completed' if request.success else 'failed'} recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reputations/{agent_id}/endorsements")
def add_endorsement(
    agent_id: int,
    request: AddEndorsementRequest,
    session: Session = Depends(get_db_session)
):
    """
    Add an endorsement from another agent.

    Endorsements boost reputation in specific categories.
    Value depends on the endorser's own reputation.
    """
    try:
        endorsement = AgentReputation.add_endorsement(
            session=session,
            agent_id=agent_id,
            endorser_agent_id=request.endorser_agent_id,
            category=request.category,
            comment=request.comment
        )

        return {
            "success": True,
            "endorsement": endorsement,
            "message": f"Endorsement added in {request.category}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reputations/{agent_id}/feedback")
def add_feedback(
    agent_id: int,
    request: AddFeedbackRequest,
    session: Session = Depends(get_db_session)
):
    """
    Add feedback from another agent.

    Feedback can be positive, neutral, or negative.
    Adjusts reputation accordingly in the specified category.
    """
    try:
        feedback = AgentReputation.add_feedback(
            session=session,
            agent_id=agent_id,
            from_agent_id=request.from_agent_id,
            feedback_type=request.feedback_type,
            category=request.category,
            comment=request.comment
        )

        return {
            "success": True,
            "feedback": feedback,
            "message": f"{request.feedback_type} feedback added"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reputations/{agent_id}/trust")
def establish_trust(
    agent_id: int,
    request: EstablishTrustRequest,
    session: Session = Depends(get_db_session)
):
    """
    Establish or update trust relationship between agents.

    Creates a directional trust relationship with a score (0-100).
    Trust relationships are used to inform collaboration decisions.
    """
    try:
        trust = AgentReputation.establish_trust(
            session=session,
            agent_id=agent_id,
            trusted_agent_id=request.trusted_agent_id,
            trust_score=request.trust_score,
            reason=request.reason
        )

        return {
            "success": True,
            "trust_relationship": trust,
            "message": f"Trust established with score {request.trust_score}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reputations/{agent_id}/decay")
def apply_reputation_decay(
    agent_id: int,
    request: ApplyDecayRequest,
    session: Session = Depends(get_db_session)
):
    """
    Apply time-based reputation decay.

    Gradually moves reputation scores toward neutral (50) over time.
    Prevents stale reputations from influencing current decisions.
    """
    try:
        reputation = AgentReputation.apply_reputation_decay(
            session=session,
            agent_id=agent_id,
            decay_factor=request.decay_factor
        )

        return {
            "success": True,
            "reputation": reputation,
            "message": f"Decay applied (factor: {request.decay_factor})"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reputations/{agent_id}")
def get_reputation(
    agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get agent reputation details.

    Returns complete reputation information including scores,
    trust level, recent endorsements, and feedback.
    """
    try:
        reputation = AgentReputation.get_reputation(
            session=session,
            agent_id=agent_id
        )

        return {
            "success": True,
            "reputation": reputation
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reputations/{agent_id}/trust-relationships")
def get_trust_relationships(
    agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get agent's trust relationships.

    Returns all trust relationships established by this agent
    toward other agents in the system.
    """
    try:
        relationships = AgentReputation.get_trust_relationships(
            session=session,
            agent_id=agent_id
        )

        return {
            "success": True,
            **relationships
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reputations/top")
def get_top_agents(
    limit: int = 10,
    category: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get top-rated agents.

    Returns the highest-rated agents overall or in a specific category.
    Useful for selecting high-quality agents for critical tasks.
    """
    try:
        result = AgentReputation.get_top_agents(
            session=session,
            limit=limit,
            category=category
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reputations/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get reputation system statistics.

    Returns aggregate statistics including average scores,
    total endorsements, feedback counts, and trust relationships.
    """
    try:
        stats = AgentReputation.get_reputation_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
def list_categories():
    """
    List all reputation categories.

    Returns all categories that can be scored and endorsed.
    """
    return {
        "success": True,
        "categories": [
            {
                "category": ReputationCategory.TASK_COMPLETION,
                "description": "Ability to complete assigned tasks successfully"
            },
            {
                "category": ReputationCategory.COLLABORATION,
                "description": "Quality of collaboration with other agents"
            },
            {
                "category": ReputationCategory.COMMUNICATION,
                "description": "Effectiveness of communication"
            },
            {
                "category": ReputationCategory.RELIABILITY,
                "description": "Consistency and dependability"
            },
            {
                "category": ReputationCategory.EXPERTISE,
                "description": "Domain knowledge and skill level"
            },
            {
                "category": ReputationCategory.RESPONSIVENESS,
                "description": "Speed and timeliness of responses"
            }
        ]
    }


@router.get("/feedback-types")
def list_feedback_types():
    """
    List all feedback types.

    Returns all types of feedback that can be given.
    """
    return {
        "success": True,
        "feedback_types": [
            {"type": FeedbackType.POSITIVE, "description": "Positive feedback, increases reputation"},
            {"type": FeedbackType.NEUTRAL, "description": "Neutral feedback, no reputation change"},
            {"type": FeedbackType.NEGATIVE, "description": "Negative feedback, decreases reputation"}
        ]
    }


@router.get("/trust-levels")
def list_trust_levels():
    """
    List all trust levels.

    Returns all possible trust levels based on reputation score.
    """
    return {
        "success": True,
        "trust_levels": [
            {"level": TrustLevel.UNTRUSTED, "score_range": "0-25", "description": "Untrusted agent"},
            {"level": TrustLevel.LOW, "score_range": "26-50", "description": "Low trust"},
            {"level": TrustLevel.MEDIUM, "score_range": "51-75", "description": "Medium trust"},
            {"level": TrustLevel.HIGH, "score_range": "76-90", "description": "High trust"},
            {"level": TrustLevel.VERIFIED, "score_range": "91-100", "description": "Verified trusted agent"}
        ]
    }
