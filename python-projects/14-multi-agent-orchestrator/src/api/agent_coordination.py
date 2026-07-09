"""
Agent Coordination Engine API

REST API endpoints for orchestrating multi-agent coordination.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_coordination import (
    AgentCoordination,
    CoordinationStrategy,
    CoordinationStatus
)


router = APIRouter()


# Request/Response Models
class InitiateCoordinationRequest(BaseModel):
    coordination_type: str = Field(..., description="Type of coordination")
    goal_description: str = Field(..., description="Goal description")
    strategy: str = Field(CoordinationStrategy.HYBRID, description="Coordination strategy")
    required_agents: Optional[List[int]] = Field(None, description="Required agent IDs")
    min_agents: int = Field(2, description="Minimum number of agents")
    max_agents: Optional[int] = Field(None, description="Maximum number of agents")
    constraints: Optional[dict] = Field(None, description="Constraints")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class JoinCoordinationRequest(BaseModel):
    capabilities: Optional[List[str]] = Field(None, description="Agent capabilities")
    commitment_level: float = Field(1.0, description="Commitment level (0-1)")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class StartNegotiationRequest(BaseModel):
    negotiation_topics: List[dict] = Field(..., description="Topics to negotiate")
    timeout_minutes: int = Field(60, description="Negotiation timeout in minutes")


class ProposeVoteRequest(BaseModel):
    proposal_id: str = Field(..., description="Proposal identifier")
    proposal_description: str = Field(..., description="Proposal description")
    voting_type: str = Field("majority", description="Voting type")
    required_threshold: float = Field(0.5, description="Required threshold (0-1)")


class CastVoteRequest(BaseModel):
    vote: bool = Field(..., description="Vote (true/false)")
    weight: float = Field(1.0, description="Vote weight")
    rationale: Optional[str] = Field(None, description="Voting rationale")


class CreateContractRequest(BaseModel):
    contract_terms: dict = Field(..., description="Contract terms")
    sla_terms: Optional[dict] = Field(None, description="SLA terms")
    duration_hours: int = Field(24, description="Contract duration in hours")


class StartExecutionRequest(BaseModel):
    execution_plan: dict = Field(..., description="Execution plan")
    monitoring_interval: int = Field(60, description="Monitoring interval in seconds")


class RecordOutcomeRequest(BaseModel):
    outcome_type: str = Field(..., description="Outcome type")
    outcome_data: dict = Field(..., description="Outcome data")
    success: bool = Field(True, description="Whether outcome was successful")


class CompleteCoordinationRequest(BaseModel):
    final_result: dict = Field(..., description="Final coordination result")
    success: bool = Field(True, description="Whether coordination succeeded")


class CancelCoordinationRequest(BaseModel):
    reason: str = Field(..., description="Cancellation reason")


@router.post("/sessions")
def initiate_coordination(
    initiator_agent_id: int,
    request: InitiateCoordinationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Initiate a coordination session.

    Creates a new multi-agent coordination session with specified strategy
    and parameters. The initiator sets the goal and coordination rules.
    """
    try:
        coordination_session = AgentCoordination.initiate_coordination(
            session=session,
            initiator_agent_id=initiator_agent_id,
            coordination_type=request.coordination_type,
            goal_description=request.goal_description,
            strategy=request.strategy,
            required_agents=request.required_agents,
            min_agents=request.min_agents,
            max_agents=request.max_agents,
            constraints=request.constraints,
            metadata=request.metadata
        )

        return {
            "success": True,
            "coordination_session": coordination_session,
            "message": f"Coordination session '{coordination_session['id']}' initiated"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/join")
def join_coordination(
    session_id: str,
    agent_id: int,
    request: JoinCoordinationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Join a coordination session.

    Adds an agent to an existing coordination session, contributing
    capabilities and committing to the coordination goal.
    """
    try:
        coordination_session = AgentCoordination.join_coordination(
            session=session,
            session_id=session_id,
            agent_id=agent_id,
            capabilities=request.capabilities,
            commitment_level=request.commitment_level,
            metadata=request.metadata
        )

        return {
            "success": True,
            "coordination_session": coordination_session,
            "message": f"Agent {agent_id} joined coordination"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/negotiation")
def start_negotiation(
    session_id: str,
    request: StartNegotiationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Start negotiation phase.

    Begins multi-agent negotiation on specified topics to reach
    agreements on coordination parameters.
    """
    try:
        coordination_session = AgentCoordination.start_negotiation_phase(
            session=session,
            session_id=session_id,
            negotiation_topics=request.negotiation_topics,
            timeout_minutes=request.timeout_minutes
        )

        return {
            "success": True,
            "coordination_session": coordination_session,
            "message": "Negotiation phase started"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/votes")
def propose_vote(
    session_id: str,
    request: ProposeVoteRequest,
    session: Session = Depends(get_db_session)
):
    """
    Propose a consensus vote.

    Creates a voting mechanism for participating agents to vote
    on a proposal and reach consensus.
    """
    try:
        vote = AgentCoordination.propose_consensus_vote(
            session=session,
            session_id=session_id,
            proposal_id=request.proposal_id,
            proposal_description=request.proposal_description,
            voting_type=request.voting_type,
            required_threshold=request.required_threshold
        )

        return {
            "success": True,
            "vote": vote,
            "message": f"Vote proposed: {request.proposal_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/votes/{proposal_id}/cast")
def cast_vote(
    session_id: str,
    proposal_id: str,
    agent_id: int,
    request: CastVoteRequest,
    session: Session = Depends(get_db_session)
):
    """
    Cast vote on a proposal.

    Agent votes on a proposal. When all agents vote, consensus
    is calculated based on the voting threshold.
    """
    try:
        vote_record = AgentCoordination.cast_vote(
            session=session,
            session_id=session_id,
            proposal_id=proposal_id,
            agent_id=agent_id,
            vote=request.vote,
            weight=request.weight,
            rationale=request.rationale
        )

        return {
            "success": True,
            "vote_record": vote_record,
            "message": f"Vote cast by agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/contracts")
def create_contract(
    session_id: str,
    request: CreateContractRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create coordination contract.

    Establishes formal contracts between coordinating agents
    with SLA terms and obligations.
    """
    try:
        contract = AgentCoordination.create_coordination_contract(
            session=session,
            session_id=session_id,
            contract_terms=request.contract_terms,
            sla_terms=request.sla_terms,
            duration_hours=request.duration_hours
        )

        return {
            "success": True,
            "contract": contract,
            "message": "Coordination contract created"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/execution")
def start_execution(
    session_id: str,
    request: StartExecutionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Start execution phase.

    Begins coordinated execution of the agreed-upon plan
    with monitoring and tracking.
    """
    try:
        coordination_session = AgentCoordination.start_execution_phase(
            session=session,
            session_id=session_id,
            execution_plan=request.execution_plan,
            monitoring_interval=request.monitoring_interval
        )

        return {
            "success": True,
            "coordination_session": coordination_session,
            "message": "Execution phase started"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/outcomes")
def record_outcome(
    session_id: str,
    agent_id: int,
    request: RecordOutcomeRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record coordination outcome.

    Tracks individual agent contributions and results during
    the execution phase.
    """
    try:
        outcome = AgentCoordination.record_coordination_outcome(
            session=session,
            session_id=session_id,
            agent_id=agent_id,
            outcome_type=request.outcome_type,
            outcome_data=request.outcome_data,
            success=request.success
        )

        return {
            "success": True,
            "outcome": outcome,
            "message": "Outcome recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/complete")
def complete_coordination(
    session_id: str,
    request: CompleteCoordinationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Complete coordination session.

    Finalizes the coordination, records final results, and updates
    agent statistics and history.
    """
    try:
        coordination_session = AgentCoordination.complete_coordination(
            session=session,
            session_id=session_id,
            final_result=request.final_result,
            success=request.success
        )

        return {
            "success": True,
            "coordination_session": coordination_session,
            "message": f"Coordination {'completed successfully' if request.success else 'failed'}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/cancel")
def cancel_coordination(
    session_id: str,
    cancelling_agent_id: int,
    request: CancelCoordinationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Cancel coordination session.

    Allows participating agents to cancel the coordination
    with a reason.
    """
    try:
        coordination_session = AgentCoordination.cancel_coordination(
            session=session,
            session_id=session_id,
            cancelling_agent_id=cancelling_agent_id,
            reason=request.reason
        )

        return {
            "success": True,
            "coordination_session": coordination_session,
            "message": "Coordination cancelled"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
def get_coordination_session(
    session_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get coordination session details.

    Returns complete information about a coordination session
    including status, participants, votes, contracts, and outcomes.
    """
    try:
        coordination_session = AgentCoordination.get_coordination_session(
            session=session,
            session_id=session_id
        )

        return {
            "success": True,
            "coordination_session": coordination_session
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
def list_coordination_sessions(
    status: Optional[str] = None,
    strategy: Optional[str] = None,
    agent_id: Optional[int] = None,
    coordination_type: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    List coordination sessions.

    Returns coordination sessions with optional filtering by
    status, strategy, agent, or coordination type.
    """
    try:
        result = AgentCoordination.list_coordination_sessions(
            session=session,
            status=status,
            strategy=strategy,
            agent_id=agent_id,
            coordination_type=coordination_type
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/history")
def get_agent_history(
    agent_id: int,
    limit: int = 10,
    session: Session = Depends(get_db_session)
):
    """
    Get agent's coordination history.

    Returns all coordination sessions the agent participated in
    with statistics and performance metrics.
    """
    try:
        result = AgentCoordination.get_agent_coordination_history(
            session=session,
            agent_id=agent_id,
            limit=limit
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
    Get coordination system statistics.

    Returns aggregate metrics about all coordination sessions including
    success rates, strategy distribution, and performance data.
    """
    try:
        stats = AgentCoordination.get_coordination_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
def list_coordination_strategies():
    """
    List all coordination strategies.

    Returns all available coordination strategies and their descriptions.
    """
    return {
        "success": True,
        "strategies": [
            {
                "strategy": CoordinationStrategy.HIERARCHICAL,
                "description": "Top-down coordination with clear hierarchy"
            },
            {
                "strategy": CoordinationStrategy.DEMOCRATIC,
                "description": "Democratic coordination with voting and consensus"
            },
            {
                "strategy": CoordinationStrategy.MARKET_BASED,
                "description": "Market-based coordination using auctions and negotiations"
            },
            {
                "strategy": CoordinationStrategy.TRUST_BASED,
                "description": "Trust-based coordination using reputation and relationships"
            },
            {
                "strategy": CoordinationStrategy.HYBRID,
                "description": "Hybrid approach combining multiple strategies"
            }
        ]
    }


@router.get("/statuses")
def list_coordination_statuses():
    """
    List all coordination statuses.

    Returns all possible coordination session lifecycle statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": CoordinationStatus.INITIATED, "description": "Coordination initiated, waiting for agents"},
            {"status": CoordinationStatus.FORMING_COALITION, "description": "Forming coalition of agents"},
            {"status": CoordinationStatus.NEGOTIATING, "description": "Negotiating terms and parameters"},
            {"status": CoordinationStatus.VOTING, "description": "Voting on proposals"},
            {"status": CoordinationStatus.EXECUTING, "description": "Executing coordinated plan"},
            {"status": CoordinationStatus.COMPLETED, "description": "Coordination completed successfully"},
            {"status": CoordinationStatus.FAILED, "description": "Coordination failed"},
            {"status": CoordinationStatus.CANCELLED, "description": "Coordination cancelled"}
        ]
    }
