"""
Agent Consensus API

REST API endpoints for agent consensus and voting mechanisms.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_consensus import (
    AgentConsensus,
    ConsensusType,
    ProposalStatus,
    VoteType
)


router = APIRouter()


# Request/Response Models
class CreateProposalRequest(BaseModel):
    title: str = Field(..., description="Proposal title")
    description: str = Field(..., description="Proposal description")
    options: List[str] = Field(..., description="List of options to choose from")
    consensus_type: str = Field(ConsensusType.SIMPLE_MAJORITY, description="Consensus mechanism type")
    eligible_agents: Optional[List[int]] = Field(None, description="Eligible agent IDs (None = all)")
    proposer_agent_id: Optional[int] = Field(None, description="Proposing agent ID")
    voting_deadline_minutes: int = Field(60, description="Voting deadline in minutes")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class CastVoteRequest(BaseModel):
    agent_id: int = Field(..., description="Agent casting vote")
    vote: str = Field(..., description="Vote type (yes/no/abstain/veto)")
    option: Optional[str] = Field(None, description="Selected option")
    ranked_options: Optional[List[str]] = Field(None, description="Ranked list of options")
    weight: Optional[float] = Field(None, description="Vote weight (for weighted voting)")
    reasoning: str = Field("", description="Vote reasoning")


class FinalizeProposalRequest(BaseModel):
    quorum_threshold: float = Field(0.5, description="Minimum participation rate (0.0-1.0)")


class CancelProposalRequest(BaseModel):
    reason: str = Field("", description="Cancellation reason")


class ExtendDeadlineRequest(BaseModel):
    additional_minutes: int = Field(..., description="Minutes to add to deadline")


@router.post("/proposals")
def create_proposal(
    request: CreateProposalRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a consensus proposal for agents to vote on.

    Creates a proposal with specified options and consensus mechanism.
    Eligible agents can then vote on the proposal until the deadline.
    """
    try:
        proposal = AgentConsensus.create_proposal(
            session=session,
            title=request.title,
            description=request.description,
            options=request.options,
            consensus_type=request.consensus_type,
            eligible_agents=request.eligible_agents,
            proposer_agent_id=request.proposer_agent_id,
            voting_deadline_minutes=request.voting_deadline_minutes,
            metadata=request.metadata
        )

        return {
            "success": True,
            "proposal": proposal,
            "message": f"Proposal created with {len(proposal['eligible_agents'])} eligible voters"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals/{proposal_id}/vote")
def cast_vote(
    proposal_id: int,
    request: CastVoteRequest,
    session: Session = Depends(get_db_session)
):
    """
    Cast a vote on a proposal.

    Agents eligible to vote can cast their vote along with optional
    reasoning. Supports different voting types including ranked choice
    and weighted voting.
    """
    try:
        vote = AgentConsensus.cast_vote(
            session=session,
            proposal_id=proposal_id,
            agent_id=request.agent_id,
            vote=request.vote,
            option=request.option,
            ranked_options=request.ranked_options,
            weight=request.weight,
            reasoning=request.reasoning
        )

        return {
            "success": True,
            "vote": vote,
            "message": f"Vote cast successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals/{proposal_id}/finalize")
def finalize_proposal(
    proposal_id: int,
    request: FinalizeProposalRequest,
    session: Session = Depends(get_db_session)
):
    """
    Finalize a proposal and determine the outcome.

    Applies the consensus mechanism to determine if the proposal
    passes or fails. Checks quorum requirements and calculates
    winning option based on the consensus type.
    """
    try:
        proposal = AgentConsensus.finalize_proposal(
            session=session,
            proposal_id=proposal_id,
            quorum_threshold=request.quorum_threshold
        )

        return {
            "success": True,
            "proposal": proposal,
            "message": f"Proposal {proposal['status']}: {proposal.get('winning_option', 'N/A')}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proposals/{proposal_id}")
def get_proposal(
    proposal_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get proposal details including votes.

    Returns proposal information, current vote counts,
    and all votes cast so far.
    """
    try:
        proposal = AgentConsensus.get_proposal(
            session=session,
            proposal_id=proposal_id
        )

        return {
            "success": True,
            "proposal": proposal
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proposals")
def list_proposals(
    status: Optional[str] = None,
    agent_id: Optional[int] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List proposals with optional filtering.

    Filter by status or agent eligibility. Returns proposals
    that match the specified criteria.
    """
    try:
        result = AgentConsensus.list_proposals(
            session=session,
            status=status,
            agent_id=agent_id,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/votes")
def get_agent_votes(
    agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get all votes cast by a specific agent.

    Returns the agent's complete voting history including
    proposals they voted on and their votes.
    """
    try:
        result = AgentConsensus.get_agent_votes(
            session=session,
            agent_id=agent_id
        )

        return {
            "success": True,
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
    Get consensus statistics.

    Returns statistics including total proposals, pass rates,
    participation rates, and breakdown by status and type.
    """
    try:
        stats = AgentConsensus.get_consensus_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals/{proposal_id}/cancel")
def cancel_proposal(
    proposal_id: int,
    request: CancelProposalRequest,
    session: Session = Depends(get_db_session)
):
    """
    Cancel an active proposal.

    Cancels a proposal that is currently in voting status.
    Requires a cancellation reason.
    """
    try:
        proposal = AgentConsensus.cancel_proposal(
            session=session,
            proposal_id=proposal_id,
            reason=request.reason
        )

        return {
            "success": True,
            "proposal": proposal,
            "message": "Proposal cancelled"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals/{proposal_id}/extend")
def extend_deadline(
    proposal_id: int,
    request: ExtendDeadlineRequest,
    session: Session = Depends(get_db_session)
):
    """
    Extend voting deadline.

    Extends the voting deadline for an active proposal
    by the specified number of minutes.
    """
    try:
        proposal = AgentConsensus.extend_deadline(
            session=session,
            proposal_id=proposal_id,
            additional_minutes=request.additional_minutes
        )

        return {
            "success": True,
            "proposal": proposal,
            "message": f"Deadline extended by {request.additional_minutes} minutes"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/consensus-types")
def list_consensus_types():
    """
    List all available consensus mechanisms.

    Returns all consensus types that can be used when
    creating proposals.
    """
    return {
        "success": True,
        "consensus_types": [
            {
                "type": ConsensusType.SIMPLE_MAJORITY,
                "description": ">50% agreement required",
                "threshold": "50%"
            },
            {
                "type": ConsensusType.SUPERMAJORITY,
                "description": ">66% agreement required",
                "threshold": "66%"
            },
            {
                "type": ConsensusType.UNANIMOUS,
                "description": "100% agreement required",
                "threshold": "100%"
            },
            {
                "type": ConsensusType.WEIGHTED_VOTING,
                "description": "Votes weighted by agent priority",
                "threshold": "Varies"
            },
            {
                "type": ConsensusType.QUORUM_BASED,
                "description": "Minimum participation required",
                "threshold": "Configurable"
            },
            {
                "type": ConsensusType.RANKED_CHOICE,
                "description": "Agents rank options (instant runoff)",
                "threshold": "Majority"
            },
            {
                "type": ConsensusType.VETO_BASED,
                "description": "Any agent can veto",
                "threshold": "No vetos"
            }
        ]
    }


@router.get("/vote-types")
def list_vote_types():
    """
    List all available vote types.

    Returns all vote types that can be cast on proposals.
    """
    return {
        "success": True,
        "vote_types": [
            {"type": VoteType.YES, "description": "Vote in favor"},
            {"type": VoteType.NO, "description": "Vote against"},
            {"type": VoteType.ABSTAIN, "description": "Abstain from voting"},
            {"type": VoteType.VETO, "description": "Veto the proposal (veto-based consensus only)"}
        ]
    }


@router.get("/proposal-statuses")
def list_proposal_statuses():
    """
    List all possible proposal statuses.

    Returns all statuses a proposal can have during its lifecycle.
    """
    return {
        "success": True,
        "statuses": [
            {"status": ProposalStatus.OPEN, "description": "Proposal created, not yet voting"},
            {"status": ProposalStatus.VOTING, "description": "Active voting period"},
            {"status": ProposalStatus.PASSED, "description": "Proposal passed consensus"},
            {"status": ProposalStatus.REJECTED, "description": "Proposal failed consensus"},
            {"status": ProposalStatus.VETOED, "description": "Proposal vetoed by agent"},
            {"status": ProposalStatus.EXPIRED, "description": "Voting deadline passed"}
        ]
    }
