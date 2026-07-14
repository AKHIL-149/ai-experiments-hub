"""
Agent Learning Service

Enables agents to learn from past experiences, recognize patterns, adapt strategies,
and improve performance over time through machine learning and experience tracking.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session

from src.models import Agent
from src.core.logging import logger


class ExperienceType:
    """Experience type constants"""
    TASK_SUCCESS = "task_success"
    TASK_FAILURE = "task_failure"
    COLLABORATION_SUCCESS = "collaboration_success"
    COLLABORATION_FAILURE = "collaboration_failure"
    CONFLICT_RESOLUTION = "conflict_resolution"
    NEGOTIATION_SUCCESS = "negotiation_success"
    NEGOTIATION_FAILURE = "negotiation_failure"


class LearningStrategy:
    """Learning strategy constants"""
    REINFORCEMENT = "reinforcement"  # Learn from rewards
    SUPERVISED = "supervised"  # Learn from labeled examples
    IMITATION = "imitation"  # Learn from observing others
    ADAPTIVE = "adaptive"  # Adapt strategies based on context


class SkillLevel:
    """Skill level constants"""
    NOVICE = "novice"  # 0-20
    BEGINNER = "beginner"  # 21-40
    INTERMEDIATE = "intermediate"  # 41-60
    ADVANCED = "advanced"  # 61-80
    EXPERT = "expert"  # 81-100


class AgentLearning:
    """Service for managing agent learning and adaptation"""

    # In-memory storage
    _experiences: Dict[int, List[Dict[str, Any]]] = {}  # agent_id -> experiences
    _patterns: Dict[int, Dict[str, Any]] = {}  # agent_id -> recognized patterns
    _skills: Dict[int, Dict[str, float]] = {}  # agent_id -> skill_name -> proficiency
    _strategies: Dict[int, Dict[str, Any]] = {}  # agent_id -> learned strategies
    _learning_curves: Dict[int, List[Dict[str, Any]]] = {}  # agent_id -> progress over time
    _experience_counter = 0

    @staticmethod
    def initialize_learning(
        session: Session,
        agent_id: int,
        initial_skills: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Initialize learning tracking for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            initial_skills: Optional initial skill proficiencies

        Returns:
            Learning profile
        """
        # Validate agent
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent_id in AgentLearning._experiences:
            raise ValueError(f"Learning already initialized for agent {agent_id}")

        AgentLearning._experiences[agent_id] = []
        AgentLearning._patterns[agent_id] = {}
        AgentLearning._skills[agent_id] = initial_skills or {}
        AgentLearning._strategies[agent_id] = {}
        AgentLearning._learning_curves[agent_id] = []

        profile = {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "total_experiences": 0,
            "skills": initial_skills or {},
            "patterns_recognized": 0,
            "strategies_learned": 0,
            "initialized_at": datetime.utcnow().isoformat()
        }

        logger.info(f"Initialized learning for agent {agent_id}")

        return profile

    @staticmethod
    def record_experience(
        session: Session,
        agent_id: int,
        experience_type: str,
        outcome: str,
        context: Dict[str, Any],
        learning_value: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Record a learning experience for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            experience_type: Type of experience
            outcome: Outcome (success/failure/neutral)
            context: Context and details of the experience
            learning_value: How valuable this experience is (0-1)
            metadata: Optional metadata

        Returns:
            Experience details
        """
        if agent_id not in AgentLearning._experiences:
            raise ValueError(f"Learning not initialized for agent {agent_id}")

        AgentLearning._experience_counter += 1
        experience = {
            "experience_id": AgentLearning._experience_counter,
            "agent_id": agent_id,
            "experience_type": experience_type,
            "outcome": outcome,
            "context": context,
            "learning_value": learning_value,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        AgentLearning._experiences[agent_id].append(experience)

        # Trigger pattern recognition after certain number of experiences
        if len(AgentLearning._experiences[agent_id]) % 10 == 0:
            AgentLearning._recognize_patterns(agent_id)

        # Update learning curve
        AgentLearning._update_learning_curve(agent_id)

        logger.info(
            f"Recorded experience for agent {agent_id}: {experience_type} "
            f"({outcome}, learning_value: {learning_value})"
        )

        return experience

    @staticmethod
    def update_skill_proficiency(
        session: Session,
        agent_id: int,
        skill_name: str,
        proficiency_delta: float,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Update agent's skill proficiency.

        Args:
            session: Database session
            agent_id: Agent ID
            skill_name: Skill name
            proficiency_delta: Change in proficiency (-100 to +100)
            reason: Reason for update

        Returns:
            Updated skill details
        """
        if agent_id not in AgentLearning._skills:
            raise ValueError(f"Learning not initialized for agent {agent_id}")

        # Get current proficiency (default to 0)
        current = AgentLearning._skills[agent_id].get(skill_name, 0.0)

        # Apply delta (clamp to 0-100)
        new_proficiency = max(0, min(100, current + proficiency_delta))

        AgentLearning._skills[agent_id][skill_name] = new_proficiency

        skill_level = AgentLearning._calculate_skill_level(new_proficiency)

        logger.info(
            f"Updated skill '{skill_name}' for agent {agent_id}: "
            f"{current:.1f} -> {new_proficiency:.1f} ({skill_level})"
        )

        return {
            "agent_id": agent_id,
            "skill_name": skill_name,
            "proficiency": new_proficiency,
            "skill_level": skill_level,
            "change": proficiency_delta,
            "reason": reason,
            "updated_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def learn_strategy(
        session: Session,
        agent_id: int,
        strategy_name: str,
        strategy_details: Dict[str, Any],
        effectiveness: float,
        learning_strategy: str = LearningStrategy.REINFORCEMENT
    ) -> Dict[str, Any]:
        """
        Record a learned strategy.

        Args:
            session: Database session
            agent_id: Agent ID
            strategy_name: Strategy name
            strategy_details: Strategy details and parameters
            effectiveness: How effective the strategy is (0-1)
            learning_strategy: How it was learned

        Returns:
            Strategy details
        """
        if agent_id not in AgentLearning._strategies:
            raise ValueError(f"Learning not initialized for agent {agent_id}")

        strategy = {
            "strategy_name": strategy_name,
            "details": strategy_details,
            "effectiveness": effectiveness,
            "learning_strategy": learning_strategy,
            "times_used": 0,
            "success_count": 0,
            "failure_count": 0,
            "learned_at": datetime.utcnow().isoformat(),
            "last_used": None
        }

        AgentLearning._strategies[agent_id][strategy_name] = strategy

        logger.info(
            f"Agent {agent_id} learned strategy '{strategy_name}' "
            f"via {learning_strategy} (effectiveness: {effectiveness})"
        )

        return strategy

    @staticmethod
    def apply_strategy(
        session: Session,
        agent_id: int,
        strategy_name: str,
        success: bool
    ) -> Dict[str, Any]:
        """
        Record application of a learned strategy.

        Args:
            session: Database session
            agent_id: Agent ID
            strategy_name: Strategy name
            success: Whether application was successful

        Returns:
            Updated strategy
        """
        if agent_id not in AgentLearning._strategies:
            raise ValueError(f"Learning not initialized for agent {agent_id}")

        if strategy_name not in AgentLearning._strategies[agent_id]:
            raise ValueError(f"Strategy '{strategy_name}' not found for agent {agent_id}")

        strategy = AgentLearning._strategies[agent_id][strategy_name]

        # Update usage stats
        strategy["times_used"] += 1
        if success:
            strategy["success_count"] += 1
        else:
            strategy["failure_count"] += 1

        # Recalculate effectiveness
        total_outcomes = strategy["success_count"] + strategy["failure_count"]
        if total_outcomes > 0:
            strategy["effectiveness"] = strategy["success_count"] / total_outcomes

        strategy["last_used"] = datetime.utcnow().isoformat()

        logger.info(
            f"Agent {agent_id} applied strategy '{strategy_name}': "
            f"{'success' if success else 'failure'} "
            f"(effectiveness now: {strategy['effectiveness']:.2f})"
        )

        return strategy

    @staticmethod
    def get_recommendations(
        session: Session,
        agent_id: int,
        task_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get learning-based recommendations for a task.

        Args:
            session: Database session
            agent_id: Agent ID
            task_context: Task context for recommendations

        Returns:
            Recommendations
        """
        if agent_id not in AgentLearning._experiences:
            raise ValueError(f"Learning not initialized for agent {agent_id}")

        recommendations = {
            "agent_id": agent_id,
            "task_context": task_context,
            "recommended_strategies": [],
            "skills_to_improve": [],
            "similar_past_experiences": [],
            "success_probability": 0.5
        }

        # Find similar past experiences
        similar_experiences = AgentLearning._find_similar_experiences(
            agent_id,
            task_context
        )
        recommendations["similar_past_experiences"] = similar_experiences[:5]

        # Calculate success probability based on past experiences
        if similar_experiences:
            successes = sum(
                1 for exp in similar_experiences
                if exp.get("outcome") == "success"
            )
            recommendations["success_probability"] = successes / len(similar_experiences)

        # Recommend strategies based on effectiveness
        strategies = AgentLearning._strategies.get(agent_id, {})
        sorted_strategies = sorted(
            strategies.items(),
            key=lambda x: x[1]["effectiveness"],
            reverse=True
        )

        recommendations["recommended_strategies"] = [
            {
                "strategy_name": name,
                "effectiveness": details["effectiveness"],
                "times_used": details["times_used"]
            }
            for name, details in sorted_strategies[:3]
        ]

        # Identify skills to improve
        skills = AgentLearning._skills.get(agent_id, {})
        low_skills = [
            {"skill": skill, "proficiency": prof}
            for skill, prof in skills.items()
            if prof < 60
        ]
        low_skills.sort(key=lambda x: x["proficiency"])
        recommendations["skills_to_improve"] = low_skills[:3]

        return recommendations

    @staticmethod
    def get_learning_progress(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """Get agent's learning progress over time"""
        if agent_id not in AgentLearning._experiences:
            raise ValueError(f"Learning not initialized for agent {agent_id}")

        experiences = AgentLearning._experiences[agent_id]
        skills = AgentLearning._skills[agent_id]
        strategies = AgentLearning._strategies[agent_id]
        patterns = AgentLearning._patterns[agent_id]
        learning_curve = AgentLearning._learning_curves[agent_id]

        # Calculate success rate over time
        total_experiences = len(experiences)
        successes = sum(1 for exp in experiences if exp.get("outcome") == "success")
        success_rate = (successes / total_experiences * 100) if total_experiences > 0 else 0

        # Calculate average skill proficiency
        avg_skill = (sum(skills.values()) / len(skills)) if skills else 0

        # Get recent improvements
        recent_experiences = experiences[-10:] if len(experiences) >= 10 else experiences
        recent_successes = sum(1 for exp in recent_experiences if exp.get("outcome") == "success")
        recent_success_rate = (recent_successes / len(recent_experiences) * 100) if recent_experiences else 0

        return {
            "agent_id": agent_id,
            "total_experiences": total_experiences,
            "success_rate": success_rate,
            "recent_success_rate": recent_success_rate,
            "total_skills": len(skills),
            "average_skill_proficiency": avg_skill,
            "strategies_learned": len(strategies),
            "patterns_recognized": len(patterns),
            "learning_curve": learning_curve[-20:] if len(learning_curve) > 20 else learning_curve
        }

    @staticmethod
    def get_learning_statistics(session: Session) -> Dict[str, Any]:
        """
        Get learning system statistics.

        Args:
            session: Database session

        Returns:
            System statistics
        """
        total_agents = len(AgentLearning._experiences)

        if total_agents == 0:
            return {
                "total_agents": 0,
                "total_experiences": 0,
                "total_skills_tracked": 0,
                "total_strategies_learned": 0
            }

        total_experiences = sum(
            len(experiences) for experiences in AgentLearning._experiences.values()
        )

        total_skills = sum(
            len(skills) for skills in AgentLearning._skills.values()
        )

        total_strategies = sum(
            len(strategies) for strategies in AgentLearning._strategies.values()
        )

        # Experience type breakdown
        experience_types = defaultdict(int)
        for experiences in AgentLearning._experiences.values():
            for exp in experiences:
                experience_types[exp["experience_type"]] += 1

        # Average success rate
        all_experiences = []
        for experiences in AgentLearning._experiences.values():
            all_experiences.extend(experiences)

        successes = sum(1 for exp in all_experiences if exp.get("outcome") == "success")
        avg_success_rate = (successes / len(all_experiences) * 100) if all_experiences else 0

        return {
            "total_agents": total_agents,
            "total_experiences": total_experiences,
            "total_skills_tracked": total_skills,
            "total_strategies_learned": total_strategies,
            "average_success_rate": avg_success_rate,
            "experience_types": dict(experience_types)
        }

    @staticmethod
    def _recognize_patterns(agent_id: int):
        """Recognize patterns in agent's experiences"""
        experiences = AgentLearning._experiences[agent_id]

        if len(experiences) < 5:
            return  # Not enough data

        # Group by experience type
        by_type = defaultdict(list)
        for exp in experiences:
            by_type[exp["experience_type"]].append(exp)

        patterns = {}

        for exp_type, type_experiences in by_type.items():
            if len(type_experiences) < 3:
                continue

            # Calculate success rate for this type
            successes = sum(1 for exp in type_experiences if exp.get("outcome") == "success")
            success_rate = successes / len(type_experiences)

            patterns[exp_type] = {
                "experience_type": exp_type,
                "total_occurrences": len(type_experiences),
                "success_rate": success_rate,
                "identified_at": datetime.utcnow().isoformat()
            }

        AgentLearning._patterns[agent_id] = patterns

        logger.info(f"Recognized {len(patterns)} patterns for agent {agent_id}")

    @staticmethod
    def _update_learning_curve(agent_id: int):
        """Update agent's learning curve over time"""
        experiences = AgentLearning._experiences[agent_id]

        # Calculate success rate for recent window (last 10 experiences)
        window_size = 10
        if len(experiences) < window_size:
            recent = experiences
        else:
            recent = experiences[-window_size:]

        successes = sum(1 for exp in recent if exp.get("outcome") == "success")
        success_rate = (successes / len(recent) * 100) if recent else 0

        # Calculate average skill
        skills = AgentLearning._skills[agent_id]
        avg_skill = (sum(skills.values()) / len(skills)) if skills else 0

        curve_point = {
            "experience_count": len(experiences),
            "success_rate": success_rate,
            "average_skill": avg_skill,
            "timestamp": datetime.utcnow().isoformat()
        }

        AgentLearning._learning_curves[agent_id].append(curve_point)

    @staticmethod
    def _find_similar_experiences(
        agent_id: int,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find similar past experiences based on context"""
        experiences = AgentLearning._experiences[agent_id]

        # Simple similarity: match on common context keys
        similar = []
        for exp in experiences:
            exp_context = exp.get("context", {})

            # Count matching keys
            matches = sum(
                1 for key in context.keys()
                if key in exp_context and context[key] == exp_context[key]
            )

            if matches > 0:
                similarity = matches / len(context)
                similar.append({
                    **exp,
                    "similarity": similarity
                })

        # Sort by similarity
        similar.sort(key=lambda x: x["similarity"], reverse=True)

        return similar

    @staticmethod
    def _calculate_skill_level(proficiency: float) -> str:
        """Calculate skill level from proficiency score"""
        if proficiency >= 81:
            return SkillLevel.EXPERT
        elif proficiency >= 61:
            return SkillLevel.ADVANCED
        elif proficiency >= 41:
            return SkillLevel.INTERMEDIATE
        elif proficiency >= 21:
            return SkillLevel.BEGINNER
        else:
            return SkillLevel.NOVICE
