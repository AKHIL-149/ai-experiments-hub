"""
Agent Collaboration Service
Handles multi-agent collaboration, team formation, and coordinated task execution
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.models.agent import Agent, AgentStatus
from src.models.task import Task, TaskStatus
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.core.logging import logger


class CollaborationPattern:
    """Collaboration execution patterns"""
    PARALLEL = "parallel"          # Agents work simultaneously
    SEQUENTIAL = "sequential"      # Agents work in sequence
    HIERARCHICAL = "hierarchical"  # Leader-worker pattern
    PEER_TO_PEER = "peer_to_peer" # Equal collaboration


class CollaborationRole:
    """Agent roles in collaboration"""
    LEADER = "leader"
    CONTRIBUTOR = "contributor"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"


class AgentCollaboration:
    """
    Agent Collaboration Service

    Manages multi-agent collaboration, team formation, and coordinated execution.
    """

    @staticmethod
    def create_collaboration(
        session: Session,
        name: str,
        task_id: int,
        agent_ids: List[int],
        pattern: str = CollaborationPattern.PARALLEL,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new collaboration session.

        Args:
            session: Database session
            name: Collaboration name
            task_id: Task being collaborated on
            agent_ids: List of agent IDs
            pattern: Collaboration pattern
            description: Optional description

        Returns:
            Collaboration information
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Validate agents exist
        agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
        if len(agents) != len(agent_ids):
            raise ValueError("One or more agents not found")

        # Initialize collaboration in task metadata
        if not task.metadata:
            task.metadata = {}

        if "collaborations" not in task.metadata:
            task.metadata["collaborations"] = []

        collaboration_id = len(task.metadata["collaborations"]) + 1

        collaboration = {
            "id": collaboration_id,
            "name": name,
            "description": description,
            "pattern": pattern,
            "agent_ids": agent_ids,
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "roles": {},
            "handoffs": [],
            "metrics": {
                "total_agents": len(agent_ids),
                "completed_handoffs": 0,
                "active_agents": 0
            }
        }

        task.metadata["collaborations"].append(collaboration)
        session.commit()

        logger.info(f"Created collaboration '{name}' for task {task_id} with {len(agent_ids)} agents")

        return {
            "collaboration_id": collaboration_id,
            "task_id": task_id,
            "collaboration": collaboration
        }

    @staticmethod
    def assign_role(
        session: Session,
        task_id: int,
        collaboration_id: int,
        agent_id: int,
        role: str
    ) -> Dict[str, Any]:
        """
        Assign a role to an agent in a collaboration.

        Args:
            session: Database session
            task_id: Task ID
            collaboration_id: Collaboration ID
            agent_id: Agent ID
            role: Role to assign

        Returns:
            Updated collaboration
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.metadata or "collaborations" not in task.metadata:
            raise ValueError(f"No collaborations found for task {task_id}")

        collaboration = None
        for collab in task.metadata["collaborations"]:
            if collab["id"] == collaboration_id:
                collaboration = collab
                break

        if not collaboration:
            raise ValueError(f"Collaboration {collaboration_id} not found")

        if agent_id not in collaboration["agent_ids"]:
            raise ValueError(f"Agent {agent_id} is not part of this collaboration")

        collaboration["roles"][str(agent_id)] = role
        collaboration["updated_at"] = datetime.utcnow().isoformat()

        session.commit()

        logger.info(f"Assigned role '{role}' to agent {agent_id} in collaboration {collaboration_id}")

        return collaboration

    @staticmethod
    def create_handoff(
        session: Session,
        task_id: int,
        collaboration_id: int,
        from_agent_id: int,
        to_agent_id: int,
        handoff_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a handoff between agents in a collaboration.

        Args:
            session: Database session
            task_id: Task ID
            collaboration_id: Collaboration ID
            from_agent_id: Source agent
            to_agent_id: Target agent
            handoff_type: Type of handoff (work/review/approval)
            context: Optional context data

        Returns:
            Handoff information
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.metadata or "collaborations" not in task.metadata:
            raise ValueError(f"No collaborations found for task {task_id}")

        collaboration = None
        for collab in task.metadata["collaborations"]:
            if collab["id"] == collaboration_id:
                collaboration = collab
                break

        if not collaboration:
            raise ValueError(f"Collaboration {collaboration_id} not found")

        if from_agent_id not in collaboration["agent_ids"]:
            raise ValueError(f"Agent {from_agent_id} is not part of this collaboration")

        if to_agent_id not in collaboration["agent_ids"]:
            raise ValueError(f"Agent {to_agent_id} is not part of this collaboration")

        handoff = {
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "handoff_type": handoff_type,
            "context": context or {},
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None
        }

        collaboration["handoffs"].append(handoff)
        collaboration["updated_at"] = datetime.utcnow().isoformat()

        session.commit()

        logger.info(f"Created {handoff_type} handoff from agent {from_agent_id} to {to_agent_id}")

        return handoff

    @staticmethod
    def complete_handoff(
        session: Session,
        task_id: int,
        collaboration_id: int,
        from_agent_id: int,
        to_agent_id: int
    ) -> Dict[str, Any]:
        """
        Mark a handoff as completed.

        Args:
            session: Database session
            task_id: Task ID
            collaboration_id: Collaboration ID
            from_agent_id: Source agent
            to_agent_id: Target agent

        Returns:
            Updated handoff
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.metadata or "collaborations" not in task.metadata:
            raise ValueError(f"No collaborations found for task {task_id}")

        collaboration = None
        for collab in task.metadata["collaborations"]:
            if collab["id"] == collaboration_id:
                collaboration = collab
                break

        if not collaboration:
            raise ValueError(f"Collaboration {collaboration_id} not found")

        # Find pending handoff
        handoff = None
        for h in collaboration["handoffs"]:
            if (h["from_agent_id"] == from_agent_id and
                h["to_agent_id"] == to_agent_id and
                h["status"] == "pending"):
                handoff = h
                break

        if not handoff:
            raise ValueError(f"No pending handoff found from {from_agent_id} to {to_agent_id}")

        handoff["status"] = "completed"
        handoff["completed_at"] = datetime.utcnow().isoformat()

        collaboration["metrics"]["completed_handoffs"] += 1
        collaboration["updated_at"] = datetime.utcnow().isoformat()

        session.commit()

        logger.info(f"Completed handoff from agent {from_agent_id} to {to_agent_id}")

        return handoff

    @staticmethod
    def get_collaboration(
        session: Session,
        task_id: int,
        collaboration_id: int
    ) -> Dict[str, Any]:
        """
        Get collaboration details.

        Args:
            session: Database session
            task_id: Task ID
            collaboration_id: Collaboration ID

        Returns:
            Collaboration information
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.metadata or "collaborations" not in task.metadata:
            raise ValueError(f"No collaborations found for task {task_id}")

        collaboration = None
        for collab in task.metadata["collaborations"]:
            if collab["id"] == collaboration_id:
                collaboration = collab
                break

        if not collaboration:
            raise ValueError(f"Collaboration {collaboration_id} not found")

        # Enrich with agent details
        agents = session.query(Agent).filter(Agent.id.in_(collaboration["agent_ids"])).all()

        collaboration_details = {
            **collaboration,
            "agents": [
                {
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "agent_role": agent.role.value,
                    "agent_status": agent.status.value,
                    "collaboration_role": collaboration["roles"].get(str(agent.id), "contributor")
                }
                for agent in agents
            ]
        }

        return collaboration_details

    @staticmethod
    def list_collaborations(
        session: Session,
        task_id: Optional[int] = None,
        agent_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List collaborations with optional filters.

        Args:
            session: Database session
            task_id: Optional task ID filter
            agent_id: Optional agent ID filter
            status: Optional status filter

        Returns:
            List of collaborations
        """
        query = session.query(Task).filter(Task.metadata.isnot(None))

        if task_id:
            query = query.filter(Task.id == task_id)

        tasks = query.all()
        collaborations = []

        for task in tasks:
            if "collaborations" not in task.metadata:
                continue

            for collab in task.metadata["collaborations"]:
                # Apply filters
                if agent_id and agent_id not in collab["agent_ids"]:
                    continue

                if status and collab["status"] != status:
                    continue

                collaborations.append({
                    "task_id": task.id,
                    "task_title": task.title,
                    "collaboration": collab
                })

        return collaborations

    @staticmethod
    def form_team(
        session: Session,
        task_id: int,
        required_roles: List[str],
        max_agents: int = 5
    ) -> Dict[str, Any]:
        """
        Automatically form a team for a task based on required roles.

        Args:
            session: Database session
            task_id: Task ID
            required_roles: List of required agent roles
            max_agents: Maximum team size

        Returns:
            Team formation result
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Find available agents for each role
        team = []
        role_coverage = {}

        for role in required_roles:
            agents = session.query(Agent).filter(
                and_(
                    Agent.role == role,
                    Agent.status == AgentStatus.ACTIVE
                )
            ).limit(max_agents).all()

            if agents:
                # Pick first available agent for this role
                selected_agent = agents[0]
                team.append({
                    "agent_id": selected_agent.id,
                    "agent_name": selected_agent.name,
                    "role": role
                })
                role_coverage[role] = True
            else:
                role_coverage[role] = False

        # Check if all roles are covered
        missing_roles = [role for role, covered in role_coverage.items() if not covered]

        return {
            "task_id": task_id,
            "task_title": task.title,
            "required_roles": required_roles,
            "team": team,
            "team_size": len(team),
            "role_coverage": role_coverage,
            "missing_roles": missing_roles,
            "is_complete": len(missing_roles) == 0
        }

    @staticmethod
    def get_agent_collaborations(
        session: Session,
        agent_id: int,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all collaborations for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            status: Optional status filter

        Returns:
            List of collaborations
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        return AgentCollaboration.list_collaborations(
            session=session,
            agent_id=agent_id,
            status=status
        )

    @staticmethod
    def update_collaboration_status(
        session: Session,
        task_id: int,
        collaboration_id: int,
        status: str
    ) -> Dict[str, Any]:
        """
        Update collaboration status.

        Args:
            session: Database session
            task_id: Task ID
            collaboration_id: Collaboration ID
            status: New status (active/paused/completed/cancelled)

        Returns:
            Updated collaboration
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.metadata or "collaborations" not in task.metadata:
            raise ValueError(f"No collaborations found for task {task_id}")

        collaboration = None
        for collab in task.metadata["collaborations"]:
            if collab["id"] == collaboration_id:
                collaboration = collab
                break

        if not collaboration:
            raise ValueError(f"Collaboration {collaboration_id} not found")

        collaboration["status"] = status
        collaboration["updated_at"] = datetime.utcnow().isoformat()

        session.commit()

        logger.info(f"Updated collaboration {collaboration_id} status to {status}")

        return collaboration

    @staticmethod
    def get_collaboration_metrics(
        session: Session,
        task_id: int,
        collaboration_id: int
    ) -> Dict[str, Any]:
        """
        Get collaboration performance metrics.

        Args:
            session: Database session
            task_id: Task ID
            collaboration_id: Collaboration ID

        Returns:
            Collaboration metrics
        """
        collaboration = AgentCollaboration.get_collaboration(
            session=session,
            task_id=task_id,
            collaboration_id=collaboration_id
        )

        # Calculate additional metrics
        total_handoffs = len(collaboration["handoffs"])
        completed_handoffs = collaboration["metrics"]["completed_handoffs"]
        pending_handoffs = total_handoffs - completed_handoffs

        # Count active agents (agents with recent activity)
        active_agents = len([
            agent for agent in collaboration["agents"]
            if agent["agent_status"] in ["active", "busy"]
        ])

        # Calculate handoff success rate
        handoff_success_rate = (
            (completed_handoffs / total_handoffs * 100)
            if total_handoffs > 0
            else 0
        )

        metrics = {
            "collaboration_id": collaboration_id,
            "task_id": task_id,
            "total_agents": collaboration["metrics"]["total_agents"],
            "active_agents": active_agents,
            "total_handoffs": total_handoffs,
            "completed_handoffs": completed_handoffs,
            "pending_handoffs": pending_handoffs,
            "handoff_success_rate": handoff_success_rate,
            "pattern": collaboration["pattern"],
            "status": collaboration["status"],
            "duration_seconds": None
        }

        # Calculate duration if collaboration is completed
        if collaboration["status"] == "completed":
            created_at = datetime.fromisoformat(collaboration["created_at"])
            updated_at = datetime.fromisoformat(collaboration["updated_at"])
            duration = (updated_at - created_at).total_seconds()
            metrics["duration_seconds"] = duration

        return metrics

    @staticmethod
    def get_pending_handoffs(
        session: Session,
        agent_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all pending handoffs for an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            List of pending handoffs
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        tasks = session.query(Task).filter(Task.metadata.isnot(None)).all()
        pending_handoffs = []

        for task in tasks:
            if "collaborations" not in task.metadata:
                continue

            for collab in task.metadata["collaborations"]:
                if agent_id not in collab["agent_ids"]:
                    continue

                for handoff in collab["handoffs"]:
                    if (handoff["to_agent_id"] == agent_id and
                        handoff["status"] == "pending"):
                        pending_handoffs.append({
                            "task_id": task.id,
                            "task_title": task.title,
                            "collaboration_id": collab["id"],
                            "collaboration_name": collab["name"],
                            "from_agent_id": handoff["from_agent_id"],
                            "handoff_type": handoff["handoff_type"],
                            "context": handoff["context"],
                            "created_at": handoff["created_at"]
                        })

        return pending_handoffs

    @staticmethod
    def sync_collaboration_state(
        session: Session,
        task_id: int,
        collaboration_id: int
    ) -> Dict[str, Any]:
        """
        Synchronize collaboration state with agent executions.

        Args:
            session: Database session
            task_id: Task ID
            collaboration_id: Collaboration ID

        Returns:
            Updated collaboration state
        """
        collaboration = AgentCollaboration.get_collaboration(
            session=session,
            task_id=task_id,
            collaboration_id=collaboration_id
        )

        # Get executions for this task
        executions = session.query(AgentExecution).filter(
            and_(
                AgentExecution.task_id == task_id,
                AgentExecution.agent_id.in_(collaboration["agent_ids"])
            )
        ).all()

        # Update active agents count
        active_count = len([
            exec for exec in executions
            if exec.status == ExecutionStatus.RUNNING
        ])

        task = session.query(Task).filter(Task.id == task_id).first()
        for collab in task.metadata["collaborations"]:
            if collab["id"] == collaboration_id:
                collab["metrics"]["active_agents"] = active_count
                collab["updated_at"] = datetime.utcnow().isoformat()
                break

        session.commit()

        return AgentCollaboration.get_collaboration(
            session=session,
            task_id=task_id,
            collaboration_id=collaboration_id
        )
