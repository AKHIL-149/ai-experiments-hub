"""
Agent Negotiation Service

Enables agents to negotiate agreements on resources, tasks, terms, and collaborations
through structured offer-counteroffer exchanges using various negotiation strategies.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.models.database import Agent
from src.core.logging import logger


class NegotiationType:
    """Negotiation type constants"""
    RESOURCE_ALLOCATION = "resource_allocation"
    TASK_ASSIGNMENT = "task_assignment"
    COLLABORATION_TERMS = "collaboration_terms"
    PRIORITY_ADJUSTMENT = "priority_adjustment"
    DEADLINE_EXTENSION = "deadline_extension"
    COST_SHARING = "cost_sharing"


class NegotiationStatus:
    """Negotiation status constants"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    AGREEMENT_REACHED = "agreement_reached"
    REJECTED = "rejected"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class OfferStatus:
    """Offer status constants"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTERED = "countered"
    WITHDRAWN = "withdrawn"


class NegotiationStrategy:
    """Negotiation strategy constants"""
    COMPETITIVE = "competitive"  # Win-lose, maximize own benefit
    COOPERATIVE = "cooperative"  # Win-win, maximize joint benefit
    COMPROMISE = "compromise"  # Meet in the middle
    ACCOMMODATING = "accommodating"  # Yield to other party
    AVOIDING = "avoiding"  # Withdraw from negotiation


class AgentNegotiation:
    """Service for managing agent-to-agent negotiations"""

    # In-memory storage
    _negotiations: Dict[int, Dict[str, Any]] = {}
    _offers: Dict[int, List[Dict[str, Any]]] = {}  # negotiation_id -> offers
    _negotiation_counter = 0
    _offer_counter = 0

    @staticmethod
    def initiate_negotiation(
        session: Session,
        initiator_agent_id: int,
        respondent_agent_id: int,
        negotiation_type: str,
        subject: str,
        initial_proposal: Dict[str, Any],
        strategy: str = NegotiationStrategy.COOPERATIVE,
        deadline_hours: int = 24,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initiate a negotiation between two agents.

        Args:
            session: Database session
            initiator_agent_id: Agent initiating negotiation
            respondent_agent_id: Agent responding to negotiation
            negotiation_type: Type of negotiation
            subject: Negotiation subject/topic
            initial_proposal: Initial proposal terms
            strategy: Negotiation strategy
            deadline_hours: Negotiation deadline in hours
            metadata: Optional metadata

        Returns:
            Negotiation details
        """
        # Validate agents
        initiator = session.query(Agent).filter(Agent.id == initiator_agent_id).first()
        if not initiator:
            raise ValueError(f"Initiator agent {initiator_agent_id} not found")

        respondent = session.query(Agent).filter(Agent.id == respondent_agent_id).first()
        if not respondent:
            raise ValueError(f"Respondent agent {respondent_agent_id} not found")

        AgentNegotiation._negotiation_counter += 1
        negotiation_id = AgentNegotiation._negotiation_counter

        negotiation = {
            "negotiation_id": negotiation_id,
            "initiator_agent_id": initiator_agent_id,
            "initiator_name": initiator.name,
            "respondent_agent_id": respondent_agent_id,
            "respondent_name": respondent.name,
            "negotiation_type": negotiation_type,
            "subject": subject,
            "strategy": strategy,
            "status": NegotiationStatus.OPEN,
            "initiated_at": datetime.utcnow().isoformat(),
            "deadline": (datetime.utcnow() + timedelta(hours=deadline_hours)).isoformat(),
            "concluded_at": None,
            "final_agreement": None,
            "round_count": 0,
            "metadata": metadata or {}
        }

        AgentNegotiation._negotiations[negotiation_id] = negotiation
        AgentNegotiation._offers[negotiation_id] = []

        # Create initial offer
        AgentNegotiation._offer_counter += 1
        initial_offer = {
            "offer_id": AgentNegotiation._offer_counter,
            "negotiation_id": negotiation_id,
            "from_agent_id": initiator_agent_id,
            "from_agent_name": initiator.name,
            "to_agent_id": respondent_agent_id,
            "round": 1,
            "proposal": initial_proposal,
            "status": OfferStatus.PENDING,
            "created_at": datetime.utcnow().isoformat(),
            "response": None,
            "response_at": None
        }

        AgentNegotiation._offers[negotiation_id].append(initial_offer)
        negotiation["status"] = NegotiationStatus.IN_PROGRESS
        negotiation["round_count"] = 1

        logger.info(
            f"Negotiation {negotiation_id} initiated: {subject} "
            f"between agents {initiator_agent_id} and {respondent_agent_id}"
        )

        return negotiation

    @staticmethod
    def respond_to_offer(
        session: Session,
        negotiation_id: int,
        offer_id: int,
        agent_id: int,
        response: str,
        counter_proposal: Optional[Dict[str, Any]] = None,
        reasoning: str = ""
    ) -> Dict[str, Any]:
        """
        Respond to a negotiation offer.

        Args:
            session: Database session
            negotiation_id: Negotiation ID
            offer_id: Offer ID to respond to
            agent_id: Agent responding
            response: Response (accept/reject/counter)
            counter_proposal: Optional counter-proposal terms
            reasoning: Optional reasoning for response

        Returns:
            Updated negotiation
        """
        if negotiation_id not in AgentNegotiation._negotiations:
            raise ValueError(f"Negotiation {negotiation_id} not found")

        negotiation = AgentNegotiation._negotiations[negotiation_id]

        # Check if negotiation is still active
        if negotiation["status"] not in [NegotiationStatus.OPEN, NegotiationStatus.IN_PROGRESS]:
            raise ValueError(f"Negotiation is {negotiation['status']}, cannot respond")

        # Check deadline
        deadline = datetime.fromisoformat(negotiation["deadline"])
        if datetime.utcnow() > deadline:
            negotiation["status"] = NegotiationStatus.EXPIRED
            raise ValueError("Negotiation deadline passed")

        # Find the offer
        offers = AgentNegotiation._offers[negotiation_id]
        offer = None
        for o in offers:
            if o["offer_id"] == offer_id:
                offer = o
                break

        if not offer:
            raise ValueError(f"Offer {offer_id} not found")

        # Validate agent is the recipient
        if offer["to_agent_id"] != agent_id:
            raise ValueError(f"Agent {agent_id} is not the recipient of this offer")

        # Check if already responded
        if offer["status"] != OfferStatus.PENDING:
            raise ValueError(f"Offer already {offer['status']}")

        # Update offer
        offer["response"] = response
        offer["response_at"] = datetime.utcnow().isoformat()
        offer["reasoning"] = reasoning

        if response == "accept":
            offer["status"] = OfferStatus.ACCEPTED
            negotiation["status"] = NegotiationStatus.AGREEMENT_REACHED
            negotiation["concluded_at"] = datetime.utcnow().isoformat()
            negotiation["final_agreement"] = offer["proposal"]

            logger.info(f"Negotiation {negotiation_id} reached agreement")

        elif response == "reject":
            offer["status"] = OfferStatus.REJECTED
            negotiation["status"] = NegotiationStatus.REJECTED
            negotiation["concluded_at"] = datetime.utcnow().isoformat()

            logger.info(f"Negotiation {negotiation_id} rejected")

        elif response == "counter" and counter_proposal:
            offer["status"] = OfferStatus.COUNTERED

            # Create counter-offer
            AgentNegotiation._offer_counter += 1
            counter_offer = {
                "offer_id": AgentNegotiation._offer_counter,
                "negotiation_id": negotiation_id,
                "from_agent_id": agent_id,
                "from_agent_name": offer["to_agent_id"],  # Will be looked up
                "to_agent_id": offer["from_agent_id"],
                "round": negotiation["round_count"] + 1,
                "proposal": counter_proposal,
                "status": OfferStatus.PENDING,
                "created_at": datetime.utcnow().isoformat(),
                "response": None,
                "response_at": None,
                "in_response_to": offer_id
            }

            AgentNegotiation._offers[negotiation_id].append(counter_offer)
            negotiation["round_count"] += 1

            logger.info(
                f"Counter-offer made in negotiation {negotiation_id}, "
                f"round {negotiation['round_count']}"
            )

        else:
            raise ValueError("Invalid response or missing counter-proposal")

        return negotiation

    @staticmethod
    def withdraw_negotiation(
        session: Session,
        negotiation_id: int,
        agent_id: int,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Withdraw from a negotiation.

        Args:
            session: Database session
            negotiation_id: Negotiation ID
            agent_id: Agent withdrawing
            reason: Withdrawal reason

        Returns:
            Updated negotiation
        """
        if negotiation_id not in AgentNegotiation._negotiations:
            raise ValueError(f"Negotiation {negotiation_id} not found")

        negotiation = AgentNegotiation._negotiations[negotiation_id]

        # Validate agent is part of negotiation
        if agent_id not in [negotiation["initiator_agent_id"], negotiation["respondent_agent_id"]]:
            raise ValueError(f"Agent {agent_id} not part of this negotiation")

        # Check if can be withdrawn
        if negotiation["status"] not in [NegotiationStatus.OPEN, NegotiationStatus.IN_PROGRESS]:
            raise ValueError(f"Cannot withdraw from {negotiation['status']} negotiation")

        negotiation["status"] = NegotiationStatus.WITHDRAWN
        negotiation["concluded_at"] = datetime.utcnow().isoformat()
        negotiation["withdrawal_reason"] = reason
        negotiation["withdrawn_by"] = agent_id

        logger.info(f"Agent {agent_id} withdrew from negotiation {negotiation_id}: {reason}")

        return negotiation

    @staticmethod
    def extend_deadline(
        session: Session,
        negotiation_id: int,
        additional_hours: int
    ) -> Dict[str, Any]:
        """
        Extend negotiation deadline.

        Args:
            session: Database session
            negotiation_id: Negotiation ID
            additional_hours: Hours to add

        Returns:
            Updated negotiation
        """
        if negotiation_id not in AgentNegotiation._negotiations:
            raise ValueError(f"Negotiation {negotiation_id} not found")

        negotiation = AgentNegotiation._negotiations[negotiation_id]

        if negotiation["status"] != NegotiationStatus.IN_PROGRESS:
            raise ValueError(f"Cannot extend deadline for {negotiation['status']} negotiation")

        current_deadline = datetime.fromisoformat(negotiation["deadline"])
        new_deadline = current_deadline + timedelta(hours=additional_hours)
        negotiation["deadline"] = new_deadline.isoformat()

        logger.info(f"Extended negotiation {negotiation_id} deadline by {additional_hours} hours")

        return negotiation

    @staticmethod
    def suggest_compromise(
        session: Session,
        negotiation_id: int
    ) -> Dict[str, Any]:
        """
        Suggest a compromise based on offers.

        Args:
            session: Database session
            negotiation_id: Negotiation ID

        Returns:
            Compromise suggestion
        """
        if negotiation_id not in AgentNegotiation._negotiations:
            raise ValueError(f"Negotiation {negotiation_id} not found")

        negotiation = AgentNegotiation._negotiations[negotiation_id]
        offers = AgentNegotiation._offers[negotiation_id]

        if len(offers) < 2:
            raise ValueError("Need at least 2 offers to suggest compromise")

        # Get latest offers from each party
        initiator_offers = [o for o in offers if o["from_agent_id"] == negotiation["initiator_agent_id"]]
        respondent_offers = [o for o in offers if o["from_agent_id"] == negotiation["respondent_agent_id"]]

        if not initiator_offers or not respondent_offers:
            raise ValueError("Need offers from both parties")

        latest_initiator = initiator_offers[-1]["proposal"]
        latest_respondent = respondent_offers[-1]["proposal"]

        # Simple compromise: average numerical values
        compromise = {}
        for key in latest_initiator:
            if key in latest_respondent:
                val1 = latest_initiator[key]
                val2 = latest_respondent[key]

                # If both are numbers, average them
                if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                    compromise[key] = (val1 + val2) / 2
                else:
                    # For non-numeric, alternate or take first
                    compromise[key] = val1

        return {
            "negotiation_id": negotiation_id,
            "compromise_proposal": compromise,
            "based_on": {
                "initiator_latest": latest_initiator,
                "respondent_latest": latest_respondent
            }
        }

    @staticmethod
    def get_negotiation(
        session: Session,
        negotiation_id: int
    ) -> Dict[str, Any]:
        """Get negotiation details including all offers"""
        if negotiation_id not in AgentNegotiation._negotiations:
            raise ValueError(f"Negotiation {negotiation_id} not found")

        negotiation = AgentNegotiation._negotiations[negotiation_id]
        offers = AgentNegotiation._offers[negotiation_id]

        return {
            **negotiation,
            "offers": offers,
            "total_offers": len(offers)
        }

    @staticmethod
    def list_negotiations(
        session: Session,
        status: Optional[str] = None,
        agent_id: Optional[int] = None,
        negotiation_type: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        List negotiations with optional filtering.

        Args:
            session: Database session
            status: Optional status filter
            agent_id: Optional agent ID filter
            negotiation_type: Optional type filter
            limit: Maximum negotiations to return

        Returns:
            List of negotiations
        """
        filtered_negotiations = []

        for negotiation in AgentNegotiation._negotiations.values():
            # Filter by status
            if status and negotiation["status"] != status:
                continue

            # Filter by agent participation
            if agent_id:
                if agent_id not in [negotiation["initiator_agent_id"], negotiation["respondent_agent_id"]]:
                    continue

            # Filter by type
            if negotiation_type and negotiation["negotiation_type"] != negotiation_type:
                continue

            filtered_negotiations.append(negotiation)

            if len(filtered_negotiations) >= limit:
                break

        return {
            "total": len(filtered_negotiations),
            "negotiations": filtered_negotiations
        }

    @staticmethod
    def get_agent_negotiations(
        session: Session,
        agent_id: int,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get all negotiations for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            status: Optional status filter

        Returns:
            Agent's negotiations
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        return AgentNegotiation.list_negotiations(
            session=session,
            agent_id=agent_id,
            status=status
        )

    @staticmethod
    def get_negotiation_statistics(session: Session) -> Dict[str, Any]:
        """
        Get negotiation statistics.

        Args:
            session: Database session

        Returns:
            Negotiation statistics
        """
        total_negotiations = len(AgentNegotiation._negotiations)

        # Count by status
        status_counts = {}
        for negotiation in AgentNegotiation._negotiations.values():
            status = negotiation["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        # Count by type
        type_counts = {}
        for negotiation in AgentNegotiation._negotiations.values():
            neg_type = negotiation["negotiation_type"]
            type_counts[neg_type] = type_counts.get(neg_type, 0) + 1

        # Calculate success rate
        agreements = status_counts.get(NegotiationStatus.AGREEMENT_REACHED, 0)
        success_rate = (agreements / total_negotiations * 100) if total_negotiations > 0 else 0

        # Calculate average rounds to agreement
        rounds_to_agreement = []
        for negotiation in AgentNegotiation._negotiations.values():
            if negotiation["status"] == NegotiationStatus.AGREEMENT_REACHED:
                rounds_to_agreement.append(negotiation["round_count"])

        avg_rounds = sum(rounds_to_agreement) / len(rounds_to_agreement) if rounds_to_agreement else 0

        # Count total offers
        total_offers = sum(len(offers) for offers in AgentNegotiation._offers.values())

        return {
            "total_negotiations": total_negotiations,
            "by_status": status_counts,
            "by_type": type_counts,
            "success_rate_percent": success_rate,
            "avg_rounds_to_agreement": avg_rounds,
            "total_offers": total_offers,
            "active_negotiations": status_counts.get(NegotiationStatus.IN_PROGRESS, 0)
        }

    @staticmethod
    def get_offer(
        session: Session,
        negotiation_id: int,
        offer_id: int
    ) -> Dict[str, Any]:
        """Get specific offer details"""
        if negotiation_id not in AgentNegotiation._offers:
            raise ValueError(f"Negotiation {negotiation_id} not found")

        offers = AgentNegotiation._offers[negotiation_id]
        for offer in offers:
            if offer["offer_id"] == offer_id:
                return offer

        raise ValueError(f"Offer {offer_id} not found in negotiation {negotiation_id}")
