"""
Coalition Formation Service

Enables agents to form temporary coalitions (teams) to collaborate on complex tasks.
Supports dynamic coalition formation, member management, resource pooling, and goal sharing.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.models.database import Agent, Task
from src.core.logging import logger


class CoalitionStatus:
    """Coalition status constants"""
    FORMING = "forming"
    ACTIVE = "active"
    COMPLETED = "completed"
    DISSOLVED = "dissolved"


class MemberRole:
    """Coalition member role constants"""
    LEADER = "leader"
    COORDINATOR = "coordinator"
    SPECIALIST = "specialist"
    CONTRIBUTOR = "contributor"
    ADVISOR = "advisor"


class FormationStrategy:
    """Coalition formation strategy constants"""
    CAPABILITY_BASED = "capability_based"  # Based on required capabilities
    REPUTATION_BASED = "reputation_based"  # Based on agent reputation
    WORKLOAD_BASED = "workload_based"  # Based on current workload
    PROXIMITY_BASED = "proximity_based"  # Based on agent similarity
    HYBRID = "hybrid"  # Combination of multiple factors


class CoalitionFormation:
    """Service for managing agent coalitions"""

    # In-memory storage for coalitions
    _coalitions: Dict[int, Dict[str, Any]] = {}
    _coalition_counter = 0

    @staticmethod
    def create_coalition(
        session: Session,
        name: str,
        goal: str,
        required_capabilities: List[str],
        leader_agent_id: Optional[int] = None,
        initial_members: Optional[List[int]] = None,
        max_members: int = 10,
        duration_hours: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new coalition.

        Args:
            session: Database session
            name: Coalition name
            goal: Coalition goal/objective
            required_capabilities: List of required capabilities
            leader_agent_id: Optional leader agent ID
            initial_members: Optional list of initial member agent IDs
            max_members: Maximum coalition size
            duration_hours: Optional coalition duration in hours
            metadata: Optional metadata

        Returns:
            Coalition details
        """
        # Validate leader if provided
        if leader_agent_id:
            leader = session.query(Agent).filter(Agent.id == leader_agent_id).first()
            if not leader:
                raise ValueError(f"Leader agent {leader_agent_id} not found")

        # Validate initial members if provided
        members = []
        if initial_members:
            agents = session.query(Agent).filter(Agent.id.in_(initial_members)).all()
            if len(agents) != len(initial_members):
                raise ValueError("One or more initial member agents not found")

            for agent in agents:
                members.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "role": MemberRole.LEADER if agent.id == leader_agent_id else MemberRole.CONTRIBUTOR,
                    "joined_at": datetime.utcnow().isoformat(),
                    "contribution_score": 0.0,
                    "active": True
                })

        CoalitionFormation._coalition_counter += 1
        coalition_id = CoalitionFormation._coalition_counter

        coalition = {
            "coalition_id": coalition_id,
            "name": name,
            "goal": goal,
            "required_capabilities": required_capabilities,
            "leader_agent_id": leader_agent_id,
            "members": members,
            "max_members": max_members,
            "status": CoalitionStatus.FORMING if not members else CoalitionStatus.ACTIVE,
            "created_at": datetime.utcnow().isoformat(),
            "activated_at": datetime.utcnow().isoformat() if members else None,
            "dissolved_at": None,
            "expires_at": (datetime.utcnow() + timedelta(hours=duration_hours)).isoformat() if duration_hours else None,
            "tasks": [],
            "pooled_resources": {},
            "achievements": [],
            "metadata": metadata or {}
        }

        CoalitionFormation._coalitions[coalition_id] = coalition

        logger.info(
            f"Created coalition {coalition_id}: '{name}' "
            f"with {len(members)} initial members"
        )

        return coalition

    @staticmethod
    def add_member(
        session: Session,
        coalition_id: int,
        agent_id: int,
        role: str = MemberRole.CONTRIBUTOR
    ) -> Dict[str, Any]:
        """
        Add a member to coalition.

        Args:
            session: Database session
            coalition_id: Coalition ID
            agent_id: Agent ID to add
            role: Member role

        Returns:
            Updated coalition
        """
        if coalition_id not in CoalitionFormation._coalitions:
            raise ValueError(f"Coalition {coalition_id} not found")

        coalition = CoalitionFormation._coalitions[coalition_id]

        # Check if coalition is active
        if coalition["status"] not in [CoalitionStatus.FORMING, CoalitionStatus.ACTIVE]:
            raise ValueError(f"Coalition is {coalition['status']}, cannot add members")

        # Check if agent already a member
        for member in coalition["members"]:
            if member["agent_id"] == agent_id:
                raise ValueError(f"Agent {agent_id} already in coalition")

        # Check max members
        if len(coalition["members"]) >= coalition["max_members"]:
            raise ValueError(f"Coalition has reached maximum size ({coalition['max_members']})")

        # Validate agent exists
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        member = {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "role": role,
            "joined_at": datetime.utcnow().isoformat(),
            "contribution_score": 0.0,
            "active": True
        }

        coalition["members"].append(member)

        # Activate coalition if it was forming
        if coalition["status"] == CoalitionStatus.FORMING:
            coalition["status"] = CoalitionStatus.ACTIVE
            coalition["activated_at"] = datetime.utcnow().isoformat()

        logger.info(f"Added agent {agent_id} to coalition {coalition_id} as {role}")

        return coalition

    @staticmethod
    def remove_member(
        session: Session,
        coalition_id: int,
        agent_id: int,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Remove a member from coalition.

        Args:
            session: Database session
            coalition_id: Coalition ID
            agent_id: Agent ID to remove
            reason: Optional removal reason

        Returns:
            Updated coalition
        """
        if coalition_id not in CoalitionFormation._coalitions:
            raise ValueError(f"Coalition {coalition_id} not found")

        coalition = CoalitionFormation._coalitions[coalition_id]

        # Find and remove member
        member = None
        for i, m in enumerate(coalition["members"]):
            if m["agent_id"] == agent_id:
                member = coalition["members"].pop(i)
                break

        if not member:
            raise ValueError(f"Agent {agent_id} not in coalition")

        # If leader left, reassign leadership
        if agent_id == coalition["leader_agent_id"] and coalition["members"]:
            # Assign to first remaining member
            coalition["leader_agent_id"] = coalition["members"][0]["agent_id"]
            coalition["members"][0]["role"] = MemberRole.LEADER

        # If no members left, dissolve coalition
        if not coalition["members"]:
            coalition["status"] = CoalitionStatus.DISSOLVED
            coalition["dissolved_at"] = datetime.utcnow().isoformat()

        logger.info(f"Removed agent {agent_id} from coalition {coalition_id}: {reason}")

        return coalition

    @staticmethod
    def assign_task(
        session: Session,
        coalition_id: int,
        task_id: int
    ) -> Dict[str, Any]:
        """
        Assign a task to coalition.

        Args:
            session: Database session
            coalition_id: Coalition ID
            task_id: Task ID

        Returns:
            Updated coalition
        """
        if coalition_id not in CoalitionFormation._coalitions:
            raise ValueError(f"Coalition {coalition_id} not found")

        coalition = CoalitionFormation._coalitions[coalition_id]

        # Validate coalition is active
        if coalition["status"] != CoalitionStatus.ACTIVE:
            raise ValueError(f"Coalition is {coalition['status']}, cannot assign tasks")

        # Validate task exists
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Check if task already assigned
        if task_id in coalition["tasks"]:
            raise ValueError(f"Task {task_id} already assigned to coalition")

        coalition["tasks"].append(task_id)

        logger.info(f"Assigned task {task_id} to coalition {coalition_id}")

        return coalition

    @staticmethod
    def pool_resource(
        session: Session,
        coalition_id: int,
        agent_id: int,
        resource_type: str,
        amount: float
    ) -> Dict[str, Any]:
        """
        Pool a resource to coalition.

        Args:
            session: Database session
            coalition_id: Coalition ID
            agent_id: Agent contributing resource
            resource_type: Type of resource
            amount: Amount to contribute

        Returns:
            Updated coalition
        """
        if coalition_id not in CoalitionFormation._coalitions:
            raise ValueError(f"Coalition {coalition_id} not found")

        coalition = CoalitionFormation._coalitions[coalition_id]

        # Validate agent is member
        is_member = any(m["agent_id"] == agent_id for m in coalition["members"])
        if not is_member:
            raise ValueError(f"Agent {agent_id} not a member of coalition")

        # Add to pooled resources
        if resource_type not in coalition["pooled_resources"]:
            coalition["pooled_resources"][resource_type] = {
                "total": 0.0,
                "contributions": []
            }

        coalition["pooled_resources"][resource_type]["total"] += amount
        coalition["pooled_resources"][resource_type]["contributions"].append({
            "agent_id": agent_id,
            "amount": amount,
            "contributed_at": datetime.utcnow().isoformat()
        })

        logger.info(
            f"Agent {agent_id} pooled {amount} {resource_type} "
            f"to coalition {coalition_id}"
        )

        return coalition

    @staticmethod
    def update_contribution_score(
        session: Session,
        coalition_id: int,
        agent_id: int,
        score_delta: float
    ) -> Dict[str, Any]:
        """
        Update agent's contribution score in coalition.

        Args:
            session: Database session
            coalition_id: Coalition ID
            agent_id: Agent ID
            score_delta: Score change (positive or negative)

        Returns:
            Updated coalition
        """
        if coalition_id not in CoalitionFormation._coalitions:
            raise ValueError(f"Coalition {coalition_id} not found")

        coalition = CoalitionFormation._coalitions[coalition_id]

        # Find member
        member = None
        for m in coalition["members"]:
            if m["agent_id"] == agent_id:
                member = m
                break

        if not member:
            raise ValueError(f"Agent {agent_id} not in coalition")

        member["contribution_score"] += score_delta

        return coalition

    @staticmethod
    def record_achievement(
        session: Session,
        coalition_id: int,
        title: str,
        description: str,
        value: float = 1.0
    ) -> Dict[str, Any]:
        """
        Record a coalition achievement.

        Args:
            session: Database session
            coalition_id: Coalition ID
            title: Achievement title
            description: Achievement description
            value: Achievement value/importance

        Returns:
            Updated coalition
        """
        if coalition_id not in CoalitionFormation._coalitions:
            raise ValueError(f"Coalition {coalition_id} not found")

        coalition = CoalitionFormation._coalitions[coalition_id]

        achievement = {
            "title": title,
            "description": description,
            "value": value,
            "achieved_at": datetime.utcnow().isoformat()
        }

        coalition["achievements"].append(achievement)

        logger.info(f"Coalition {coalition_id} achieved: {title}")

        return coalition

    @staticmethod
    def dissolve_coalition(
        session: Session,
        coalition_id: int,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Dissolve a coalition.

        Args:
            session: Database session
            coalition_id: Coalition ID
            reason: Dissolution reason

        Returns:
            Dissolved coalition
        """
        if coalition_id not in CoalitionFormation._coalitions:
            raise ValueError(f"Coalition {coalition_id} not found")

        coalition = CoalitionFormation._coalitions[coalition_id]

        coalition["status"] = CoalitionStatus.DISSOLVED
        coalition["dissolved_at"] = datetime.utcnow().isoformat()
        coalition["dissolution_reason"] = reason

        # Mark all members as inactive
        for member in coalition["members"]:
            member["active"] = False

        logger.info(f"Dissolved coalition {coalition_id}: {reason}")

        return coalition

    @staticmethod
    def complete_coalition(
        session: Session,
        coalition_id: int,
        outcome: str = ""
    ) -> Dict[str, Any]:
        """
        Mark coalition as completed.

        Args:
            session: Database session
            coalition_id: Coalition ID
            outcome: Completion outcome

        Returns:
            Completed coalition
        """
        if coalition_id not in CoalitionFormation._coalitions:
            raise ValueError(f"Coalition {coalition_id} not found")

        coalition = CoalitionFormation._coalitions[coalition_id]

        coalition["status"] = CoalitionStatus.COMPLETED
        coalition["dissolved_at"] = datetime.utcnow().isoformat()
        coalition["outcome"] = outcome

        logger.info(f"Completed coalition {coalition_id}: {outcome}")

        return coalition

    @staticmethod
    def suggest_coalition(
        session: Session,
        task_id: int,
        strategy: str = FormationStrategy.CAPABILITY_BASED,
        max_members: int = 5
    ) -> Dict[str, Any]:
        """
        Suggest optimal coalition for a task.

        Args:
            session: Database session
            task_id: Task ID
            strategy: Formation strategy
            max_members: Maximum coalition size

        Returns:
            Coalition suggestion
        """
        # Validate task
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Get all available agents
        agents = session.query(Agent).all()

        if strategy == FormationStrategy.CAPABILITY_BASED:
            suggested = CoalitionFormation._suggest_by_capability(
                task, agents, max_members
            )
        elif strategy == FormationStrategy.WORKLOAD_BASED:
            suggested = CoalitionFormation._suggest_by_workload(
                task, agents, max_members
            )
        else:  # HYBRID or default
            suggested = CoalitionFormation._suggest_hybrid(
                task, agents, max_members
            )

        return {
            "task_id": task_id,
            "task_title": task.title,
            "strategy": strategy,
            "suggested_members": suggested,
            "coalition_size": len(suggested)
        }

    @staticmethod
    def _suggest_by_capability(
        task: Task,
        agents: List[Agent],
        max_members: int
    ) -> List[Dict[str, Any]]:
        """Suggest coalition based on agent capabilities"""
        # Get required capabilities from task metadata
        required_caps = task.metadata.get("required_capabilities", []) if task.metadata else []

        suggestions = []
        for agent in agents:
            agent_caps = agent.metadata.get("capabilities", []) if agent.metadata else []

            # Calculate capability match
            if required_caps:
                matched = set(agent_caps) & set(required_caps)
                match_score = len(matched) / len(required_caps)
            else:
                match_score = 0.5

            suggestions.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "match_score": match_score,
                "capabilities": agent_caps
            })

        # Sort by match score and take top N
        suggestions.sort(key=lambda x: x["match_score"], reverse=True)
        return suggestions[:max_members]

    @staticmethod
    def _suggest_by_workload(
        task: Task,
        agents: List[Agent],
        max_members: int
    ) -> List[Dict[str, Any]]:
        """Suggest coalition based on agent workload"""
        suggestions = []
        for agent in agents:
            workload = agent.metadata.get("current_workload", 0.5) if agent.metadata else 0.5
            availability = 1.0 - workload

            suggestions.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "match_score": availability,
                "workload": workload
            })

        suggestions.sort(key=lambda x: x["match_score"], reverse=True)
        return suggestions[:max_members]

    @staticmethod
    def _suggest_hybrid(
        task: Task,
        agents: List[Agent],
        max_members: int
    ) -> List[Dict[str, Any]]:
        """Suggest coalition using hybrid strategy"""
        required_caps = task.metadata.get("required_capabilities", []) if task.metadata else []

        suggestions = []
        for agent in agents:
            agent_caps = agent.metadata.get("capabilities", []) if agent.metadata else []
            workload = agent.metadata.get("current_workload", 0.5) if agent.metadata else 0.5

            # Calculate capability match
            if required_caps:
                matched = set(agent_caps) & set(required_caps)
                capability_score = len(matched) / len(required_caps)
            else:
                capability_score = 0.5

            # Calculate availability
            availability_score = 1.0 - workload

            # Hybrid score (weighted average)
            hybrid_score = (capability_score * 0.7) + (availability_score * 0.3)

            suggestions.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "match_score": hybrid_score,
                "capability_score": capability_score,
                "availability_score": availability_score
            })

        suggestions.sort(key=lambda x: x["match_score"], reverse=True)
        return suggestions[:max_members]

    @staticmethod
    def get_coalition(session: Session, coalition_id: int) -> Dict[str, Any]:
        """Get coalition details"""
        if coalition_id not in CoalitionFormation._coalitions:
            raise ValueError(f"Coalition {coalition_id} not found")

        return CoalitionFormation._coalitions[coalition_id]

    @staticmethod
    def list_coalitions(
        session: Session,
        status: Optional[str] = None,
        agent_id: Optional[int] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        List coalitions with optional filtering.

        Args:
            session: Database session
            status: Optional status filter
            agent_id: Optional agent ID filter (coalitions they're in)
            limit: Maximum coalitions to return

        Returns:
            List of coalitions
        """
        filtered_coalitions = []

        for coalition in CoalitionFormation._coalitions.values():
            # Filter by status
            if status and coalition["status"] != status:
                continue

            # Filter by agent membership
            if agent_id:
                is_member = any(
                    m["agent_id"] == agent_id
                    for m in coalition["members"]
                )
                if not is_member:
                    continue

            filtered_coalitions.append(coalition)

            if len(filtered_coalitions) >= limit:
                break

        return {
            "total": len(filtered_coalitions),
            "coalitions": filtered_coalitions
        }

    @staticmethod
    def get_coalition_statistics(session: Session) -> Dict[str, Any]:
        """
        Get coalition statistics.

        Args:
            session: Database session

        Returns:
            Coalition statistics
        """
        total_coalitions = len(CoalitionFormation._coalitions)

        # Count by status
        status_counts = {}
        for coalition in CoalitionFormation._coalitions.values():
            status = coalition["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        # Calculate average coalition size
        sizes = [len(c["members"]) for c in CoalitionFormation._coalitions.values()]
        avg_size = sum(sizes) / len(sizes) if sizes else 0

        # Count total members across all coalitions
        total_members = sum(sizes)

        # Count total tasks assigned
        total_tasks = sum(
            len(c["tasks"])
            for c in CoalitionFormation._coalitions.values()
        )

        # Count total achievements
        total_achievements = sum(
            len(c["achievements"])
            for c in CoalitionFormation._coalitions.values()
        )

        return {
            "total_coalitions": total_coalitions,
            "by_status": status_counts,
            "avg_coalition_size": avg_size,
            "total_unique_members": total_members,
            "total_tasks_assigned": total_tasks,
            "total_achievements": total_achievements,
            "active_coalitions": status_counts.get(CoalitionStatus.ACTIVE, 0)
        }
