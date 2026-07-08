"""
Agent Consensus Service

Enables agents to reach consensus on decisions through various mechanisms
including voting, quorum-based decisions, weighted voting, and consensus protocols.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from collections import Counter

from src.models.database import Agent
from src.core.logging import logger


class ConsensusType:
    """Consensus mechanism types"""
    SIMPLE_MAJORITY = "simple_majority"  # >50% agreement
    SUPERMAJORITY = "supermajority"  # >66% agreement
    UNANIMOUS = "unanimous"  # 100% agreement
    WEIGHTED_VOTING = "weighted_voting"  # Votes weighted by agent priority
    QUORUM_BASED = "quorum_based"  # Minimum participation required
    RANKED_CHOICE = "ranked_choice"  # Agents rank options
    VETO_BASED = "veto_based"  # Any agent can veto


class ProposalStatus:
    """Proposal status constants"""
    OPEN = "open"
    VOTING = "voting"
    PASSED = "passed"
    REJECTED = "rejected"
    VETOED = "vetoed"
    EXPIRED = "expired"


class VoteType:
    """Vote type constants"""
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"
    VETO = "veto"


class AgentConsensus:
    """Service for managing agent consensus and voting"""

    # In-memory storage for consensus data
    _proposals: Dict[int, Dict[str, Any]] = {}
    _votes: Dict[int, List[Dict[str, Any]]] = {}  # proposal_id -> votes
    _consensus_history: List[Dict[str, Any]] = []

    # Counters
    _proposal_counter = 0

    @staticmethod
    def create_proposal(
        session: Session,
        title: str,
        description: str,
        options: List[str],
        consensus_type: str = ConsensusType.SIMPLE_MAJORITY,
        eligible_agents: Optional[List[int]] = None,
        proposer_agent_id: Optional[int] = None,
        voting_deadline_minutes: int = 60,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a consensus proposal.

        Args:
            session: Database session
            title: Proposal title
            description: Proposal description
            options: List of options to choose from
            consensus_type: Type of consensus mechanism
            eligible_agents: List of agent IDs eligible to vote (None = all agents)
            proposer_agent_id: Agent proposing the decision
            voting_deadline_minutes: Voting deadline in minutes
            metadata: Optional metadata

        Returns:
            Proposal details
        """
        # Validate proposer if provided
        if proposer_agent_id:
            proposer = session.query(Agent).filter(Agent.id == proposer_agent_id).first()
            if not proposer:
                raise ValueError(f"Proposer agent {proposer_agent_id} not found")

        # Validate eligible agents if provided
        if eligible_agents:
            agents = session.query(Agent).filter(Agent.id.in_(eligible_agents)).all()
            if len(agents) != len(eligible_agents):
                raise ValueError("One or more eligible agents not found")
        else:
            # All agents are eligible
            all_agents = session.query(Agent).all()
            eligible_agents = [agent.id for agent in all_agents]

        AgentConsensus._proposal_counter += 1
        proposal_id = AgentConsensus._proposal_counter

        proposal = {
            "proposal_id": proposal_id,
            "title": title,
            "description": description,
            "options": options,
            "consensus_type": consensus_type,
            "eligible_agents": eligible_agents,
            "proposer_agent_id": proposer_agent_id,
            "status": ProposalStatus.VOTING,
            "created_at": datetime.utcnow().isoformat(),
            "voting_deadline": (datetime.utcnow() + timedelta(minutes=voting_deadline_minutes)).isoformat(),
            "finalized_at": None,
            "winning_option": None,
            "vote_counts": {option: 0 for option in options},
            "participation_count": 0,
            "metadata": metadata or {}
        }

        AgentConsensus._proposals[proposal_id] = proposal
        AgentConsensus._votes[proposal_id] = []

        logger.info(
            f"Created proposal {proposal_id}: '{title}' "
            f"with {len(eligible_agents)} eligible voters"
        )

        return proposal

    @staticmethod
    def cast_vote(
        session: Session,
        proposal_id: int,
        agent_id: int,
        vote: str,
        option: Optional[str] = None,
        ranked_options: Optional[List[str]] = None,
        weight: Optional[float] = None,
        reasoning: str = ""
    ) -> Dict[str, Any]:
        """
        Cast a vote on a proposal.

        Args:
            session: Database session
            proposal_id: Proposal ID
            agent_id: Agent casting vote
            vote: Vote type (yes/no/abstain/veto)
            option: Selected option (for multi-option proposals)
            ranked_options: Ranked list of options (for ranked choice)
            weight: Vote weight (for weighted voting)
            reasoning: Optional reasoning for vote

        Returns:
            Vote details
        """
        if proposal_id not in AgentConsensus._proposals:
            raise ValueError(f"Proposal {proposal_id} not found")

        proposal = AgentConsensus._proposals[proposal_id]

        # Check if agent is eligible
        if agent_id not in proposal["eligible_agents"]:
            raise ValueError(f"Agent {agent_id} not eligible to vote on this proposal")

        # Check if proposal is still open for voting
        if proposal["status"] != ProposalStatus.VOTING:
            raise ValueError(f"Proposal {proposal_id} is {proposal['status']}, not accepting votes")

        # Check deadline
        deadline = datetime.fromisoformat(proposal["voting_deadline"])
        if datetime.utcnow() > deadline:
            proposal["status"] = ProposalStatus.EXPIRED
            raise ValueError("Voting deadline has passed")

        # Check if agent already voted
        existing_votes = AgentConsensus._votes[proposal_id]
        for existing_vote in existing_votes:
            if existing_vote["agent_id"] == agent_id:
                raise ValueError(f"Agent {agent_id} has already voted")

        # Validate agent exists
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Get agent weight (from metadata or default to 1.0)
        if weight is None:
            weight = agent.metadata.get("voting_weight", 1.0) if agent.metadata else 1.0

        # Create vote record
        vote_record = {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "vote": vote,
            "option": option,
            "ranked_options": ranked_options,
            "weight": weight,
            "reasoning": reasoning,
            "voted_at": datetime.utcnow().isoformat()
        }

        AgentConsensus._votes[proposal_id].append(vote_record)

        # Update vote counts
        if option and option in proposal["vote_counts"]:
            proposal["vote_counts"][option] += 1

        proposal["participation_count"] += 1

        logger.info(
            f"Agent {agent_id} voted {vote} on proposal {proposal_id}"
        )

        return vote_record

    @staticmethod
    def finalize_proposal(
        session: Session,
        proposal_id: int,
        quorum_threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        Finalize a proposal and determine outcome.

        Args:
            session: Database session
            proposal_id: Proposal ID
            quorum_threshold: Minimum participation rate (0.0-1.0)

        Returns:
            Finalized proposal with outcome
        """
        if proposal_id not in AgentConsensus._proposals:
            raise ValueError(f"Proposal {proposal_id} not found")

        proposal = AgentConsensus._proposals[proposal_id]

        if proposal["status"] not in [ProposalStatus.VOTING, ProposalStatus.EXPIRED]:
            raise ValueError(f"Proposal already finalized: {proposal['status']}")

        consensus_type = proposal["consensus_type"]
        votes = AgentConsensus._votes[proposal_id]
        total_eligible = len(proposal["eligible_agents"])

        # Check quorum
        participation_rate = proposal["participation_count"] / total_eligible
        if participation_rate < quorum_threshold:
            proposal["status"] = ProposalStatus.REJECTED
            proposal["finalized_at"] = datetime.utcnow().isoformat()
            proposal["rejection_reason"] = f"Quorum not met: {participation_rate:.1%} < {quorum_threshold:.1%}"

            logger.warning(
                f"Proposal {proposal_id} rejected: quorum not met "
                f"({participation_rate:.1%} < {quorum_threshold:.1%})"
            )

            return proposal

        # Check for vetoes (if veto-based consensus)
        if consensus_type == ConsensusType.VETO_BASED:
            veto_votes = [v for v in votes if v["vote"] == VoteType.VETO]
            if veto_votes:
                proposal["status"] = ProposalStatus.VETOED
                proposal["finalized_at"] = datetime.utcnow().isoformat()
                proposal["vetoed_by"] = [v["agent_id"] for v in veto_votes]

                logger.info(f"Proposal {proposal_id} vetoed by {len(veto_votes)} agent(s)")

                return proposal

        # Determine outcome based on consensus type
        if consensus_type == ConsensusType.SIMPLE_MAJORITY:
            result = AgentConsensus._apply_simple_majority(proposal, votes)
        elif consensus_type == ConsensusType.SUPERMAJORITY:
            result = AgentConsensus._apply_supermajority(proposal, votes)
        elif consensus_type == ConsensusType.UNANIMOUS:
            result = AgentConsensus._apply_unanimous(proposal, votes)
        elif consensus_type == ConsensusType.WEIGHTED_VOTING:
            result = AgentConsensus._apply_weighted_voting(proposal, votes)
        elif consensus_type == ConsensusType.RANKED_CHOICE:
            result = AgentConsensus._apply_ranked_choice(proposal, votes)
        else:  # QUORUM_BASED or default
            result = AgentConsensus._apply_simple_majority(proposal, votes)

        proposal["status"] = result["status"]
        proposal["winning_option"] = result.get("winning_option")
        proposal["finalized_at"] = datetime.utcnow().isoformat()
        proposal["vote_breakdown"] = result.get("breakdown")

        # Add to history
        AgentConsensus._consensus_history.append({
            "proposal_id": proposal_id,
            "title": proposal["title"],
            "consensus_type": consensus_type,
            "status": proposal["status"],
            "winning_option": proposal["winning_option"],
            "participation_rate": participation_rate,
            "finalized_at": proposal["finalized_at"]
        })

        # Keep only last 1000 history entries
        if len(AgentConsensus._consensus_history) > 1000:
            AgentConsensus._consensus_history = AgentConsensus._consensus_history[-1000:]

        logger.info(
            f"Proposal {proposal_id} finalized: {proposal['status']} "
            f"(winning option: {proposal['winning_option']})"
        )

        return proposal

    @staticmethod
    def _apply_simple_majority(proposal: Dict[str, Any], votes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply simple majority (>50%) rule"""
        total_votes = len(votes)

        # Count votes for each option
        option_votes = Counter()
        for vote in votes:
            if vote["option"]:
                option_votes[vote["option"]] += 1

        if not option_votes:
            return {"status": ProposalStatus.REJECTED, "breakdown": {}}

        # Get option with most votes
        winning_option, max_votes = option_votes.most_common(1)[0]

        # Check if it has majority
        if max_votes > total_votes / 2:
            return {
                "status": ProposalStatus.PASSED,
                "winning_option": winning_option,
                "breakdown": dict(option_votes)
            }
        else:
            return {
                "status": ProposalStatus.REJECTED,
                "breakdown": dict(option_votes)
            }

    @staticmethod
    def _apply_supermajority(proposal: Dict[str, Any], votes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply supermajority (>66%) rule"""
        total_votes = len(votes)

        option_votes = Counter()
        for vote in votes:
            if vote["option"]:
                option_votes[vote["option"]] += 1

        if not option_votes:
            return {"status": ProposalStatus.REJECTED, "breakdown": {}}

        winning_option, max_votes = option_votes.most_common(1)[0]

        # Check if it has supermajority (>2/3)
        if max_votes > (total_votes * 2 / 3):
            return {
                "status": ProposalStatus.PASSED,
                "winning_option": winning_option,
                "breakdown": dict(option_votes)
            }
        else:
            return {
                "status": ProposalStatus.REJECTED,
                "breakdown": dict(option_votes)
            }

    @staticmethod
    def _apply_unanimous(proposal: Dict[str, Any], votes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply unanimous (100%) rule"""
        option_votes = Counter()
        for vote in votes:
            if vote["option"]:
                option_votes[vote["option"]] += 1

        if not option_votes:
            return {"status": ProposalStatus.REJECTED, "breakdown": {}}

        # Check if all votes are for the same option
        if len(option_votes) == 1:
            winning_option = list(option_votes.keys())[0]
            return {
                "status": ProposalStatus.PASSED,
                "winning_option": winning_option,
                "breakdown": dict(option_votes)
            }
        else:
            return {
                "status": ProposalStatus.REJECTED,
                "breakdown": dict(option_votes)
            }

    @staticmethod
    def _apply_weighted_voting(proposal: Dict[str, Any], votes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply weighted voting based on agent weights"""
        weighted_votes = {}
        total_weight = 0

        for vote in votes:
            if vote["option"]:
                option = vote["option"]
                weight = vote.get("weight", 1.0)
                weighted_votes[option] = weighted_votes.get(option, 0) + weight
                total_weight += weight

        if not weighted_votes:
            return {"status": ProposalStatus.REJECTED, "breakdown": {}}

        # Find option with highest weighted vote
        winning_option = max(weighted_votes, key=weighted_votes.get)
        winning_weight = weighted_votes[winning_option]

        # Check if it has weighted majority (>50%)
        if winning_weight > total_weight / 2:
            return {
                "status": ProposalStatus.PASSED,
                "winning_option": winning_option,
                "breakdown": weighted_votes
            }
        else:
            return {
                "status": ProposalStatus.REJECTED,
                "breakdown": weighted_votes
            }

    @staticmethod
    def _apply_ranked_choice(proposal: Dict[str, Any], votes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply ranked choice voting (instant runoff)"""
        # Simplified ranked choice: use first choice from each voter
        first_choices = Counter()

        for vote in votes:
            if vote.get("ranked_options"):
                first_choice = vote["ranked_options"][0]
                first_choices[first_choice] += 1

        if not first_choices:
            return {"status": ProposalStatus.REJECTED, "breakdown": {}}

        total_votes = sum(first_choices.values())
        winning_option, max_votes = first_choices.most_common(1)[0]

        # Check if winner has majority
        if max_votes > total_votes / 2:
            return {
                "status": ProposalStatus.PASSED,
                "winning_option": winning_option,
                "breakdown": dict(first_choices)
            }
        else:
            return {
                "status": ProposalStatus.REJECTED,
                "breakdown": dict(first_choices)
            }

    @staticmethod
    def get_proposal(session: Session, proposal_id: int) -> Dict[str, Any]:
        """Get proposal details"""
        if proposal_id not in AgentConsensus._proposals:
            raise ValueError(f"Proposal {proposal_id} not found")

        proposal = AgentConsensus._proposals[proposal_id]
        votes = AgentConsensus._votes[proposal_id]

        return {
            **proposal,
            "total_votes": len(votes),
            "votes": votes
        }

    @staticmethod
    def list_proposals(
        session: Session,
        status: Optional[str] = None,
        agent_id: Optional[int] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        List proposals with optional filtering.

        Args:
            session: Database session
            status: Optional status filter
            agent_id: Optional agent ID filter (proposals they can vote on or proposed)
            limit: Maximum proposals to return

        Returns:
            List of proposals
        """
        filtered_proposals = []

        for proposal in AgentConsensus._proposals.values():
            # Filter by status
            if status and proposal["status"] != status:
                continue

            # Filter by agent eligibility or proposer
            if agent_id:
                if agent_id not in proposal["eligible_agents"] and \
                   proposal["proposer_agent_id"] != agent_id:
                    continue

            filtered_proposals.append(proposal)

            if len(filtered_proposals) >= limit:
                break

        return {
            "total": len(filtered_proposals),
            "proposals": filtered_proposals
        }

    @staticmethod
    def get_agent_votes(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Get all votes cast by an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Agent's voting history
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        agent_votes = []

        for proposal_id, votes in AgentConsensus._votes.items():
            for vote in votes:
                if vote["agent_id"] == agent_id:
                    proposal = AgentConsensus._proposals[proposal_id]
                    agent_votes.append({
                        "proposal_id": proposal_id,
                        "proposal_title": proposal["title"],
                        "vote": vote["vote"],
                        "option": vote["option"],
                        "voted_at": vote["voted_at"],
                        "proposal_status": proposal["status"]
                    })

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "total_votes": len(agent_votes),
            "votes": agent_votes
        }

    @staticmethod
    def get_consensus_statistics(session: Session) -> Dict[str, Any]:
        """
        Get consensus statistics.

        Args:
            session: Database session

        Returns:
            Consensus statistics
        """
        total_proposals = len(AgentConsensus._proposals)

        # Count by status
        status_counts = {}
        for proposal in AgentConsensus._proposals.values():
            status = proposal["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        # Count by consensus type
        type_counts = {}
        for proposal in AgentConsensus._proposals.values():
            consensus_type = proposal["consensus_type"]
            type_counts[consensus_type] = type_counts.get(consensus_type, 0) + 1

        # Calculate pass rate
        passed = status_counts.get(ProposalStatus.PASSED, 0)
        pass_rate = (passed / total_proposals * 100) if total_proposals > 0 else 0

        # Calculate average participation
        participation_rates = []
        for proposal in AgentConsensus._proposals.values():
            if proposal["eligible_agents"]:
                rate = proposal["participation_count"] / len(proposal["eligible_agents"])
                participation_rates.append(rate)

        avg_participation = sum(participation_rates) / len(participation_rates) if participation_rates else 0

        # Total votes cast
        total_votes = sum(len(votes) for votes in AgentConsensus._votes.values())

        return {
            "total_proposals": total_proposals,
            "by_status": status_counts,
            "by_consensus_type": type_counts,
            "pass_rate_percent": pass_rate,
            "avg_participation_rate": avg_participation,
            "total_votes_cast": total_votes,
            "active_proposals": status_counts.get(ProposalStatus.VOTING, 0)
        }

    @staticmethod
    def cancel_proposal(
        session: Session,
        proposal_id: int,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Cancel an active proposal.

        Args:
            session: Database session
            proposal_id: Proposal ID
            reason: Cancellation reason

        Returns:
            Cancelled proposal
        """
        if proposal_id not in AgentConsensus._proposals:
            raise ValueError(f"Proposal {proposal_id} not found")

        proposal = AgentConsensus._proposals[proposal_id]

        if proposal["status"] != ProposalStatus.VOTING:
            raise ValueError(f"Can only cancel voting proposals, this is {proposal['status']}")

        proposal["status"] = ProposalStatus.REJECTED
        proposal["finalized_at"] = datetime.utcnow().isoformat()
        proposal["cancellation_reason"] = reason

        logger.info(f"Proposal {proposal_id} cancelled: {reason}")

        return proposal

    @staticmethod
    def extend_deadline(
        session: Session,
        proposal_id: int,
        additional_minutes: int
    ) -> Dict[str, Any]:
        """
        Extend voting deadline.

        Args:
            session: Database session
            proposal_id: Proposal ID
            additional_minutes: Minutes to add to deadline

        Returns:
            Updated proposal
        """
        if proposal_id not in AgentConsensus._proposals:
            raise ValueError(f"Proposal {proposal_id} not found")

        proposal = AgentConsensus._proposals[proposal_id]

        if proposal["status"] != ProposalStatus.VOTING:
            raise ValueError(f"Can only extend voting proposals, this is {proposal['status']}")

        current_deadline = datetime.fromisoformat(proposal["voting_deadline"])
        new_deadline = current_deadline + timedelta(minutes=additional_minutes)
        proposal["voting_deadline"] = new_deadline.isoformat()

        logger.info(
            f"Extended proposal {proposal_id} deadline by {additional_minutes} minutes"
        )

        return proposal
