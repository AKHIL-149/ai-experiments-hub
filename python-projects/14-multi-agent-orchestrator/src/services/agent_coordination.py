"""
Agent Coordination Engine Service

High-level orchestration layer that integrates all multi-agent coordination
features including consensus, coalitions, negotiations, trust, contracts, and auctions.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict


class CoordinationStrategy:
    """Coordination strategy types"""
    HIERARCHICAL = "hierarchical"
    DEMOCRATIC = "democratic"
    MARKET_BASED = "market_based"
    TRUST_BASED = "trust_based"
    HYBRID = "hybrid"


class CoordinationStatus:
    """Coordination session statuses"""
    INITIATED = "initiated"
    FORMING_COALITION = "forming_coalition"
    NEGOTIATING = "negotiating"
    VOTING = "voting"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentCoordination:
    """
    Agent Coordination Engine

    Provides high-level coordination workflows that integrate:
    - Consensus mechanisms
    - Coalition formation
    - Negotiations
    - Trust relationships
    - Contracts
    - Auctions
    - Conflict resolution
    """

    # In-memory storage
    _coordination_sessions = {}
    _session_counter = 0
    _coordination_history = []
    _agent_participation = defaultdict(list)

    @staticmethod
    def _generate_session_id() -> str:
        """Generate unique session ID"""
        AgentCoordination._session_counter += 1
        return f"coord_{AgentCoordination._session_counter}"

    @staticmethod
    def initiate_coordination(
        session,
        initiator_agent_id: int,
        coordination_type: str,
        goal_description: str,
        strategy: str = CoordinationStrategy.HYBRID,
        required_agents: Optional[List[int]] = None,
        min_agents: int = 2,
        max_agents: Optional[int] = None,
        constraints: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Initiate a coordination session.

        Creates a new coordination session that can orchestrate multiple
        agents working together using various coordination mechanisms.
        """
        session_id = AgentCoordination._generate_session_id()

        coordination_session = {
            "id": session_id,
            "initiator_agent_id": initiator_agent_id,
            "coordination_type": coordination_type,
            "goal_description": goal_description,
            "strategy": strategy,
            "required_agents": required_agents or [],
            "min_agents": min_agents,
            "max_agents": max_agents,
            "constraints": constraints or {},
            "metadata": metadata or {},
            "status": CoordinationStatus.INITIATED,
            "participating_agents": [initiator_agent_id],
            "coalition_id": None,
            "negotiation_ids": [],
            "contract_ids": [],
            "auction_id": None,
            "consensus_votes": {},
            "outcomes": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "completed_at": None
        }

        AgentCoordination._coordination_sessions[session_id] = coordination_session
        AgentCoordination._agent_participation[initiator_agent_id].append(session_id)

        return coordination_session

    @staticmethod
    def join_coordination(
        session,
        session_id: str,
        agent_id: int,
        capabilities: Optional[List[str]] = None,
        commitment_level: float = 1.0,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Agent joins a coordination session.

        Adds agent to the coordination session, potentially triggering
        coalition formation or contract negotiation.
        """
        if session_id not in AgentCoordination._coordination_sessions:
            raise ValueError(f"Coordination session {session_id} not found")

        coordination_session = AgentCoordination._coordination_sessions[session_id]

        if coordination_session["status"] not in [CoordinationStatus.INITIATED, CoordinationStatus.FORMING_COALITION]:
            raise ValueError(f"Cannot join coordination session in status {coordination_session['status']}")

        if agent_id in coordination_session["participating_agents"]:
            raise ValueError(f"Agent {agent_id} already participating")

        # Check if max_agents exceeded
        if coordination_session["max_agents"] and len(coordination_session["participating_agents"]) >= coordination_session["max_agents"]:
            raise ValueError("Maximum number of agents reached")

        coordination_session["participating_agents"].append(agent_id)

        # Record participation
        participation = {
            "agent_id": agent_id,
            "joined_at": datetime.utcnow().isoformat(),
            "capabilities": capabilities or [],
            "commitment_level": commitment_level,
            "metadata": metadata or {}
        }

        if "participations" not in coordination_session:
            coordination_session["participations"] = []
        coordination_session["participations"].append(participation)

        AgentCoordination._agent_participation[agent_id].append(session_id)

        # Check if minimum agents reached
        if len(coordination_session["participating_agents"]) >= coordination_session["min_agents"]:
            coordination_session["status"] = CoordinationStatus.FORMING_COALITION

        coordination_session["updated_at"] = datetime.utcnow().isoformat()

        return coordination_session

    @staticmethod
    def start_negotiation_phase(
        session,
        session_id: str,
        negotiation_topics: List[dict],
        timeout_minutes: int = 60
    ) -> dict:
        """
        Start negotiation phase for coordination.

        Moves session to negotiating status and creates negotiation
        sessions for key topics.
        """
        if session_id not in AgentCoordination._coordination_sessions:
            raise ValueError(f"Coordination session {session_id} not found")

        coordination_session = AgentCoordination._coordination_sessions[session_id]

        if coordination_session["status"] not in [CoordinationStatus.FORMING_COALITION, CoordinationStatus.INITIATED]:
            raise ValueError(f"Cannot start negotiation from status {coordination_session['status']}")

        coordination_session["status"] = CoordinationStatus.NEGOTIATING
        coordination_session["negotiation_topics"] = negotiation_topics
        coordination_session["negotiation_timeout"] = (datetime.utcnow() + timedelta(minutes=timeout_minutes)).isoformat()
        coordination_session["updated_at"] = datetime.utcnow().isoformat()

        return coordination_session

    @staticmethod
    def propose_consensus_vote(
        session,
        session_id: str,
        proposal_id: str,
        proposal_description: str,
        voting_type: str = "majority",
        required_threshold: float = 0.5
    ) -> dict:
        """
        Propose a consensus vote for the coordination.

        Creates a voting mechanism for agents to reach consensus
        on key decisions.
        """
        if session_id not in AgentCoordination._coordination_sessions:
            raise ValueError(f"Coordination session {session_id} not found")

        coordination_session = AgentCoordination._coordination_sessions[session_id]

        vote = {
            "proposal_id": proposal_id,
            "description": proposal_description,
            "voting_type": voting_type,
            "required_threshold": required_threshold,
            "votes": {},
            "status": "open",
            "created_at": datetime.utcnow().isoformat()
        }

        coordination_session["consensus_votes"][proposal_id] = vote
        coordination_session["status"] = CoordinationStatus.VOTING
        coordination_session["updated_at"] = datetime.utcnow().isoformat()

        return vote

    @staticmethod
    def cast_vote(
        session,
        session_id: str,
        proposal_id: str,
        agent_id: int,
        vote: bool,
        weight: float = 1.0,
        rationale: Optional[str] = None
    ) -> dict:
        """
        Agent casts vote on a proposal.

        Records vote and checks if consensus threshold is reached.
        """
        if session_id not in AgentCoordination._coordination_sessions:
            raise ValueError(f"Coordination session {session_id} not found")

        coordination_session = AgentCoordination._coordination_sessions[session_id]

        if proposal_id not in coordination_session["consensus_votes"]:
            raise ValueError(f"Proposal {proposal_id} not found")

        if agent_id not in coordination_session["participating_agents"]:
            raise ValueError(f"Agent {agent_id} not participating in this coordination")

        vote_record = coordination_session["consensus_votes"][proposal_id]

        if vote_record["status"] != "open":
            raise ValueError(f"Voting is {vote_record['status']}")

        # Record vote
        vote_record["votes"][agent_id] = {
            "vote": vote,
            "weight": weight,
            "rationale": rationale,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Check if all agents have voted
        if len(vote_record["votes"]) == len(coordination_session["participating_agents"]):
            # Calculate result
            total_weight = sum(v["weight"] for v in vote_record["votes"].values())
            positive_weight = sum(v["weight"] for v in vote_record["votes"].values() if v["vote"])

            threshold = vote_record["required_threshold"]
            consensus_reached = (positive_weight / total_weight) >= threshold

            vote_record["status"] = "passed" if consensus_reached else "failed"
            vote_record["result"] = {
                "consensus_reached": consensus_reached,
                "positive_votes": positive_weight,
                "total_votes": total_weight,
                "percentage": positive_weight / total_weight,
                "closed_at": datetime.utcnow().isoformat()
            }

        coordination_session["updated_at"] = datetime.utcnow().isoformat()

        return vote_record

    @staticmethod
    def create_coordination_contract(
        session,
        session_id: str,
        contract_terms: dict,
        sla_terms: Optional[dict] = None,
        duration_hours: int = 24
    ) -> dict:
        """
        Create contracts between coordinating agents.

        Establishes formal agreements for the coordination work.
        """
        if session_id not in AgentCoordination._coordination_sessions:
            raise ValueError(f"Coordination session {session_id} not found")

        coordination_session = AgentCoordination._coordination_sessions[session_id]

        contract_id = f"contract_{session_id}_{len(coordination_session['contract_ids']) + 1}"

        contract = {
            "contract_id": contract_id,
            "session_id": session_id,
            "terms": contract_terms,
            "sla_terms": sla_terms or {},
            "parties": coordination_session["participating_agents"],
            "duration_hours": duration_hours,
            "created_at": datetime.utcnow().isoformat(),
            "status": "proposed"
        }

        coordination_session["contract_ids"].append(contract_id)
        coordination_session["updated_at"] = datetime.utcnow().isoformat()

        return contract

    @staticmethod
    def start_execution_phase(
        session,
        session_id: str,
        execution_plan: dict,
        monitoring_interval: int = 60
    ) -> dict:
        """
        Start execution phase of coordination.

        Moves to executing status and begins coordinated work.
        """
        if session_id not in AgentCoordination._coordination_sessions:
            raise ValueError(f"Coordination session {session_id} not found")

        coordination_session = AgentCoordination._coordination_sessions[session_id]

        if coordination_session["status"] not in [CoordinationStatus.VOTING, CoordinationStatus.NEGOTIATING]:
            raise ValueError(f"Cannot start execution from status {coordination_session['status']}")

        coordination_session["status"] = CoordinationStatus.EXECUTING
        coordination_session["execution_plan"] = execution_plan
        coordination_session["execution_started_at"] = datetime.utcnow().isoformat()
        coordination_session["monitoring_interval"] = monitoring_interval
        coordination_session["updated_at"] = datetime.utcnow().isoformat()

        return coordination_session

    @staticmethod
    def record_coordination_outcome(
        session,
        session_id: str,
        agent_id: int,
        outcome_type: str,
        outcome_data: dict,
        success: bool = True
    ) -> dict:
        """
        Record outcome from coordinating agent.

        Tracks individual agent contributions and results.
        """
        if session_id not in AgentCoordination._coordination_sessions:
            raise ValueError(f"Coordination session {session_id} not found")

        coordination_session = AgentCoordination._coordination_sessions[session_id]

        if agent_id not in coordination_session["participating_agents"]:
            raise ValueError(f"Agent {agent_id} not participating")

        outcome = {
            "agent_id": agent_id,
            "outcome_type": outcome_type,
            "outcome_data": outcome_data,
            "success": success,
            "timestamp": datetime.utcnow().isoformat()
        }

        coordination_session["outcomes"].append(outcome)
        coordination_session["updated_at"] = datetime.utcnow().isoformat()

        return outcome

    @staticmethod
    def complete_coordination(
        session,
        session_id: str,
        final_result: dict,
        success: bool = True
    ) -> dict:
        """
        Complete coordination session.

        Finalizes the coordination, records results, and updates
        agent statistics.
        """
        if session_id not in AgentCoordination._coordination_sessions:
            raise ValueError(f"Coordination session {session_id} not found")

        coordination_session = AgentCoordination._coordination_sessions[session_id]

        coordination_session["status"] = CoordinationStatus.COMPLETED if success else CoordinationStatus.FAILED
        coordination_session["final_result"] = final_result
        coordination_session["success"] = success
        coordination_session["completed_at"] = datetime.utcnow().isoformat()
        coordination_session["updated_at"] = datetime.utcnow().isoformat()

        # Calculate duration
        started = datetime.fromisoformat(coordination_session["created_at"])
        completed = datetime.fromisoformat(coordination_session["completed_at"])
        duration = (completed - started).total_seconds()
        coordination_session["duration_seconds"] = duration

        # Record in history
        AgentCoordination._coordination_history.append({
            "session_id": session_id,
            "initiator_agent_id": coordination_session["initiator_agent_id"],
            "participating_agents": coordination_session["participating_agents"],
            "coordination_type": coordination_session["coordination_type"],
            "strategy": coordination_session["strategy"],
            "success": success,
            "duration_seconds": duration,
            "completed_at": coordination_session["completed_at"]
        })

        return coordination_session

    @staticmethod
    def cancel_coordination(
        session,
        session_id: str,
        cancelling_agent_id: int,
        reason: str
    ) -> dict:
        """
        Cancel coordination session.

        Allows initiator or participating agents to cancel coordination.
        """
        if session_id not in AgentCoordination._coordination_sessions:
            raise ValueError(f"Coordination session {session_id} not found")

        coordination_session = AgentCoordination._coordination_sessions[session_id]

        if cancelling_agent_id not in coordination_session["participating_agents"]:
            raise ValueError(f"Agent {cancelling_agent_id} not participating")

        coordination_session["status"] = CoordinationStatus.CANCELLED
        coordination_session["cancelled_by"] = cancelling_agent_id
        coordination_session["cancellation_reason"] = reason
        coordination_session["cancelled_at"] = datetime.utcnow().isoformat()
        coordination_session["updated_at"] = datetime.utcnow().isoformat()

        return coordination_session

    @staticmethod
    def get_coordination_session(
        session,
        session_id: str
    ) -> dict:
        """Get coordination session details."""
        if session_id not in AgentCoordination._coordination_sessions:
            raise ValueError(f"Coordination session {session_id} not found")

        return AgentCoordination._coordination_sessions[session_id]

    @staticmethod
    def list_coordination_sessions(
        session,
        status: Optional[str] = None,
        strategy: Optional[str] = None,
        agent_id: Optional[int] = None,
        coordination_type: Optional[str] = None
    ) -> dict:
        """
        List coordination sessions with filtering.

        Returns sessions matching the filter criteria.
        """
        sessions = list(AgentCoordination._coordination_sessions.values())

        # Apply filters
        if status:
            sessions = [s for s in sessions if s["status"] == status]

        if strategy:
            sessions = [s for s in sessions if s["strategy"] == strategy]

        if agent_id:
            sessions = [s for s in sessions if agent_id in s["participating_agents"]]

        if coordination_type:
            sessions = [s for s in sessions if s["coordination_type"] == coordination_type]

        return {
            "sessions": sessions,
            "total": len(sessions)
        }

    @staticmethod
    def get_agent_coordination_history(
        session,
        agent_id: int,
        limit: int = 10
    ) -> dict:
        """
        Get agent's coordination history.

        Returns all coordination sessions the agent participated in.
        """
        session_ids = AgentCoordination._agent_participation.get(agent_id, [])

        sessions = []
        for session_id in session_ids[-limit:]:
            if session_id in AgentCoordination._coordination_sessions:
                sessions.append(AgentCoordination._coordination_sessions[session_id])

        # Calculate statistics
        total_sessions = len(session_ids)
        completed_sessions = sum(1 for s in sessions if s["status"] == CoordinationStatus.COMPLETED)
        success_rate = completed_sessions / total_sessions if total_sessions > 0 else 0

        return {
            "agent_id": agent_id,
            "total_coordinations": total_sessions,
            "completed_coordinations": completed_sessions,
            "success_rate": success_rate,
            "recent_sessions": sessions,
            "session_ids": session_ids
        }

    @staticmethod
    def get_coordination_statistics(session) -> dict:
        """
        Get coordination system statistics.

        Returns aggregate metrics about coordination sessions.
        """
        all_sessions = list(AgentCoordination._coordination_sessions.values())

        # Status distribution
        status_dist = defaultdict(int)
        for s in all_sessions:
            status_dist[s["status"]] += 1

        # Strategy distribution
        strategy_dist = defaultdict(int)
        for s in all_sessions:
            strategy_dist[s["strategy"]] += 1

        # Type distribution
        type_dist = defaultdict(int)
        for s in all_sessions:
            type_dist[s["coordination_type"]] += 1

        # Calculate success metrics
        completed = [s for s in all_sessions if s["status"] == CoordinationStatus.COMPLETED]
        successful = [s for s in completed if s.get("success", False)]

        # Average duration
        durations = [s.get("duration_seconds", 0) for s in completed]
        avg_duration = sum(durations) / len(durations) if durations else 0

        # Average participation
        participations = [len(s["participating_agents"]) for s in all_sessions]
        avg_agents = sum(participations) / len(participations) if participations else 0

        return {
            "total_sessions": len(all_sessions),
            "status_distribution": dict(status_dist),
            "strategy_distribution": dict(strategy_dist),
            "type_distribution": dict(type_dist),
            "completed_sessions": len(completed),
            "successful_sessions": len(successful),
            "success_rate": len(successful) / len(completed) if completed else 0,
            "average_duration_seconds": avg_duration,
            "average_participating_agents": avg_agents,
            "total_unique_agents": len(AgentCoordination._agent_participation)
        }
