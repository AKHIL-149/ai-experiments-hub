"""
Agent Reputation Service

Tracks agent reliability, performance, and trustworthiness through reputation scores,
trust metrics, endorsements, and performance history to inform collaboration decisions.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.models import Agent
from src.core.logging import logger


class ReputationCategory:
    """Reputation category constants"""
    TASK_COMPLETION = "task_completion"
    COLLABORATION = "collaboration"
    COMMUNICATION = "communication"
    RELIABILITY = "reliability"
    EXPERTISE = "expertise"
    RESPONSIVENESS = "responsiveness"


class FeedbackType:
    """Feedback type constants"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class TrustLevel:
    """Trust level constants"""
    UNTRUSTED = "untrusted"  # 0-25
    LOW = "low"  # 26-50
    MEDIUM = "medium"  # 51-75
    HIGH = "high"  # 76-90
    VERIFIED = "verified"  # 91-100


class AgentReputation:
    """Service for managing agent reputation and trust"""

    # In-memory storage
    _reputations: Dict[int, Dict[str, Any]] = {}  # agent_id -> reputation
    _trust_relationships: Dict[int, Dict[int, Dict[str, Any]]] = {}  # agent_id -> agent_id -> trust
    _endorsements: Dict[int, List[Dict[str, Any]]] = {}  # agent_id -> endorsements
    _feedback: Dict[int, List[Dict[str, Any]]] = {}  # agent_id -> feedback
    _performance_history: Dict[int, List[Dict[str, Any]]] = {}  # agent_id -> history
    _feedback_counter = 0
    _endorsement_counter = 0

    @staticmethod
    def initialize_reputation(
        session: Session,
        agent_id: int,
        initial_score: float = 50.0
    ) -> Dict[str, Any]:
        """
        Initialize reputation for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            initial_score: Starting reputation score (0-100)

        Returns:
            Reputation details
        """
        # Validate agent
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent_id in AgentReputation._reputations:
            raise ValueError(f"Reputation already initialized for agent {agent_id}")

        reputation = {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "overall_score": initial_score,
            "category_scores": {
                ReputationCategory.TASK_COMPLETION: initial_score,
                ReputationCategory.COLLABORATION: initial_score,
                ReputationCategory.COMMUNICATION: initial_score,
                ReputationCategory.RELIABILITY: initial_score,
                ReputationCategory.EXPERTISE: initial_score,
                ReputationCategory.RESPONSIVENESS: initial_score
            },
            "trust_level": AgentReputation._calculate_trust_level(initial_score),
            "total_endorsements": 0,
            "total_feedback": 0,
            "positive_feedback_count": 0,
            "neutral_feedback_count": 0,
            "negative_feedback_count": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "avg_task_rating": 0.0,
            "collaboration_count": 0,
            "last_updated": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        }

        AgentReputation._reputations[agent_id] = reputation
        AgentReputation._trust_relationships[agent_id] = {}
        AgentReputation._endorsements[agent_id] = []
        AgentReputation._feedback[agent_id] = []
        AgentReputation._performance_history[agent_id] = []

        logger.info(f"Initialized reputation for agent {agent_id} with score {initial_score}")

        return reputation

    @staticmethod
    def update_reputation_score(
        session: Session,
        agent_id: int,
        category: str,
        score_delta: float,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Update agent reputation score in a specific category.

        Args:
            session: Database session
            agent_id: Agent ID
            category: Reputation category
            score_delta: Score change (-100 to +100)
            reason: Optional reason for update

        Returns:
            Updated reputation
        """
        if agent_id not in AgentReputation._reputations:
            raise ValueError(f"Reputation not initialized for agent {agent_id}")

        reputation = AgentReputation._reputations[agent_id]

        # Validate category
        valid_categories = [
            ReputationCategory.TASK_COMPLETION,
            ReputationCategory.COLLABORATION,
            ReputationCategory.COMMUNICATION,
            ReputationCategory.RELIABILITY,
            ReputationCategory.EXPERTISE,
            ReputationCategory.RESPONSIVENESS
        ]
        if category not in valid_categories:
            raise ValueError(f"Invalid category: {category}")

        # Update category score (clamp to 0-100)
        old_score = reputation["category_scores"][category]
        new_score = max(0, min(100, old_score + score_delta))
        reputation["category_scores"][category] = new_score

        # Recalculate overall score (average of all categories)
        category_scores = reputation["category_scores"].values()
        reputation["overall_score"] = sum(category_scores) / len(category_scores)

        # Update trust level
        reputation["trust_level"] = AgentReputation._calculate_trust_level(
            reputation["overall_score"]
        )

        # Record in history
        AgentReputation._performance_history[agent_id].append({
            "timestamp": datetime.utcnow().isoformat(),
            "category": category,
            "score_delta": score_delta,
            "new_score": new_score,
            "reason": reason
        })

        reputation["last_updated"] = datetime.utcnow().isoformat()

        logger.info(
            f"Updated reputation for agent {agent_id}: {category} "
            f"{old_score:.1f} -> {new_score:.1f} (delta: {score_delta:+.1f})"
        )

        return reputation

    @staticmethod
    def record_task_completion(
        session: Session,
        agent_id: int,
        success: bool,
        rating: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Record task completion and update reputation.

        Args:
            session: Database session
            agent_id: Agent ID
            success: Whether task completed successfully
            rating: Optional task rating (0-5)

        Returns:
            Updated reputation
        """
        if agent_id not in AgentReputation._reputations:
            raise ValueError(f"Reputation not initialized for agent {agent_id}")

        reputation = AgentReputation._reputations[agent_id]

        if success:
            reputation["tasks_completed"] += 1
            score_delta = 2.0  # +2 points for successful completion
        else:
            reputation["tasks_failed"] += 1
            score_delta = -3.0  # -3 points for failure

        # Update task completion category
        AgentReputation.update_reputation_score(
            session=session,
            agent_id=agent_id,
            category=ReputationCategory.TASK_COMPLETION,
            score_delta=score_delta,
            reason=f"Task {'completed' if success else 'failed'}"
        )

        # Update average task rating if provided
        if rating is not None:
            if rating < 0 or rating > 5:
                raise ValueError("Rating must be between 0 and 5")

            # Calculate new average
            total_tasks = reputation["tasks_completed"] + reputation["tasks_failed"]
            current_avg = reputation["avg_task_rating"]
            new_avg = ((current_avg * (total_tasks - 1)) + rating) / total_tasks
            reputation["avg_task_rating"] = new_avg

            # Adjust reliability based on rating (3.0 is neutral)
            rating_delta = (rating - 3.0) * 1.5
            AgentReputation.update_reputation_score(
                session=session,
                agent_id=agent_id,
                category=ReputationCategory.RELIABILITY,
                score_delta=rating_delta,
                reason=f"Task rated {rating}/5"
            )

        return reputation

    @staticmethod
    def add_endorsement(
        session: Session,
        agent_id: int,
        endorser_agent_id: int,
        category: str,
        comment: str = ""
    ) -> Dict[str, Any]:
        """
        Add an endorsement from another agent.

        Args:
            session: Database session
            agent_id: Agent being endorsed
            endorser_agent_id: Agent giving endorsement
            category: Category being endorsed
            comment: Optional endorsement comment

        Returns:
            Endorsement details
        """
        if agent_id not in AgentReputation._reputations:
            raise ValueError(f"Reputation not initialized for agent {agent_id}")

        if endorser_agent_id not in AgentReputation._reputations:
            raise ValueError(f"Endorser agent {endorser_agent_id} reputation not initialized")

        # Can't endorse yourself
        if agent_id == endorser_agent_id:
            raise ValueError("Agents cannot endorse themselves")

        # Check if already endorsed recently (within 7 days)
        existing_endorsements = AgentReputation._endorsements[agent_id]
        recent_cutoff = datetime.utcnow() - timedelta(days=7)
        recent_from_endorser = [
            e for e in existing_endorsements
            if e["endorser_agent_id"] == endorser_agent_id
            and datetime.fromisoformat(e["created_at"]) > recent_cutoff
        ]

        if recent_from_endorser:
            raise ValueError("Cannot endorse same agent more than once per week")

        AgentReputation._endorsement_counter += 1
        endorsement = {
            "endorsement_id": AgentReputation._endorsement_counter,
            "agent_id": agent_id,
            "endorser_agent_id": endorser_agent_id,
            "endorser_name": AgentReputation._reputations[endorser_agent_id]["agent_name"],
            "category": category,
            "comment": comment,
            "created_at": datetime.utcnow().isoformat()
        }

        AgentReputation._endorsements[agent_id].append(endorsement)

        # Update reputation
        reputation = AgentReputation._reputations[agent_id]
        reputation["total_endorsements"] += 1

        # Endorsement value depends on endorser's reputation
        endorser_score = AgentReputation._reputations[endorser_agent_id]["overall_score"]
        endorsement_value = (endorser_score / 100) * 3.0  # Max +3 from high-reputation endorser

        AgentReputation.update_reputation_score(
            session=session,
            agent_id=agent_id,
            category=category,
            score_delta=endorsement_value,
            reason=f"Endorsed by agent {endorser_agent_id}"
        )

        logger.info(f"Agent {endorser_agent_id} endorsed agent {agent_id} in {category}")

        return endorsement

    @staticmethod
    def add_feedback(
        session: Session,
        agent_id: int,
        from_agent_id: int,
        feedback_type: str,
        category: str,
        comment: str = ""
    ) -> Dict[str, Any]:
        """
        Add feedback from another agent.

        Args:
            session: Database session
            agent_id: Agent receiving feedback
            from_agent_id: Agent giving feedback
            feedback_type: Type of feedback (positive/neutral/negative)
            category: Category of feedback
            comment: Optional feedback comment

        Returns:
            Feedback details
        """
        if agent_id not in AgentReputation._reputations:
            raise ValueError(f"Reputation not initialized for agent {agent_id}")

        if from_agent_id not in AgentReputation._reputations:
            raise ValueError(f"Feedback agent {from_agent_id} reputation not initialized")

        # Validate feedback type
        valid_types = [FeedbackType.POSITIVE, FeedbackType.NEUTRAL, FeedbackType.NEGATIVE]
        if feedback_type not in valid_types:
            raise ValueError(f"Invalid feedback type: {feedback_type}")

        AgentReputation._feedback_counter += 1
        feedback = {
            "feedback_id": AgentReputation._feedback_counter,
            "agent_id": agent_id,
            "from_agent_id": from_agent_id,
            "from_agent_name": AgentReputation._reputations[from_agent_id]["agent_name"],
            "feedback_type": feedback_type,
            "category": category,
            "comment": comment,
            "created_at": datetime.utcnow().isoformat()
        }

        AgentReputation._feedback[agent_id].append(feedback)

        # Update feedback counts
        reputation = AgentReputation._reputations[agent_id]
        reputation["total_feedback"] += 1

        if feedback_type == FeedbackType.POSITIVE:
            reputation["positive_feedback_count"] += 1
            score_delta = 1.5
        elif feedback_type == FeedbackType.NEGATIVE:
            reputation["negative_feedback_count"] += 1
            score_delta = -2.0
        else:  # NEUTRAL
            reputation["neutral_feedback_count"] += 1
            score_delta = 0.0

        if score_delta != 0:
            AgentReputation.update_reputation_score(
                session=session,
                agent_id=agent_id,
                category=category,
                score_delta=score_delta,
                reason=f"{feedback_type} feedback from agent {from_agent_id}"
            )

        logger.info(f"Agent {from_agent_id} gave {feedback_type} feedback to agent {agent_id}")

        return feedback

    @staticmethod
    def establish_trust(
        session: Session,
        agent_id: int,
        trusted_agent_id: int,
        trust_score: float,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Establish or update trust relationship between agents.

        Args:
            session: Database session
            agent_id: Agent establishing trust
            trusted_agent_id: Agent being trusted
            trust_score: Trust score (0-100)
            reason: Optional reason

        Returns:
            Trust relationship details
        """
        if agent_id not in AgentReputation._reputations:
            raise ValueError(f"Reputation not initialized for agent {agent_id}")

        if trusted_agent_id not in AgentReputation._reputations:
            raise ValueError(f"Reputation not initialized for trusted agent {trusted_agent_id}")

        if agent_id == trusted_agent_id:
            raise ValueError("Agents cannot establish trust with themselves")

        if trust_score < 0 or trust_score > 100:
            raise ValueError("Trust score must be between 0 and 100")

        trust_relationship = {
            "agent_id": agent_id,
            "trusted_agent_id": trusted_agent_id,
            "trusted_agent_name": AgentReputation._reputations[trusted_agent_id]["agent_name"],
            "trust_score": trust_score,
            "trust_level": AgentReputation._calculate_trust_level(trust_score),
            "reason": reason,
            "established_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat()
        }

        AgentReputation._trust_relationships[agent_id][trusted_agent_id] = trust_relationship

        logger.info(
            f"Agent {agent_id} established trust with agent {trusted_agent_id}: "
            f"{trust_score:.1f} ({trust_relationship['trust_level']})"
        )

        return trust_relationship

    @staticmethod
    def apply_reputation_decay(
        session: Session,
        agent_id: int,
        decay_factor: float = 0.01
    ) -> Dict[str, Any]:
        """
        Apply time-based reputation decay.

        Args:
            session: Database session
            agent_id: Agent ID
            decay_factor: Decay percentage (0-1)

        Returns:
            Updated reputation
        """
        if agent_id not in AgentReputation._reputations:
            raise ValueError(f"Reputation not initialized for agent {agent_id}")

        reputation = AgentReputation._reputations[agent_id]

        # Apply decay to all categories (move toward 50 - neutral)
        for category in reputation["category_scores"]:
            current_score = reputation["category_scores"][category]
            # Decay pulls score toward 50
            decay = (50 - current_score) * decay_factor
            new_score = current_score + decay
            reputation["category_scores"][category] = new_score

        # Recalculate overall score
        category_scores = reputation["category_scores"].values()
        reputation["overall_score"] = sum(category_scores) / len(category_scores)

        # Update trust level
        reputation["trust_level"] = AgentReputation._calculate_trust_level(
            reputation["overall_score"]
        )

        reputation["last_updated"] = datetime.utcnow().isoformat()

        logger.info(f"Applied reputation decay to agent {agent_id} (factor: {decay_factor})")

        return reputation

    @staticmethod
    def get_reputation(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """Get agent reputation details"""
        if agent_id not in AgentReputation._reputations:
            raise ValueError(f"Reputation not initialized for agent {agent_id}")

        reputation = AgentReputation._reputations[agent_id]
        endorsements = AgentReputation._endorsements.get(agent_id, [])
        feedback = AgentReputation._feedback.get(agent_id, [])

        return {
            **reputation,
            "recent_endorsements": endorsements[-5:] if endorsements else [],
            "recent_feedback": feedback[-5:] if feedback else []
        }

    @staticmethod
    def get_trust_relationships(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """Get agent's trust relationships"""
        if agent_id not in AgentReputation._reputations:
            raise ValueError(f"Reputation not initialized for agent {agent_id}")

        trust_relationships = AgentReputation._trust_relationships.get(agent_id, {})

        return {
            "agent_id": agent_id,
            "total_relationships": len(trust_relationships),
            "relationships": list(trust_relationships.values())
        }

    @staticmethod
    def get_top_agents(
        session: Session,
        limit: int = 10,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get top-rated agents.

        Args:
            session: Database session
            limit: Maximum agents to return
            category: Optional category to rank by

        Returns:
            Top agents list
        """
        agents = []

        for agent_id, reputation in AgentReputation._reputations.items():
            if category:
                score = reputation["category_scores"].get(category, 0)
            else:
                score = reputation["overall_score"]

            agents.append({
                "agent_id": agent_id,
                "agent_name": reputation["agent_name"],
                "score": score,
                "trust_level": reputation["trust_level"],
                "tasks_completed": reputation["tasks_completed"],
                "avg_task_rating": reputation["avg_task_rating"]
            })

        # Sort by score descending
        agents.sort(key=lambda x: x["score"], reverse=True)

        return {
            "category": category or "overall",
            "total_agents": len(agents),
            "top_agents": agents[:limit]
        }

    @staticmethod
    def get_reputation_statistics(session: Session) -> Dict[str, Any]:
        """
        Get reputation system statistics.

        Args:
            session: Database session

        Returns:
            Reputation statistics
        """
        total_agents = len(AgentReputation._reputations)

        if total_agents == 0:
            return {
                "total_agents": 0,
                "avg_overall_score": 0.0,
                "total_endorsements": 0,
                "total_feedback": 0,
                "total_trust_relationships": 0
            }

        # Calculate averages
        total_score = sum(r["overall_score"] for r in AgentReputation._reputations.values())
        avg_score = total_score / total_agents

        total_endorsements = sum(
            len(endorsements) for endorsements in AgentReputation._endorsements.values()
        )

        total_feedback = sum(
            len(feedback) for feedback in AgentReputation._feedback.values()
        )

        total_trust = sum(
            len(trust) for trust in AgentReputation._trust_relationships.values()
        )

        # Count by trust level
        trust_level_counts = {}
        for reputation in AgentReputation._reputations.values():
            level = reputation["trust_level"]
            trust_level_counts[level] = trust_level_counts.get(level, 0) + 1

        # Category averages
        category_averages = {}
        for category in [
            ReputationCategory.TASK_COMPLETION,
            ReputationCategory.COLLABORATION,
            ReputationCategory.COMMUNICATION,
            ReputationCategory.RELIABILITY,
            ReputationCategory.EXPERTISE,
            ReputationCategory.RESPONSIVENESS
        ]:
            total = sum(
                r["category_scores"][category]
                for r in AgentReputation._reputations.values()
            )
            category_averages[category] = total / total_agents

        return {
            "total_agents": total_agents,
            "avg_overall_score": avg_score,
            "total_endorsements": total_endorsements,
            "total_feedback": total_feedback,
            "total_trust_relationships": total_trust,
            "by_trust_level": trust_level_counts,
            "category_averages": category_averages
        }

    @staticmethod
    def _calculate_trust_level(score: float) -> str:
        """Calculate trust level from score"""
        if score >= 91:
            return TrustLevel.VERIFIED
        elif score >= 76:
            return TrustLevel.HIGH
        elif score >= 51:
            return TrustLevel.MEDIUM
        elif score >= 26:
            return TrustLevel.LOW
        else:
            return TrustLevel.UNTRUSTED
