"""
Agent Registry

Central registry for managing and discovering agents.
"""

from typing import Dict, List, Optional, Type
from enum import Enum

from src.agents.base import BaseAgent, AgentConfig
from src.agents.base.llm_provider import LLMProvider, create_llm_provider
from src.agents.specialized import (
    ResearchAgent,
    CodeAgent,
    DataAnalystAgent,
    WriterAgent,
    PlannerAgent
)
from src.core.logging import logger


class AgentType(str, Enum):
    """Available agent types"""
    RESEARCH = "research"
    CODE = "code"
    DATA_ANALYST = "data_analyst"
    WRITER = "writer"
    PLANNER = "planner"
    CUSTOM = "custom"


class AgentRegistry:
    """
    Agent Registry

    Features:
    - Register and discover agents
    - Create agent instances
    - Manage agent configurations
    - List available agents
    """

    def __init__(self):
        """Initialize agent registry"""
        self._agents: Dict[str, Type[BaseAgent]] = {}
        self._configs: Dict[str, AgentConfig] = {}
        self._instances: Dict[str, BaseAgent] = {}

        # Register built-in agents
        self._register_builtin_agents()

        logger.info("Agent registry initialized")

    def _register_builtin_agents(self):
        """Register built-in specialized agents"""
        self.register_agent("research", ResearchAgent)
        self.register_agent("code", CodeAgent)
        self.register_agent("data_analyst", DataAnalystAgent)
        self.register_agent("writer", WriterAgent)
        self.register_agent("planner", PlannerAgent)

    def register_agent(self, agent_type: str, agent_class: Type[BaseAgent]):
        """
        Register an agent type

        Args:
            agent_type: Unique identifier for the agent
            agent_class: Agent class
        """
        if agent_type in self._agents:
            logger.warning(f"Agent type '{agent_type}' already registered. Overwriting.")

        self._agents[agent_type] = agent_class
        logger.info(f"Registered agent: {agent_type}")

    def register_config(self, agent_type: str, config: AgentConfig):
        """
        Register a default configuration for an agent type

        Args:
            agent_type: Agent type identifier
            config: Agent configuration
        """
        self._configs[agent_type] = config
        logger.info(f"Registered config for agent: {agent_type}")

    def create_agent(
        self,
        agent_type: str,
        llm_provider: Optional[LLMProvider] = None,
        config: Optional[AgentConfig] = None,
        cache_instance: bool = False
    ) -> BaseAgent:
        """
        Create an agent instance

        Args:
            agent_type: Type of agent to create
            llm_provider: LLM provider (optional, will create default if not provided)
            config: Agent configuration (optional, will use registered config if available)
            cache_instance: Whether to cache the instance for reuse

        Returns:
            BaseAgent: Agent instance

        Raises:
            ValueError: If agent type is not registered
        """
        if agent_type not in self._agents:
            raise ValueError(
                f"Unknown agent type: {agent_type}. "
                f"Available: {list(self._agents.keys())}"
            )

        # Check if instance is cached
        if cache_instance and agent_type in self._instances:
            logger.debug(f"Returning cached instance of {agent_type}")
            return self._instances[agent_type]

        # Get agent class
        agent_class = self._agents[agent_type]

        # Get or create LLM provider
        if llm_provider is None:
            llm_provider = create_llm_provider(provider="openai", model="gpt-4")

        # Get configuration
        if config is None and agent_type in self._configs:
            config = self._configs[agent_type]

        # Create instance
        if config:
            agent = agent_class(llm_provider, config)
        else:
            agent = agent_class(llm_provider)

        # Cache if requested
        if cache_instance:
            self._instances[agent_type] = agent

        logger.info(f"Created agent instance: {agent_type}")
        return agent

    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        """
        Get cached agent instance

        Args:
            agent_type: Agent type

        Returns:
            Agent instance or None if not cached
        """
        return self._instances.get(agent_type)

    def list_agents(self) -> List[Dict[str, str]]:
        """
        List all registered agents

        Returns:
            List of agent information
        """
        agents = []
        for agent_type, agent_class in self._agents.items():
            # Try to get default config for description
            config = self._configs.get(agent_type)

            agents.append({
                "type": agent_type,
                "class": agent_class.__name__,
                "name": config.name if config else agent_class.__name__,
                "description": config.description if config else "No description available"
            })

        return agents

    def get_agent_info(self, agent_type: str) -> Optional[Dict[str, any]]:
        """
        Get detailed information about an agent type

        Args:
            agent_type: Agent type

        Returns:
            Agent information or None if not found
        """
        if agent_type not in self._agents:
            return None

        agent_class = self._agents[agent_type]
        config = self._configs.get(agent_type)

        return {
            "type": agent_type,
            "class": agent_class.__name__,
            "name": config.name if config else agent_class.__name__,
            "description": config.description if config else "No description available",
            "config": config.dict() if config else None,
            "is_cached": agent_type in self._instances
        }

    def clear_cache(self, agent_type: Optional[str] = None):
        """
        Clear cached agent instances

        Args:
            agent_type: Specific agent type to clear, or None to clear all
        """
        if agent_type:
            if agent_type in self._instances:
                del self._instances[agent_type]
                logger.info(f"Cleared cached instance: {agent_type}")
        else:
            self._instances.clear()
            logger.info("Cleared all cached agent instances")

    def is_registered(self, agent_type: str) -> bool:
        """Check if agent type is registered"""
        return agent_type in self._agents

    def __len__(self) -> int:
        """Get number of registered agents"""
        return len(self._agents)

    def __repr__(self) -> str:
        return f"<AgentRegistry(agents={len(self._agents)}, cached={len(self._instances)})>"


# Global registry instance
agent_registry = AgentRegistry()
