"""
Agent Capability Management Service
Handles capability registration, matching, and discovery
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.models.agent import Agent, AgentRole, AgentStatus
from src.core.logging import logger


class CapabilityLevel:
    """Capability proficiency levels"""
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class CapabilityCategory:
    """Capability categories"""
    PROGRAMMING = "programming"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    ANALYSIS = "analysis"
    DESIGN = "design"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    SECURITY = "security"
    DATABASE = "database"
    API = "api"
    UI_UX = "ui_ux"
    MACHINE_LEARNING = "machine_learning"
    DATA_PROCESSING = "data_processing"
    CLOUD = "cloud"
    DEVOPS = "devops"


class AgentCapability:
    """
    Agent Capability Management Service

    Manages agent capabilities including registration, matching,
    scoring, and discovery.
    """

    @staticmethod
    def register_capability(
        session: Session,
        agent_id: int,
        capability: str,
        level: str = CapabilityLevel.INTERMEDIATE,
        category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Register a capability for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            capability: Capability name (e.g., "python", "docker")
            level: Proficiency level (basic, intermediate, advanced, expert)
            category: Capability category
            metadata: Additional capability metadata

        Returns:
            Capability information
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Initialize capabilities if not present
        if not agent.capabilities:
            agent.capabilities = []

        # Check if capability already exists
        existing_caps = [cap for cap in agent.capabilities if isinstance(cap, dict)]
        for cap in existing_caps:
            if cap.get("name") == capability:
                # Update existing capability
                cap["level"] = level
                cap["category"] = category
                cap["updated_at"] = datetime.utcnow().isoformat()
                if metadata:
                    cap["metadata"] = metadata
                session.commit()

                logger.info(f"Updated capability '{capability}' for agent {agent_id}")
                return cap

        # Add new capability
        new_capability = {
            "name": capability,
            "level": level,
            "category": category,
            "registered_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        agent.capabilities.append(new_capability)
        session.commit()

        logger.info(f"Registered capability '{capability}' ({level}) for agent {agent_id}")
        return new_capability

    @staticmethod
    def batch_register_capabilities(
        session: Session,
        agent_id: int,
        capabilities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Register multiple capabilities for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            capabilities: List of capability definitions

        Returns:
            List of registered capabilities
        """
        registered = []
        for cap_def in capabilities:
            cap = AgentCapability.register_capability(
                session=session,
                agent_id=agent_id,
                capability=cap_def["name"],
                level=cap_def.get("level", CapabilityLevel.INTERMEDIATE),
                category=cap_def.get("category"),
                metadata=cap_def.get("metadata")
            )
            registered.append(cap)

        return registered

    @staticmethod
    def remove_capability(
        session: Session,
        agent_id: int,
        capability: str
    ) -> bool:
        """
        Remove a capability from an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            capability: Capability name

        Returns:
            True if removed, False if not found
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.capabilities:
            return False

        # Filter out the capability
        original_count = len(agent.capabilities)
        agent.capabilities = [
            cap for cap in agent.capabilities
            if not (isinstance(cap, dict) and cap.get("name") == capability)
        ]

        removed = len(agent.capabilities) < original_count
        if removed:
            session.commit()
            logger.info(f"Removed capability '{capability}' from agent {agent_id}")

        return removed

    @staticmethod
    def get_agent_capabilities(
        session: Session,
        agent_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all capabilities for an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            List of capabilities
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.capabilities:
            return []

        return [cap for cap in agent.capabilities if isinstance(cap, dict)]

    @staticmethod
    def match_capabilities(
        session: Session,
        required_capabilities: List[str],
        min_level: str = CapabilityLevel.BASIC,
        role: Optional[AgentRole] = None,
        status: Optional[AgentStatus] = None
    ) -> List[Dict[str, Any]]:
        """
        Find agents that match required capabilities.

        Args:
            session: Database session
            required_capabilities: List of required capability names
            min_level: Minimum proficiency level
            role: Optional role filter
            status: Optional status filter

        Returns:
            List of matching agents with match scores
        """
        query = session.query(Agent)

        if role:
            query = query.filter(Agent.role == role)
        if status:
            query = query.filter(Agent.status == status)

        agents = query.all()
        matches = []

        for agent in agents:
            if not agent.capabilities:
                continue

            score, matched_caps = AgentCapability._calculate_match_score(
                agent_capabilities=agent.capabilities,
                required_capabilities=required_capabilities,
                min_level=min_level
            )

            if score > 0:
                matches.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "agent_role": agent.role.value,
                    "agent_status": agent.status.value,
                    "match_score": score,
                    "matched_capabilities": matched_caps,
                    "total_capabilities": len(agent.capabilities),
                    "match_percentage": score / len(required_capabilities) if required_capabilities else 0
                })

        # Sort by match score (descending)
        matches.sort(key=lambda x: x["match_score"], reverse=True)

        return matches

    @staticmethod
    def _calculate_match_score(
        agent_capabilities: List[Any],
        required_capabilities: List[str],
        min_level: str
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Calculate match score for agent capabilities.

        Args:
            agent_capabilities: Agent's capabilities
            required_capabilities: Required capabilities
            min_level: Minimum level

        Returns:
            Tuple of (score, matched_capabilities)
        """
        level_weights = {
            CapabilityLevel.BASIC: 1.0,
            CapabilityLevel.INTERMEDIATE: 2.0,
            CapabilityLevel.ADVANCED: 3.0,
            CapabilityLevel.EXPERT: 4.0
        }

        min_level_weight = level_weights.get(min_level, 1.0)

        agent_cap_dict = {}
        for cap in agent_capabilities:
            if isinstance(cap, dict):
                agent_cap_dict[cap.get("name")] = cap

        score = 0.0
        matched = []

        for req_cap in required_capabilities:
            if req_cap in agent_cap_dict:
                cap = agent_cap_dict[req_cap]
                cap_level = cap.get("level", CapabilityLevel.BASIC)
                cap_weight = level_weights.get(cap_level, 1.0)

                # Only count if meets minimum level
                if cap_weight >= min_level_weight:
                    # Score based on how much the capability exceeds minimum
                    score += cap_weight / min_level_weight
                    matched.append({
                        "name": req_cap,
                        "level": cap_level,
                        "category": cap.get("category")
                    })

        return score, matched

    @staticmethod
    def find_best_agent(
        session: Session,
        required_capabilities: List[str],
        min_level: str = CapabilityLevel.INTERMEDIATE,
        role: Optional[AgentRole] = None,
        prefer_available: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best agent for given capabilities.

        Args:
            session: Database session
            required_capabilities: Required capabilities
            min_level: Minimum proficiency level
            role: Optional role filter
            prefer_available: Prefer idle/available agents

        Returns:
            Best matching agent or None
        """
        # First try with available agents if preferred
        if prefer_available:
            matches = AgentCapability.match_capabilities(
                session=session,
                required_capabilities=required_capabilities,
                min_level=min_level,
                role=role,
                status=AgentStatus.IDLE
            )
            if matches:
                return matches[0]

        # Fallback to any status
        matches = AgentCapability.match_capabilities(
            session=session,
            required_capabilities=required_capabilities,
            min_level=min_level,
            role=role
        )

        return matches[0] if matches else None

    @staticmethod
    def get_capability_coverage(
        session: Session,
        capabilities: List[str]
    ) -> Dict[str, Any]:
        """
        Analyze capability coverage across all agents.

        Args:
            session: Database session
            capabilities: List of capabilities to check

        Returns:
            Coverage analysis
        """
        agents = session.query(Agent).all()

        coverage = {}
        for cap in capabilities:
            coverage[cap] = {
                "total_agents": 0,
                "by_level": {
                    CapabilityLevel.BASIC: 0,
                    CapabilityLevel.INTERMEDIATE: 0,
                    CapabilityLevel.ADVANCED: 0,
                    CapabilityLevel.EXPERT: 0
                },
                "agents": []
            }

        for agent in agents:
            if not agent.capabilities:
                continue

            for agent_cap in agent.capabilities:
                if not isinstance(agent_cap, dict):
                    continue

                cap_name = agent_cap.get("name")
                if cap_name in coverage:
                    coverage[cap_name]["total_agents"] += 1
                    level = agent_cap.get("level", CapabilityLevel.BASIC)
                    coverage[cap_name]["by_level"][level] += 1
                    coverage[cap_name]["agents"].append({
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "level": level
                    })

        return {
            "coverage": coverage,
            "summary": {
                "total_capabilities": len(capabilities),
                "covered_capabilities": sum(1 for c in coverage.values() if c["total_agents"] > 0),
                "uncovered_capabilities": sum(1 for c in coverage.values() if c["total_agents"] == 0),
                "coverage_percentage": sum(1 for c in coverage.values() if c["total_agents"] > 0) / len(capabilities) if capabilities else 0
            }
        }

    @staticmethod
    def get_all_capabilities(
        session: Session,
        category: Optional[str] = None,
        min_agents: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get all unique capabilities across agents.

        Args:
            session: Database session
            category: Optional category filter
            min_agents: Minimum number of agents with capability

        Returns:
            List of capabilities with statistics
        """
        agents = session.query(Agent).all()

        capability_map = {}

        for agent in agents:
            if not agent.capabilities:
                continue

            for cap in agent.capabilities:
                if not isinstance(cap, dict):
                    continue

                cap_name = cap.get("name")
                cap_category = cap.get("category")
                cap_level = cap.get("level", CapabilityLevel.BASIC)

                # Apply category filter
                if category and cap_category != category:
                    continue

                if cap_name not in capability_map:
                    capability_map[cap_name] = {
                        "name": cap_name,
                        "category": cap_category,
                        "agent_count": 0,
                        "levels": {
                            CapabilityLevel.BASIC: 0,
                            CapabilityLevel.INTERMEDIATE: 0,
                            CapabilityLevel.ADVANCED: 0,
                            CapabilityLevel.EXPERT: 0
                        },
                        "agents": []
                    }

                capability_map[cap_name]["agent_count"] += 1
                capability_map[cap_name]["levels"][cap_level] += 1
                capability_map[cap_name]["agents"].append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "level": cap_level
                })

        # Filter by minimum agents
        capabilities = [
            cap for cap in capability_map.values()
            if cap["agent_count"] >= min_agents
        ]

        # Sort by agent count (descending)
        capabilities.sort(key=lambda x: x["agent_count"], reverse=True)

        return capabilities

    @staticmethod
    def suggest_capabilities_for_agent(
        session: Session,
        agent_id: int,
        based_on_role: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Suggest capabilities for an agent based on role and gaps.

        Args:
            session: Database session
            agent_id: Agent ID
            based_on_role: Whether to base suggestions on agent role

        Returns:
            List of suggested capabilities
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Role-based capability templates
        role_capabilities = {
            AgentRole.RESEARCHER: [
                {"name": "web_search", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.ANALYSIS},
                {"name": "data_analysis", "level": CapabilityLevel.INTERMEDIATE, "category": CapabilityCategory.ANALYSIS},
                {"name": "information_extraction", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.ANALYSIS},
                {"name": "summarization", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.DOCUMENTATION}
            ],
            AgentRole.CODER: [
                {"name": "python", "level": CapabilityLevel.EXPERT, "category": CapabilityCategory.PROGRAMMING},
                {"name": "javascript", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.PROGRAMMING},
                {"name": "git", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.DEVOPS},
                {"name": "debugging", "level": CapabilityLevel.EXPERT, "category": CapabilityCategory.PROGRAMMING},
                {"name": "code_review", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.PROGRAMMING}
            ],
            AgentRole.TESTER: [
                {"name": "pytest", "level": CapabilityLevel.EXPERT, "category": CapabilityCategory.TESTING},
                {"name": "test_automation", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.TESTING},
                {"name": "bug_tracking", "level": CapabilityLevel.INTERMEDIATE, "category": CapabilityCategory.TESTING},
                {"name": "qa_analysis", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.TESTING}
            ],
            AgentRole.REVIEWER: [
                {"name": "code_review", "level": CapabilityLevel.EXPERT, "category": CapabilityCategory.PROGRAMMING},
                {"name": "static_analysis", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.ANALYSIS},
                {"name": "security_review", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.SECURITY},
                {"name": "best_practices", "level": CapabilityLevel.EXPERT, "category": CapabilityCategory.PROGRAMMING}
            ],
            AgentRole.WRITER: [
                {"name": "documentation", "level": CapabilityLevel.EXPERT, "category": CapabilityCategory.DOCUMENTATION},
                {"name": "technical_writing", "level": CapabilityLevel.EXPERT, "category": CapabilityCategory.DOCUMENTATION},
                {"name": "markdown", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.DOCUMENTATION},
                {"name": "api_documentation", "level": CapabilityLevel.ADVANCED, "category": CapabilityCategory.API}
            ]
        }

        # Get existing capabilities
        existing_caps = set()
        if agent.capabilities:
            for cap in agent.capabilities:
                if isinstance(cap, dict):
                    existing_caps.add(cap.get("name"))

        suggestions = []

        if based_on_role and agent.role in role_capabilities:
            # Suggest role-specific capabilities not yet possessed
            for cap in role_capabilities[agent.role]:
                if cap["name"] not in existing_caps:
                    suggestions.append({
                        **cap,
                        "reason": f"Recommended for {agent.role.value} role"
                    })

        # Get popular capabilities from similar agents
        similar_agents = session.query(Agent).filter(
            Agent.role == agent.role,
            Agent.id != agent_id
        ).all()

        capability_popularity = {}
        for similar_agent in similar_agents:
            if not similar_agent.capabilities:
                continue

            for cap in similar_agent.capabilities:
                if isinstance(cap, dict):
                    cap_name = cap.get("name")
                    if cap_name not in existing_caps:
                        if cap_name not in capability_popularity:
                            capability_popularity[cap_name] = {
                                "count": 0,
                                "avg_level": [],
                                "category": cap.get("category")
                            }
                        capability_popularity[cap_name]["count"] += 1
                        capability_popularity[cap_name]["avg_level"].append(cap.get("level"))

        # Add popular capabilities to suggestions
        for cap_name, data in capability_popularity.items():
            if data["count"] >= 2:  # At least 2 similar agents have it
                # Already in suggestions from role?
                if any(s["name"] == cap_name for s in suggestions):
                    continue

                # Calculate most common level
                level_counts = {}
                for level in data["avg_level"]:
                    level_counts[level] = level_counts.get(level, 0) + 1
                most_common_level = max(level_counts, key=level_counts.get)

                suggestions.append({
                    "name": cap_name,
                    "level": most_common_level,
                    "category": data["category"],
                    "reason": f"Used by {data['count']} similar {agent.role.value} agents"
                })

        return suggestions

    @staticmethod
    def validate_capability(
        capability: str,
        level: str,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate a capability definition.

        Args:
            capability: Capability name
            level: Proficiency level
            category: Optional category

        Returns:
            Validation result
        """
        valid_levels = [
            CapabilityLevel.BASIC,
            CapabilityLevel.INTERMEDIATE,
            CapabilityLevel.ADVANCED,
            CapabilityLevel.EXPERT
        ]

        valid_categories = [
            CapabilityCategory.PROGRAMMING,
            CapabilityCategory.TESTING,
            CapabilityCategory.DOCUMENTATION,
            CapabilityCategory.ANALYSIS,
            CapabilityCategory.DESIGN,
            CapabilityCategory.DEPLOYMENT,
            CapabilityCategory.MONITORING,
            CapabilityCategory.SECURITY,
            CapabilityCategory.DATABASE,
            CapabilityCategory.API,
            CapabilityCategory.UI_UX,
            CapabilityCategory.MACHINE_LEARNING,
            CapabilityCategory.DATA_PROCESSING,
            CapabilityCategory.CLOUD,
            CapabilityCategory.DEVOPS
        ]

        errors = []
        warnings = []

        # Validate capability name
        if not capability or not isinstance(capability, str):
            errors.append("Capability name must be a non-empty string")
        elif len(capability) > 100:
            errors.append("Capability name must be <= 100 characters")

        # Validate level
        if level not in valid_levels:
            errors.append(f"Invalid level '{level}'. Valid: {', '.join(valid_levels)}")

        # Validate category
        if category and category not in valid_categories:
            warnings.append(f"Unknown category '{category}'. Valid: {', '.join(valid_categories)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
