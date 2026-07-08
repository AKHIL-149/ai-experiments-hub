"""
Agent Role Management Service

Manages agent roles, responsibilities, capabilities, hierarchies, and dynamic role assignment.
Enables role-based task routing and performance tracking.
"""

from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict


class RoleType:
    """Predefined agent role types"""
    LEADER = "leader"
    COORDINATOR = "coordinator"
    SPECIALIST = "specialist"
    EXECUTOR = "executor"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    RESEARCHER = "researcher"
    DEVELOPER = "developer"
    TESTER = "tester"
    SUPPORT = "support"


class RoleLevel:
    """Role hierarchy levels"""
    EXECUTIVE = "executive"  # Level 5
    SENIOR = "senior"  # Level 4
    INTERMEDIATE = "intermediate"  # Level 3
    JUNIOR = "junior"  # Level 2
    ENTRY = "entry"  # Level 1


class AssignmentStatus:
    """Role assignment statuses"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    REVOKED = "revoked"


class AgentRole:
    """
    Agent Role Management System

    Manages role definitions, assignments, hierarchies, and performance tracking.
    Supports dynamic role assignment and role-based task routing.
    """

    # In-memory storage
    _role_definitions = {}
    _role_counter = 0

    _agent_roles = defaultdict(list)  # agent_id -> [role_assignments]
    _assignment_counter = 0

    _role_hierarchies = {}
    _role_permissions = defaultdict(list)  # role_id -> [permissions]
    _role_performance = defaultdict(list)  # assignment_id -> [performance_records]

    # Role level mapping
    LEVEL_RANKS = {
        RoleLevel.ENTRY: 1,
        RoleLevel.JUNIOR: 2,
        RoleLevel.INTERMEDIATE: 3,
        RoleLevel.SENIOR: 4,
        RoleLevel.EXECUTIVE: 5
    }

    @staticmethod
    def define_role(
        session,
        role_type: str,
        role_name: str,
        role_level: str,
        description: str,
        responsibilities: List[str],
        required_capabilities: List[str],
        optional_capabilities: Optional[List[str]] = None,
        min_experience_hours: float = 0,
        permissions: Optional[List[str]] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Define a new role.

        Args:
            session: Database session
            role_type: Type of role
            role_name: Name of role
            role_level: Hierarchy level
            description: Role description
            responsibilities: List of responsibilities
            required_capabilities: Required agent capabilities
            optional_capabilities: Optional capabilities
            min_experience_hours: Minimum experience required
            permissions: Role permissions
            metadata: Additional metadata

        Returns:
            Role definition
        """
        AgentRole._role_counter += 1
        role_id = f"role_{AgentRole._role_counter}"

        role_definition = {
            "id": role_id,
            "role_type": role_type,
            "role_name": role_name,
            "role_level": role_level,
            "description": description,
            "responsibilities": responsibilities,
            "required_capabilities": required_capabilities,
            "optional_capabilities": optional_capabilities or [],
            "min_experience_hours": min_experience_hours,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "is_active": True
        }

        AgentRole._role_definitions[role_id] = role_definition

        # Store permissions
        if permissions:
            AgentRole._role_permissions[role_id] = permissions

        return role_definition

    @staticmethod
    def assign_role(
        session,
        agent_id: int,
        role_id: str,
        assigned_by: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        assignment_reason: str = "",
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Assign role to an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            role_id: Role ID
            assigned_by: Agent ID who assigned the role
            start_date: Role start date
            end_date: Optional role end date
            assignment_reason: Reason for assignment
            metadata: Additional metadata

        Returns:
            Role assignment record
        """
        if role_id not in AgentRole._role_definitions:
            raise ValueError(f"Role {role_id} not found")

        role = AgentRole._role_definitions[role_id]

        # Check if agent already has this role
        existing_assignments = AgentRole._agent_roles[agent_id]
        for assignment in existing_assignments:
            if assignment["role_id"] == role_id and assignment["status"] == AssignmentStatus.ACTIVE:
                raise ValueError(f"Agent {agent_id} already has active role {role_id}")

        AgentRole._assignment_counter += 1
        assignment_id = f"assignment_{AgentRole._assignment_counter}"

        assignment = {
            "id": assignment_id,
            "agent_id": agent_id,
            "role_id": role_id,
            "role_name": role["role_name"],
            "role_type": role["role_type"],
            "role_level": role["role_level"],
            "assigned_by": assigned_by,
            "assignment_reason": assignment_reason,
            "status": AssignmentStatus.ACTIVE,
            "start_date": start_date or datetime.utcnow().isoformat(),
            "end_date": end_date,
            "metadata": metadata or {},
            "assigned_at": datetime.utcnow().isoformat(),
            "tasks_completed": 0,
            "performance_score": 0.0
        }

        AgentRole._agent_roles[agent_id].append(assignment)

        return assignment

    @staticmethod
    def revoke_role(
        session,
        assignment_id: str,
        revoked_by: Optional[int] = None,
        revocation_reason: str = ""
    ) -> dict:
        """
        Revoke a role assignment.

        Args:
            session: Database session
            assignment_id: Assignment ID
            revoked_by: Agent ID who revoked the role
            revocation_reason: Reason for revocation

        Returns:
            Updated assignment
        """
        # Find assignment
        assignment = None
        for agent_assignments in AgentRole._agent_roles.values():
            for a in agent_assignments:
                if a["id"] == assignment_id:
                    assignment = a
                    break
            if assignment:
                break

        if not assignment:
            raise ValueError(f"Assignment {assignment_id} not found")

        assignment["status"] = AssignmentStatus.REVOKED
        assignment["revoked_by"] = revoked_by
        assignment["revocation_reason"] = revocation_reason
        assignment["revoked_at"] = datetime.utcnow().isoformat()

        return assignment

    @staticmethod
    def update_role_assignment(
        session,
        assignment_id: str,
        status: Optional[str] = None,
        end_date: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Update role assignment.

        Args:
            session: Database session
            assignment_id: Assignment ID
            status: New status
            end_date: New end date
            metadata: Updated metadata

        Returns:
            Updated assignment
        """
        # Find assignment
        assignment = None
        for agent_assignments in AgentRole._agent_roles.values():
            for a in agent_assignments:
                if a["id"] == assignment_id:
                    assignment = a
                    break
            if assignment:
                break

        if not assignment:
            raise ValueError(f"Assignment {assignment_id} not found")

        if status:
            assignment["status"] = status
        if end_date:
            assignment["end_date"] = end_date
        if metadata:
            assignment["metadata"].update(metadata)

        assignment["updated_at"] = datetime.utcnow().isoformat()

        return assignment

    @staticmethod
    def record_role_performance(
        session,
        assignment_id: str,
        task_id: int,
        performance_score: float,
        quality_score: float,
        completion_time: float,
        notes: str = ""
    ) -> dict:
        """
        Record performance in a role.

        Args:
            session: Database session
            assignment_id: Assignment ID
            task_id: Task ID
            performance_score: Performance score (0-1)
            quality_score: Quality score (0-1)
            completion_time: Time taken
            notes: Additional notes

        Returns:
            Performance record
        """
        performance = {
            "assignment_id": assignment_id,
            "task_id": task_id,
            "performance_score": performance_score,
            "quality_score": quality_score,
            "completion_time": completion_time,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat()
        }

        AgentRole._role_performance[assignment_id].append(performance)

        # Update assignment stats
        for agent_assignments in AgentRole._agent_roles.values():
            for assignment in agent_assignments:
                if assignment["id"] == assignment_id:
                    assignment["tasks_completed"] += 1
                    # Recalculate average performance
                    records = AgentRole._role_performance[assignment_id]
                    avg_perf = sum(r["performance_score"] for r in records) / len(records)
                    assignment["performance_score"] = avg_perf
                    break

        return performance

    @staticmethod
    def promote_agent(
        session,
        agent_id: int,
        current_assignment_id: str,
        new_role_level: str,
        promoted_by: Optional[int] = None,
        promotion_reason: str = ""
    ) -> dict:
        """
        Promote agent to higher role level.

        Args:
            session: Database session
            agent_id: Agent ID
            current_assignment_id: Current role assignment
            new_role_level: New role level
            promoted_by: Agent ID who approved promotion
            promotion_reason: Reason for promotion

        Returns:
            Promotion record with new assignment
        """
        # Find current assignment
        current_assignment = None
        for assignment in AgentRole._agent_roles[agent_id]:
            if assignment["id"] == current_assignment_id:
                current_assignment = assignment
                break

        if not current_assignment:
            raise ValueError(f"Assignment {current_assignment_id} not found")

        current_level = current_assignment["role_level"]
        current_rank = AgentRole.LEVEL_RANKS.get(current_level, 0)
        new_rank = AgentRole.LEVEL_RANKS.get(new_role_level, 0)

        if new_rank <= current_rank:
            raise ValueError(f"New level {new_role_level} is not a promotion from {current_level}")

        # Complete current assignment
        current_assignment["status"] = AssignmentStatus.COMPLETED
        current_assignment["end_date"] = datetime.utcnow().isoformat()

        # Find or create new role definition at higher level
        role = AgentRole._role_definitions[current_assignment["role_id"]]
        new_role_name = f"{new_role_level.title()} {role['role_type'].title()}"

        # Create new role if needed
        new_role_id = None
        for rid, r in AgentRole._role_definitions.items():
            if r["role_type"] == role["role_type"] and r["role_level"] == new_role_level:
                new_role_id = rid
                break

        if not new_role_id:
            new_role = AgentRole.define_role(
                session=session,
                role_type=role["role_type"],
                role_name=new_role_name,
                role_level=new_role_level,
                description=f"{new_role_level.title()} level {role['role_type']}",
                responsibilities=role["responsibilities"],
                required_capabilities=role["required_capabilities"],
                optional_capabilities=role["optional_capabilities"]
            )
            new_role_id = new_role["id"]

        # Assign new role
        new_assignment = AgentRole.assign_role(
            session=session,
            agent_id=agent_id,
            role_id=new_role_id,
            assigned_by=promoted_by,
            assignment_reason=f"Promoted from {current_level}: {promotion_reason}"
        )

        return {
            "agent_id": agent_id,
            "previous_assignment": current_assignment,
            "new_assignment": new_assignment,
            "previous_level": current_level,
            "new_level": new_role_level,
            "promoted_by": promoted_by,
            "promotion_reason": promotion_reason,
            "promoted_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_agent_roles(
        session,
        agent_id: int,
        active_only: bool = True
    ) -> dict:
        """
        Get agent's roles.

        Args:
            session: Database session
            agent_id: Agent ID
            active_only: Only return active roles

        Returns:
            Agent's role assignments
        """
        assignments = AgentRole._agent_roles.get(agent_id, [])

        if active_only:
            assignments = [a for a in assignments if a["status"] == AssignmentStatus.ACTIVE]

        return {
            "agent_id": agent_id,
            "total_assignments": len(assignments),
            "active_roles": sum(1 for a in assignments if a["status"] == AssignmentStatus.ACTIVE),
            "assignments": assignments
        }

    @staticmethod
    def get_agents_by_role(
        session,
        role_id: str,
        active_only: bool = True
    ) -> dict:
        """
        Get all agents with a specific role.

        Args:
            session: Database session
            role_id: Role ID
            active_only: Only return active assignments

        Returns:
            Agents with this role
        """
        if role_id not in AgentRole._role_definitions:
            raise ValueError(f"Role {role_id} not found")

        agents = []
        for agent_id, assignments in AgentRole._agent_roles.items():
            for assignment in assignments:
                if assignment["role_id"] == role_id:
                    if not active_only or assignment["status"] == AssignmentStatus.ACTIVE:
                        agents.append({
                            "agent_id": agent_id,
                            "assignment": assignment
                        })

        return {
            "role_id": role_id,
            "role_name": AgentRole._role_definitions[role_id]["role_name"],
            "total_agents": len(agents),
            "agents": agents
        }

    @staticmethod
    def suggest_role_for_task(
        session,
        task_requirements: dict,
        required_level: Optional[str] = None
    ) -> dict:
        """
        Suggest best role for a task.

        Args:
            session: Database session
            task_requirements: Task requirements and capabilities needed
            required_level: Minimum role level required

        Returns:
            Suggested roles ranked by suitability
        """
        required_capabilities = task_requirements.get("capabilities", [])
        task_complexity = task_requirements.get("complexity", "medium")

        suggestions = []

        for role_id, role in AgentRole._role_definitions.items():
            if not role["is_active"]:
                continue

            # Check level requirement
            if required_level:
                role_rank = AgentRole.LEVEL_RANKS.get(role["role_level"], 0)
                required_rank = AgentRole.LEVEL_RANKS.get(required_level, 0)
                if role_rank < required_rank:
                    continue

            # Calculate capability match
            role_caps = set(role["required_capabilities"] + role["optional_capabilities"])
            required_caps = set(required_capabilities)

            if not required_caps:
                match_score = 0.5
            else:
                matched = role_caps.intersection(required_caps)
                match_score = len(matched) / len(required_caps)

            # Adjust by role level
            level_bonus = AgentRole.LEVEL_RANKS.get(role["role_level"], 1) * 0.05

            suitability_score = match_score + level_bonus

            suggestions.append({
                "role_id": role_id,
                "role_name": role["role_name"],
                "role_level": role["role_level"],
                "suitability_score": suitability_score,
                "capability_match": match_score,
                "matched_capabilities": list(role_caps.intersection(required_caps))
            })

        # Sort by suitability
        suggestions.sort(key=lambda x: x["suitability_score"], reverse=True)

        return {
            "task_requirements": task_requirements,
            "suggestions": suggestions[:5]  # Top 5
        }

    @staticmethod
    def get_role_hierarchy(session) -> dict:
        """
        Get role hierarchy visualization.

        Args:
            session: Database session

        Returns:
            Role hierarchy structure
        """
        hierarchy = defaultdict(lambda: defaultdict(list))

        for role_id, role in AgentRole._role_definitions.items():
            hierarchy[role["role_type"]][role["role_level"]].append(role)

        return {
            "hierarchy": dict(hierarchy),
            "levels": list(AgentRole.LEVEL_RANKS.keys())
        }

    @staticmethod
    def get_role_statistics(session) -> dict:
        """
        Get role system statistics.

        Args:
            session: Database session

        Returns:
            System statistics
        """
        total_roles = len(AgentRole._role_definitions)
        total_assignments = sum(len(assignments) for assignments in AgentRole._agent_roles.values())
        active_assignments = sum(
            sum(1 for a in assignments if a["status"] == AssignmentStatus.ACTIVE)
            for assignments in AgentRole._agent_roles.values()
        )

        # Count by role type
        by_type = defaultdict(int)
        for role in AgentRole._role_definitions.values():
            by_type[role["role_type"]] += 1

        # Count by level
        by_level = defaultdict(int)
        for assignments in AgentRole._agent_roles.values():
            for assignment in assignments:
                if assignment["status"] == AssignmentStatus.ACTIVE:
                    by_level[assignment["role_level"]] += 1

        return {
            "total_role_definitions": total_roles,
            "total_assignments": total_assignments,
            "active_assignments": active_assignments,
            "agents_with_roles": len(AgentRole._agent_roles),
            "roles_by_type": dict(by_type),
            "active_by_level": dict(by_level)
        }
