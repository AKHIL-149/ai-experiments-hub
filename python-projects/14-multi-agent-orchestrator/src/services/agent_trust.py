"""
Agent Trust System Service

Manages trust relationships, scores, recommendations, and verification
between agents for secure multi-agent collaboration.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import statistics


class TrustLevel:
    """Trust levels"""
    UNKNOWN = "unknown"
    UNTRUSTED = "untrusted"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"


class RecommendationType:
    """Recommendation types"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class VerificationStatus:
    """Verification statuses"""
    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class AgentTrust:
    """
    Agent Trust System

    Manages trust relationships, scores, recommendations, and verification
    to enable secure multi-agent collaboration.
    """

    # In-memory storage
    _trust_relationships = {}  # (agent_a, agent_b) -> relationship
    _relationship_counter = 0

    _trust_scores = defaultdict(lambda: defaultdict(float))  # agent_a -> {agent_b: score}
    _global_trust_scores = defaultdict(float)  # agent_id -> global_score

    _recommendations = []
    _recommendation_counter = 0

    _verifications = {}
    _verification_counter = 0

    _trust_history = defaultdict(list)  # (agent_a, agent_b) -> [history]

    @staticmethod
    def establish_trust(
        session,
        agent_a_id: int,
        agent_b_id: int,
        initial_score: float = 0.5,
        trust_level: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Establish trust relationship between agents.

        Args:
            session: Database session
            agent_a_id: First agent ID
            agent_b_id: Second agent ID
            initial_score: Initial trust score (0-1)
            trust_level: Trust level classification
            metadata: Additional metadata

        Returns:
            Trust relationship
        """
        if agent_a_id == agent_b_id:
            raise ValueError("Agent cannot establish trust with itself")

        if not 0 <= initial_score <= 1:
            raise ValueError("Trust score must be between 0 and 1")

        AgentTrust._relationship_counter += 1
        relationship_id = f"trust_{AgentTrust._relationship_counter}"

        # Determine trust level from score if not provided
        if not trust_level:
            trust_level = AgentTrust._score_to_level(initial_score)

        relationship = {
            "id": relationship_id,
            "agent_a_id": agent_a_id,
            "agent_b_id": agent_b_id,
            "trust_score": initial_score,
            "trust_level": trust_level,
            "established_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
            "interaction_count": 0,
            "successful_interactions": 0,
            "failed_interactions": 0,
            "metadata": metadata or {},
            "is_mutual": False
        }

        # Store bidirectional
        key = (min(agent_a_id, agent_b_id), max(agent_a_id, agent_b_id))
        AgentTrust._trust_relationships[key] = relationship

        # Update trust scores
        AgentTrust._trust_scores[agent_a_id][agent_b_id] = initial_score
        AgentTrust._trust_scores[agent_b_id][agent_a_id] = initial_score

        # Record in history
        AgentTrust._trust_history[key].append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": "established",
            "score": initial_score,
            "level": trust_level
        })

        return relationship

    @staticmethod
    def update_trust_score(
        session,
        agent_a_id: int,
        agent_b_id: int,
        new_score: Optional[float] = None,
        adjustment: Optional[float] = None,
        reason: Optional[str] = None
    ) -> dict:
        """
        Update trust score between agents.

        Args:
            session: Database session
            agent_a_id: First agent ID
            agent_b_id: Second agent ID
            new_score: New absolute score
            adjustment: Score adjustment (+/-)
            reason: Reason for update

        Returns:
            Updated relationship
        """
        key = (min(agent_a_id, agent_b_id), max(agent_a_id, agent_b_id))

        if key not in AgentTrust._trust_relationships:
            raise ValueError(f"No trust relationship between agents {agent_a_id} and {agent_b_id}")

        relationship = AgentTrust._trust_relationships[key]

        old_score = relationship["trust_score"]

        # Calculate new score
        if new_score is not None:
            if not 0 <= new_score <= 1:
                raise ValueError("Trust score must be between 0 and 1")
            relationship["trust_score"] = new_score
        elif adjustment is not None:
            relationship["trust_score"] = max(0, min(1, old_score + adjustment))
        else:
            raise ValueError("Must provide either new_score or adjustment")

        # Update trust level
        relationship["trust_level"] = AgentTrust._score_to_level(relationship["trust_score"])
        relationship["last_updated"] = datetime.utcnow().isoformat()

        # Update bidirectional scores
        AgentTrust._trust_scores[agent_a_id][agent_b_id] = relationship["trust_score"]
        AgentTrust._trust_scores[agent_b_id][agent_a_id] = relationship["trust_score"]

        # Record in history
        AgentTrust._trust_history[key].append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": "score_updated",
            "old_score": old_score,
            "new_score": relationship["trust_score"],
            "adjustment": adjustment,
            "reason": reason
        })

        # Update global trust scores
        AgentTrust._recalculate_global_trust(agent_a_id)
        AgentTrust._recalculate_global_trust(agent_b_id)

        return relationship

    @staticmethod
    def record_interaction(
        session,
        agent_a_id: int,
        agent_b_id: int,
        success: bool,
        interaction_type: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record interaction between agents and adjust trust.

        Args:
            session: Database session
            agent_a_id: First agent ID
            agent_b_id: Second agent ID
            success: Whether interaction was successful
            interaction_type: Type of interaction
            metadata: Interaction metadata

        Returns:
            Updated relationship
        """
        key = (min(agent_a_id, agent_b_id), max(agent_a_id, agent_b_id))

        if key not in AgentTrust._trust_relationships:
            # Auto-establish if doesn't exist
            AgentTrust.establish_trust(session, agent_a_id, agent_b_id)

        relationship = AgentTrust._trust_relationships[key]

        # Update interaction counts
        relationship["interaction_count"] += 1
        if success:
            relationship["successful_interactions"] += 1
        else:
            relationship["failed_interactions"] += 1

        # Calculate trust adjustment
        success_rate = relationship["successful_interactions"] / relationship["interaction_count"]

        # Adjust trust based on interaction outcome
        if success:
            adjustment = 0.05 * (1 - relationship["trust_score"])  # Smaller gains when already high
        else:
            adjustment = -0.1 * relationship["trust_score"]  # Larger losses when trust is high

        # Apply adjustment
        AgentTrust.update_trust_score(
            session=session,
            agent_a_id=agent_a_id,
            agent_b_id=agent_b_id,
            adjustment=adjustment,
            reason=f"{interaction_type or 'interaction'} {'succeeded' if success else 'failed'}"
        )

        return relationship

    @staticmethod
    def add_recommendation(
        session,
        recommender_agent_id: int,
        recommended_agent_id: int,
        target_agent_id: int,
        recommendation_type: str,
        score: float,
        comment: Optional[str] = None,
        evidence: Optional[dict] = None
    ) -> dict:
        """
        Add trust recommendation.

        Args:
            session: Database session
            recommender_agent_id: Agent making recommendation
            recommended_agent_id: Agent being recommended
            target_agent_id: Agent receiving recommendation
            recommendation_type: Type of recommendation
            score: Recommended trust score
            comment: Optional comment
            evidence: Supporting evidence

        Returns:
            Recommendation record
        """
        if not 0 <= score <= 1:
            raise ValueError("Recommendation score must be between 0 and 1")

        AgentTrust._recommendation_counter += 1
        recommendation_id = f"rec_{AgentTrust._recommendation_counter}"

        # Weight recommendation by recommender's trust
        recommender_trust = AgentTrust.get_trust_score(
            session, target_agent_id, recommender_agent_id
        )
        weighted_score = score * recommender_trust

        recommendation = {
            "id": recommendation_id,
            "recommender_agent_id": recommender_agent_id,
            "recommended_agent_id": recommended_agent_id,
            "target_agent_id": target_agent_id,
            "recommendation_type": recommendation_type,
            "score": score,
            "weighted_score": weighted_score,
            "comment": comment,
            "evidence": evidence or {},
            "created_at": datetime.utcnow().isoformat(),
            "used": False
        }

        AgentTrust._recommendations.append(recommendation)

        return recommendation

    @staticmethod
    def request_verification(
        session,
        agent_id: int,
        verification_type: str,
        evidence: dict,
        verifier_agent_id: Optional[int] = None
    ) -> dict:
        """
        Request verification of agent credentials or claims.

        Args:
            session: Database session
            agent_id: Agent requesting verification
            verification_type: Type of verification
            evidence: Evidence to verify
            verifier_agent_id: Optional specific verifier

        Returns:
            Verification request
        """
        AgentTrust._verification_counter += 1
        verification_id = f"verify_{AgentTrust._verification_counter}"

        verification = {
            "id": verification_id,
            "agent_id": agent_id,
            "verification_type": verification_type,
            "evidence": evidence,
            "verifier_agent_id": verifier_agent_id,
            "status": VerificationStatus.PENDING,
            "requested_at": datetime.utcnow().isoformat(),
            "verified_at": None,
            "verification_result": None,
            "verifier_notes": None
        }

        AgentTrust._verifications[verification_id] = verification

        return verification

    @staticmethod
    def verify_agent(
        session,
        verification_id: str,
        verifier_agent_id: int,
        approved: bool,
        verifier_notes: Optional[str] = None
    ) -> dict:
        """
        Verify an agent's credentials or claims.

        Args:
            session: Database session
            verification_id: Verification request ID
            verifier_agent_id: Verifier agent ID
            approved: Whether verification passed
            verifier_notes: Verifier notes

        Returns:
            Verification result
        """
        if verification_id not in AgentTrust._verifications:
            raise ValueError(f"Verification {verification_id} not found")

        verification = AgentTrust._verifications[verification_id]

        if verification["status"] != VerificationStatus.PENDING:
            raise ValueError(f"Verification already {verification['status']}")

        verification["status"] = VerificationStatus.VERIFIED if approved else VerificationStatus.REJECTED
        verification["verifier_agent_id"] = verifier_agent_id
        verification["verified_at"] = datetime.utcnow().isoformat()
        verification["verification_result"] = approved
        verification["verifier_notes"] = verifier_notes

        # If verified, boost agent's global trust
        if approved:
            AgentTrust._global_trust_scores[verification["agent_id"]] += 0.1
            AgentTrust._global_trust_scores[verification["agent_id"]] = min(
                1.0, AgentTrust._global_trust_scores[verification["agent_id"]]
            )

        return verification

    @staticmethod
    def get_trust_score(
        session,
        agent_a_id: int,
        agent_b_id: int
    ) -> float:
        """
        Get trust score between two agents.

        Args:
            session: Database session
            agent_a_id: First agent ID
            agent_b_id: Second agent ID

        Returns:
            Trust score (0-1)
        """
        return AgentTrust._trust_scores[agent_a_id].get(agent_b_id, 0.5)

    @staticmethod
    def get_trust_relationship(
        session,
        agent_a_id: int,
        agent_b_id: int
    ) -> dict:
        """
        Get detailed trust relationship.

        Args:
            session: Database session
            agent_a_id: First agent ID
            agent_b_id: Second agent ID

        Returns:
            Trust relationship details
        """
        key = (min(agent_a_id, agent_b_id), max(agent_a_id, agent_b_id))

        if key not in AgentTrust._trust_relationships:
            raise ValueError(f"No trust relationship between agents {agent_a_id} and {agent_b_id}")

        relationship = AgentTrust._trust_relationships[key]
        history = AgentTrust._trust_history.get(key, [])

        return {
            **relationship,
            "history": history[-10:]  # Last 10 events
        }

    @staticmethod
    def get_trusted_agents(
        session,
        agent_id: int,
        min_trust_level: str = TrustLevel.MEDIUM,
        limit: int = 10
    ) -> dict:
        """
        Get agents trusted by an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            min_trust_level: Minimum trust level
            limit: Maximum results

        Returns:
            Trusted agents
        """
        trust_scores = AgentTrust._trust_scores.get(agent_id, {})

        # Filter by minimum level
        min_score = AgentTrust._level_to_min_score(min_trust_level)
        trusted = [
            {
                "agent_id": other_id,
                "trust_score": score,
                "trust_level": AgentTrust._score_to_level(score)
            }
            for other_id, score in trust_scores.items()
            if score >= min_score
        ]

        # Sort by score
        trusted.sort(key=lambda x: x["trust_score"], reverse=True)

        return {
            "agent_id": agent_id,
            "min_trust_level": min_trust_level,
            "total_trusted": len(trusted),
            "trusted_agents": trusted[:limit]
        }

    @staticmethod
    def get_recommendations(
        session,
        target_agent_id: int,
        recommended_agent_id: int
    ) -> dict:
        """
        Get recommendations for an agent.

        Args:
            session: Database session
            target_agent_id: Agent receiving recommendations
            recommended_agent_id: Agent being recommended

        Returns:
            Recommendations
        """
        recommendations = [
            r for r in AgentTrust._recommendations
            if r["target_agent_id"] == target_agent_id
            and r["recommended_agent_id"] == recommended_agent_id
        ]

        if not recommendations:
            return {
                "target_agent_id": target_agent_id,
                "recommended_agent_id": recommended_agent_id,
                "total_recommendations": 0,
                "average_score": 0.5,
                "recommendations": []
            }

        avg_score = statistics.mean(r["weighted_score"] for r in recommendations)

        return {
            "target_agent_id": target_agent_id,
            "recommended_agent_id": recommended_agent_id,
            "total_recommendations": len(recommendations),
            "average_score": avg_score,
            "recommendations": recommendations
        }

    @staticmethod
    def get_global_trust_score(
        session,
        agent_id: int
    ) -> dict:
        """
        Get agent's global trust score.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Global trust information
        """
        global_score = AgentTrust._global_trust_scores.get(agent_id, 0.5)

        # Count relationships
        relationships = [
            r for r in AgentTrust._trust_relationships.values()
            if r["agent_a_id"] == agent_id or r["agent_b_id"] == agent_id
        ]

        # Count verifications
        verifications = [
            v for v in AgentTrust._verifications.values()
            if v["agent_id"] == agent_id and v["status"] == VerificationStatus.VERIFIED
        ]

        return {
            "agent_id": agent_id,
            "global_trust_score": global_score,
            "trust_level": AgentTrust._score_to_level(global_score),
            "total_relationships": len(relationships),
            "verified_credentials": len(verifications)
        }

    @staticmethod
    def get_trust_statistics(session) -> dict:
        """
        Get trust system statistics.

        Args:
            session: Database session

        Returns:
            System statistics
        """
        total_relationships = len(AgentTrust._trust_relationships)
        total_recommendations = len(AgentTrust._recommendations)
        total_verifications = len(AgentTrust._verifications)

        # Average trust score
        all_scores = [r["trust_score"] for r in AgentTrust._trust_relationships.values()]
        avg_trust = statistics.mean(all_scores) if all_scores else 0.5

        # Trust level distribution
        level_distribution = defaultdict(int)
        for relationship in AgentTrust._trust_relationships.values():
            level_distribution[relationship["trust_level"]] += 1

        # Verification stats
        verified_count = sum(
            1 for v in AgentTrust._verifications.values()
            if v["status"] == VerificationStatus.VERIFIED
        )

        return {
            "total_relationships": total_relationships,
            "total_recommendations": total_recommendations,
            "total_verifications": total_verifications,
            "verified_agents": verified_count,
            "average_trust_score": avg_trust,
            "trust_level_distribution": dict(level_distribution)
        }

    # Helper methods

    @staticmethod
    def _score_to_level(score: float) -> str:
        """Convert trust score to level"""
        if score >= 0.9:
            return TrustLevel.VERIFIED
        elif score >= 0.7:
            return TrustLevel.HIGH
        elif score >= 0.5:
            return TrustLevel.MEDIUM
        elif score >= 0.3:
            return TrustLevel.LOW
        else:
            return TrustLevel.UNTRUSTED

    @staticmethod
    def _level_to_min_score(level: str) -> float:
        """Convert trust level to minimum score"""
        level_scores = {
            TrustLevel.VERIFIED: 0.9,
            TrustLevel.HIGH: 0.7,
            TrustLevel.MEDIUM: 0.5,
            TrustLevel.LOW: 0.3,
            TrustLevel.UNTRUSTED: 0.0,
            TrustLevel.UNKNOWN: 0.0
        }
        return level_scores.get(level, 0.5)

    @staticmethod
    def _recalculate_global_trust(agent_id: int):
        """Recalculate agent's global trust score"""
        trust_scores = AgentTrust._trust_scores.get(agent_id, {})

        if not trust_scores:
            return

        # Global trust is average of all trust scores
        avg_score = statistics.mean(trust_scores.values())
        AgentTrust._global_trust_scores[agent_id] = avg_score
