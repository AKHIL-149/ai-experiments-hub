"""
Agent Trust System API

REST API endpoints for managing trust relationships and verification.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_trust import (
    AgentTrust,
    TrustLevel,
    RecommendationType,
    VerificationStatus
)


router = APIRouter()


# Request/Response Models
class EstablishTrustRequest(BaseModel):
    agent_b_id: int = Field(..., description="Second agent ID")
    initial_score: float = Field(0.5, description="Initial trust score (0-1)")
    trust_level: Optional[str] = Field(None, description="Trust level")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class UpdateTrustScoreRequest(BaseModel):
    agent_b_id: int = Field(..., description="Second agent ID")
    new_score: Optional[float] = Field(None, description="New absolute score")
    adjustment: Optional[float] = Field(None, description="Score adjustment")
    reason: Optional[str] = Field(None, description="Reason for update")


class RecordInteractionRequest(BaseModel):
    agent_b_id: int = Field(..., description="Second agent ID")
    success: bool = Field(..., description="Whether interaction succeeded")
    interaction_type: Optional[str] = Field(None, description="Interaction type")
    metadata: Optional[dict] = Field(None, description="Interaction metadata")


class AddRecommendationRequest(BaseModel):
    recommended_agent_id: int = Field(..., description="Agent being recommended")
    target_agent_id: int = Field(..., description="Agent receiving recommendation")
    recommendation_type: str = Field(..., description="Recommendation type")
    score: float = Field(..., description="Recommended trust score (0-1)")
    comment: Optional[str] = Field(None, description="Optional comment")
    evidence: Optional[dict] = Field(None, description="Supporting evidence")


class RequestVerificationRequest(BaseModel):
    verification_type: str = Field(..., description="Type of verification")
    evidence: dict = Field(..., description="Evidence to verify")
    verifier_agent_id: Optional[int] = Field(None, description="Specific verifier")


class VerifyAgentRequest(BaseModel):
    approved: bool = Field(..., description="Whether verification passed")
    verifier_notes: Optional[str] = Field(None, description="Verifier notes")


@router.post("/relationships")
def establish_trust(
    agent_a_id: int,
    request: EstablishTrustRequest,
    session: Session = Depends(get_db_session)
):
    """
    Establish trust relationship between agents.

    Creates bidirectional trust relationship with initial score.
    Trust scores range from 0 (no trust) to 1 (complete trust).
    """
    try:
        relationship = AgentTrust.establish_trust(
            session=session,
            agent_a_id=agent_a_id,
            agent_b_id=request.agent_b_id,
            initial_score=request.initial_score,
            trust_level=request.trust_level,
            metadata=request.metadata
        )

        return {
            "success": True,
            "relationship": relationship,
            "message": "Trust relationship established"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/relationships/{agent_a_id}/score")
def update_trust_score(
    agent_a_id: int,
    request: UpdateTrustScoreRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update trust score between agents.

    Can set new absolute score or apply adjustment.
    Trust automatically decays over time without interaction.
    """
    try:
        relationship = AgentTrust.update_trust_score(
            session=session,
            agent_a_id=agent_a_id,
            agent_b_id=request.agent_b_id,
            new_score=request.new_score,
            adjustment=request.adjustment,
            reason=request.reason
        )

        return {
            "success": True,
            "relationship": relationship,
            "message": "Trust score updated"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/relationships/{agent_a_id}/interactions")
def record_interaction(
    agent_a_id: int,
    request: RecordInteractionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record interaction between agents.

    Automatically adjusts trust based on interaction outcome.
    Successful interactions increase trust, failures decrease it.
    """
    try:
        relationship = AgentTrust.record_interaction(
            session=session,
            agent_a_id=agent_a_id,
            agent_b_id=request.agent_b_id,
            success=request.success,
            interaction_type=request.interaction_type,
            metadata=request.metadata
        )

        return {
            "success": True,
            "relationship": relationship,
            "message": f"Interaction recorded: {'success' if request.success else 'failure'}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommendations")
def add_recommendation(
    recommender_agent_id: int,
    request: AddRecommendationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Add trust recommendation.

    Recommender vouches for recommended agent to target agent.
    Recommendation is weighted by recommender's trust with target.
    """
    try:
        recommendation = AgentTrust.add_recommendation(
            session=session,
            recommender_agent_id=recommender_agent_id,
            recommended_agent_id=request.recommended_agent_id,
            target_agent_id=request.target_agent_id,
            recommendation_type=request.recommendation_type,
            score=request.score,
            comment=request.comment,
            evidence=request.evidence
        )

        return {
            "success": True,
            "recommendation": recommendation,
            "message": "Recommendation added"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verifications")
def request_verification(
    agent_id: int,
    request: RequestVerificationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Request verification of credentials.

    Agent submits evidence for verification by trusted verifier.
    Verified agents receive global trust boost.
    """
    try:
        verification = AgentTrust.request_verification(
            session=session,
            agent_id=agent_id,
            verification_type=request.verification_type,
            evidence=request.evidence,
            verifier_agent_id=request.verifier_agent_id
        )

        return {
            "success": True,
            "verification": verification,
            "message": "Verification requested"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verifications/{verification_id}/verify")
def verify_agent(
    verification_id: str,
    verifier_agent_id: int,
    request: VerifyAgentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Verify agent credentials.

    Verifier reviews evidence and approves or rejects.
    Approved verifications boost agent's global trust.
    """
    try:
        verification = AgentTrust.verify_agent(
            session=session,
            verification_id=verification_id,
            verifier_agent_id=verifier_agent_id,
            approved=request.approved,
            verifier_notes=request.verifier_notes
        )

        return {
            "success": True,
            "verification": verification,
            "message": f"Verification {'approved' if request.approved else 'rejected'}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/relationships/{agent_a_id}/{agent_b_id}/score")
def get_trust_score(
    agent_a_id: int,
    agent_b_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get trust score between two agents.

    Returns simple numeric score (0-1) representing trust level.
    """
    try:
        score = AgentTrust.get_trust_score(
            session=session,
            agent_a_id=agent_a_id,
            agent_b_id=agent_b_id
        )

        return {
            "success": True,
            "agent_a_id": agent_a_id,
            "agent_b_id": agent_b_id,
            "trust_score": score,
            "trust_level": AgentTrust._score_to_level(score)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/relationships/{agent_a_id}/{agent_b_id}")
def get_trust_relationship(
    agent_a_id: int,
    agent_b_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get detailed trust relationship.

    Returns complete relationship data including interaction history,
    success rates, and trust score evolution.
    """
    try:
        relationship = AgentTrust.get_trust_relationship(
            session=session,
            agent_a_id=agent_a_id,
            agent_b_id=agent_b_id
        )

        return {
            "success": True,
            "relationship": relationship
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/trusted")
def get_trusted_agents(
    agent_id: int,
    min_trust_level: str = TrustLevel.MEDIUM,
    limit: int = 10,
    session: Session = Depends(get_db_session)
):
    """
    Get agents trusted by an agent.

    Returns list of agents with trust scores above minimum level,
    sorted by trust score descending.
    """
    try:
        result = AgentTrust.get_trusted_agents(
            session=session,
            agent_id=agent_id,
            min_trust_level=min_trust_level,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations/{target_agent_id}/{recommended_agent_id}")
def get_recommendations(
    target_agent_id: int,
    recommended_agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get recommendations for an agent.

    Returns all recommendations for recommended_agent to target_agent,
    with weighted average based on recommender trust.
    """
    try:
        result = AgentTrust.get_recommendations(
            session=session,
            target_agent_id=target_agent_id,
            recommended_agent_id=recommended_agent_id
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/global-trust")
def get_global_trust_score(
    agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get agent's global trust score.

    Returns overall trust score aggregated from all relationships,
    verifications, and system-wide reputation.
    """
    try:
        result = AgentTrust.get_global_trust_score(
            session=session,
            agent_id=agent_id
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get trust system statistics.

    Returns aggregate data including total relationships, recommendations,
    verifications, and trust score distributions.
    """
    try:
        stats = AgentTrust.get_trust_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trust-levels")
def list_trust_levels():
    """
    List all trust levels.

    Returns all possible trust level classifications.
    """
    return {
        "success": True,
        "trust_levels": [
            {"level": TrustLevel.UNKNOWN, "min_score": 0.0, "description": "No trust relationship"},
            {"level": TrustLevel.UNTRUSTED, "min_score": 0.0, "description": "Untrusted agent"},
            {"level": TrustLevel.LOW, "min_score": 0.3, "description": "Low trust"},
            {"level": TrustLevel.MEDIUM, "min_score": 0.5, "description": "Medium trust"},
            {"level": TrustLevel.HIGH, "min_score": 0.7, "description": "High trust"},
            {"level": TrustLevel.VERIFIED, "min_score": 0.9, "description": "Verified and highly trusted"}
        ]
    }


@router.get("/recommendation-types")
def list_recommendation_types():
    """
    List all recommendation types.

    Returns all types of trust recommendations.
    """
    return {
        "success": True,
        "recommendation_types": [
            {"type": RecommendationType.POSITIVE, "description": "Positive recommendation"},
            {"type": RecommendationType.NEUTRAL, "description": "Neutral observation"},
            {"type": RecommendationType.NEGATIVE, "description": "Negative warning"}
        ]
    }


@router.get("/verification-statuses")
def list_verification_statuses():
    """
    List all verification statuses.

    Returns all possible verification status values.
    """
    return {
        "success": True,
        "statuses": [
            {"status": VerificationStatus.UNVERIFIED, "description": "Not yet verified"},
            {"status": VerificationStatus.PENDING, "description": "Verification pending"},
            {"status": VerificationStatus.VERIFIED, "description": "Verified and approved"},
            {"status": VerificationStatus.REJECTED, "description": "Verification rejected"}
        ]
    }
