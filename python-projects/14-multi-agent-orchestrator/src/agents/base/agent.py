"""
Base Agent Class

Abstract base class for all agents in the system.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from src.core.logging import logger


class AgentStatus(str, Enum):
    """Agent execution status"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class AgentConfig(BaseModel):
    """Agent configuration"""
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Agent description")
    model: str = Field(default="gpt-4", description="LLM model to use")
    temperature: float = Field(default=0.7, ge=0, le=2, description="LLM temperature")
    max_tokens: int = Field(default=2000, gt=0, description="Maximum tokens to generate")
    system_prompt: Optional[str] = Field(None, description="System prompt override")
    tools: List[str] = Field(default_factory=list, description="Available tools")
    memory_enabled: bool = Field(default=True, description="Enable memory")
    max_memory_items: int = Field(default=10, description="Max memory items to retain")
    timeout: int = Field(default=300, description="Execution timeout in seconds")
    retry_on_failure: bool = Field(default=True, description="Retry on failure")
    max_retries: int = Field(default=3, description="Maximum retry attempts")

    class Config:
        use_enum_values = True


class AgentContext(BaseModel):
    """Agent execution context"""
    task_id: Optional[str] = None
    workflow_id: Optional[str] = None
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    input_data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    parent_agent: Optional[str] = None
    depth: int = Field(default=0, description="Nesting depth for sub-agents")

    class Config:
        arbitrary_types_allowed = True


class AgentResult(BaseModel):
    """Agent execution result"""
    status: AgentStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    completed_at: Optional[datetime] = None
    execution_time: Optional[float] = None
    tokens_used: Optional[int] = None
    cost: Optional[float] = None

    class Config:
        use_enum_values = True


class BaseAgent(ABC):
    """
    Base Agent Class

    All agents must inherit from this class and implement the execute method.

    Features:
    - LLM integration
    - Memory management
    - Error handling and retries
    - Execution tracking
    - Tool integration
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize agent

        Args:
            config: Agent configuration
        """
        self.config = config
        self.status = AgentStatus.IDLE
        self.current_context: Optional[AgentContext] = None

        logger.info(f"Initialized agent: {self.config.name}")

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute agent with given context

        Args:
            context: Execution context

        Returns:
            AgentResult: Execution result
        """
        pass

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Any:
        """
        Process input and generate output

        Args:
            input_data: Input data to process

        Returns:
            Processed output
        """
        pass

    def get_system_prompt(self) -> str:
        """
        Get system prompt for the agent

        Returns:
            str: System prompt
        """
        if self.config.system_prompt:
            return self.config.system_prompt

        return f"""You are {self.config.name}, an AI agent.

Description: {self.config.description}

Your role is to process tasks efficiently and accurately. You have access to the following tools:
{', '.join(self.config.tools) if self.config.tools else 'No tools available'}

Always provide clear, actionable responses and explain your reasoning when necessary."""

    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """
        Validate input data

        Args:
            input_data: Input data to validate

        Returns:
            bool: True if valid
        """
        # Override in subclasses for custom validation
        return True

    async def prepare_context(self, context: AgentContext) -> AgentContext:
        """
        Prepare execution context

        Args:
            context: Raw context

        Returns:
            AgentContext: Prepared context
        """
        # Override in subclasses for custom preparation
        return context

    async def handle_error(self, error: Exception, context: AgentContext) -> AgentResult:
        """
        Handle execution error

        Args:
            error: Exception that occurred
            context: Execution context

        Returns:
            AgentResult: Error result
        """
        logger.error(f"Agent {self.config.name} error: {error}")

        return AgentResult(
            status=AgentStatus.FAILED,
            error=str(error),
            metadata={"error_type": type(error).__name__},
            started_at=datetime.utcnow()
        )

    async def post_process(self, result: AgentResult, context: AgentContext) -> AgentResult:
        """
        Post-process result before returning

        Args:
            result: Raw result
            context: Execution context

        Returns:
            AgentResult: Post-processed result
        """
        # Override in subclasses for custom post-processing
        return result

    def get_status(self) -> AgentStatus:
        """Get current agent status"""
        return self.status

    def get_config(self) -> AgentConfig:
        """Get agent configuration"""
        return self.config

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.config.name}, status={self.status})>"
