"""
Agent Negotiation API

REST API endpoints for agent-to-agent negotiations.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_negotiation import (
    AgentNegotiation,
    NegotiationType,
    NegotiationStatus,
    OfferStatus,
    NegotiationStrategy
)


router = APIRouter()


# Request/Response Models
class InitiateNegotiationRequest(BaseModel):
    initiator_agent_id: int = Field(..., description="Agent initiating negotiation")
    respondent_agent_id: int = Field(..., description="Agent responding to negotiation")
    negotiation_type: str = Field(..., description="Type of negotiation")
    subject: str = Field(..., description="Negotiation subject/topic")
    initial_proposal: Dict[str, Any] = Field(..., description="Initial proposal terms")
    strategy: str = Field(NegotiationStrategy.COOPERATIVE, description="Negotiation strategy")
    deadline_hours: int = Field(24, description="Negotiation deadline in hours")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RespondToOfferRequest(BaseModel):
    agent_id: int = Field(..., description="Agent responding")
    response: str = Field(..., description="Response (accept/reject/counter)")
    counter_proposal: Optional[Dict[str, Any]] = Field(None, description="Counter-proposal terms")
    reasoning: str = Field("", description="Response reasoning")


class WithdrawRequest(BaseModel):
    agent_id: int = Field(..., description="Agent withdrawing")
    reason: str = Field("", description="Withdrawal reason")


class ExtendDeadlineRequest(BaseModel):
    additional_hours: int = Field(..., description="Hours to add to deadline")


@router.post("/negotiations")
def initiate_negotiation(
    request: InitiateNegotiationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Initiate a negotiation between two agents.

    Creates a new negotiation with an initial proposal. The respondent
    agent can then accept, reject, or counter the proposal.
    """
    try:
        negotiation = AgentNegotiation.initiate_negotiation(
            session=session,
            initiator_agent_id=request.initiator_agent_id,
            respondent_agent_id=request.respondent_agent_id,
            negotiation_type=request.negotiation_type,
            subject=request.subject,
            initial_proposal=request.initial_proposal,
            strategy=request.strategy,
            deadline_hours=request.deadline_hours,
            metadata=request.metadata
        )

        return {
            "success": True,
            "negotiation": negotiation,
            "message": f"Negotiation initiated on: {request.subject}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/negotiations/{negotiation_id}/offers/{offer_id}/respond")
def respond_to_offer(
    negotiation_id: int,
    offer_id: int,
    request: RespondToOfferRequest,
    session: Session = Depends(get_db_session)
):
    """
    Respond to a negotiation offer.

    Accept, reject, or counter an offer. Counter-offers continue
    the negotiation to the next round.
    """
    try:
        negotiation = AgentNegotiation.respond_to_offer(
            session=session,
            negotiation_id=negotiation_id,
            offer_id=offer_id,
            agent_id=request.agent_id,
            response=request.response,
            counter_proposal=request.counter_proposal,
            reasoning=request.reasoning
        )

        return {
            "success": True,
            "negotiation": negotiation,
            "message": f"Response: {request.response}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/negotiations/{negotiation_id}/withdraw")
def withdraw_negotiation(
    negotiation_id: int,
    request: WithdrawRequest,
    session: Session = Depends(get_db_session)
):
    """
    Withdraw from a negotiation.

    Either party can withdraw from an active negotiation,
    ending it without agreement.
    """
    try:
        negotiation = AgentNegotiation.withdraw_negotiation(
            session=session,
            negotiation_id=negotiation_id,
            agent_id=request.agent_id,
            reason=request.reason
        )

        return {
            "success": True,
            "negotiation": negotiation,
            "message": "Negotiation withdrawn"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/negotiations/{negotiation_id}/extend")
def extend_deadline(
    negotiation_id: int,
    request: ExtendDeadlineRequest,
    session: Session = Depends(get_db_session)
):
    """
    Extend negotiation deadline.

    Adds additional time to the negotiation deadline to allow
    for more rounds of offers and counter-offers.
    """
    try:
        negotiation = AgentNegotiation.extend_deadline(
            session=session,
            negotiation_id=negotiation_id,
            additional_hours=request.additional_hours
        )

        return {
            "success": True,
            "negotiation": negotiation,
            "message": f"Deadline extended by {request.additional_hours} hours"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/negotiations/{negotiation_id}/compromise")
def suggest_compromise(
    negotiation_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Suggest a compromise for the negotiation.

    Analyzes offers from both parties and suggests a middle-ground
    compromise to help reach agreement.
    """
    try:
        suggestion = AgentNegotiation.suggest_compromise(
            session=session,
            negotiation_id=negotiation_id
        )

        return {
            "success": True,
            **suggestion
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/negotiations/{negotiation_id}")
def get_negotiation(
    negotiation_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get negotiation details including all offers.

    Returns complete negotiation information including status,
    all offers exchanged, and current state.
    """
    try:
        negotiation = AgentNegotiation.get_negotiation(
            session=session,
            negotiation_id=negotiation_id
        )

        return {
            "success": True,
            "negotiation": negotiation
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/negotiations")
def list_negotiations(
    status: Optional[str] = None,
    agent_id: Optional[int] = None,
    negotiation_type: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List negotiations with optional filtering.

    Filter by status, agent participation, or negotiation type.
    Returns negotiations matching the criteria.
    """
    try:
        result = AgentNegotiation.list_negotiations(
            session=session,
            status=status,
            agent_id=agent_id,
            negotiation_type=negotiation_type,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/negotiations")
def get_agent_negotiations(
    agent_id: int,
    status: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get all negotiations for a specific agent.

    Returns all negotiations where the agent is either
    the initiator or respondent.
    """
    try:
        result = AgentNegotiation.get_agent_negotiations(
            session=session,
            agent_id=agent_id,
            status=status
        )

        return {
            "success": True,
            "agent_id": agent_id,
            **result
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
    Get negotiation statistics.

    Returns statistics including total negotiations, success rates,
    average rounds to agreement, and breakdown by status and type.
    """
    try:
        stats = AgentNegotiation.get_negotiation_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/negotiations/{negotiation_id}/offers/{offer_id}")
def get_offer(
    negotiation_id: int,
    offer_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get specific offer details.

    Returns detailed information about a specific offer
    within a negotiation.
    """
    try:
        offer = AgentNegotiation.get_offer(
            session=session,
            negotiation_id=negotiation_id,
            offer_id=offer_id
        )

        return {
            "success": True,
            "offer": offer
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types")
def list_negotiation_types():
    """
    List all negotiation types.

    Returns all available types of negotiations that can be initiated.
    """
    return {
        "success": True,
        "negotiation_types": [
            {
                "type": NegotiationType.RESOURCE_ALLOCATION,
                "description": "Negotiate resource distribution"
            },
            {
                "type": NegotiationType.TASK_ASSIGNMENT,
                "description": "Negotiate task responsibility"
            },
            {
                "type": NegotiationType.COLLABORATION_TERMS,
                "description": "Negotiate collaboration conditions"
            },
            {
                "type": NegotiationType.PRIORITY_ADJUSTMENT,
                "description": "Negotiate priority changes"
            },
            {
                "type": NegotiationType.DEADLINE_EXTENSION,
                "description": "Negotiate deadline extensions"
            },
            {
                "type": NegotiationType.COST_SHARING,
                "description": "Negotiate cost distribution"
            }
        ]
    }


@router.get("/strategies")
def list_negotiation_strategies():
    """
    List all negotiation strategies.

    Returns all available strategies that can be used
    when initiating negotiations.
    """
    return {
        "success": True,
        "strategies": [
            {
                "strategy": NegotiationStrategy.COMPETITIVE,
                "description": "Win-lose, maximize own benefit"
            },
            {
                "strategy": NegotiationStrategy.COOPERATIVE,
                "description": "Win-win, maximize joint benefit"
            },
            {
                "strategy": NegotiationStrategy.COMPROMISE,
                "description": "Meet in the middle"
            },
            {
                "strategy": NegotiationStrategy.ACCOMMODATING,
                "description": "Yield to other party's interests"
            },
            {
                "strategy": NegotiationStrategy.AVOIDING,
                "description": "Withdraw from negotiation"
            }
        ]
    }


@router.get("/statuses")
def list_statuses():
    """
    List all negotiation statuses.

    Returns all possible statuses a negotiation can have.
    """
    return {
        "success": True,
        "statuses": [
            {
                "status": NegotiationStatus.OPEN,
                "description": "Negotiation initiated, awaiting response"
            },
            {
                "status": NegotiationStatus.IN_PROGRESS,
                "description": "Active negotiation with ongoing offers"
            },
            {
                "status": NegotiationStatus.AGREEMENT_REACHED,
                "description": "Successful agreement reached"
            },
            {
                "status": NegotiationStatus.REJECTED,
                "description": "Negotiation rejected by respondent"
            },
            {
                "status": NegotiationStatus.EXPIRED,
                "description": "Negotiation deadline passed"
            },
            {
                "status": NegotiationStatus.WITHDRAWN,
                "description": "Negotiation withdrawn by one party"
            }
        ]
    }
