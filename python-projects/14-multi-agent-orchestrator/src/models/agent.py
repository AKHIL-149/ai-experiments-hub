"""
Agent model for AI agents in the orchestration system
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum,
    ForeignKey, JSON, Float, Boolean
)
from sqlalchemy.orm import relationship

from src.core.database import Base


class AgentRole(str, enum.Enum):
    """Agent specialization roles"""
    RESEARCHER = "researcher"      # Gathers information and context
    CODER = "coder"               # Implements solutions and writes code
    REVIEWER = "reviewer"         # Reviews code quality and suggests improvements
    TESTER = "tester"            # Creates and runs tests
    WRITER = "writer"            # Generates documentation
    COORDINATOR = "coordinator"   # Orchestrates other agents


class AgentStatus(str, enum.Enum):
    """Agent execution status"""
    IDLE = "idle"
    BUSY = "busy"
    WAITING = "waiting"
    ERROR = "error"
    OFFLINE = "offline"


class Agent(Base):
    """
    Agent model representing an AI agent with specific role and capabilities.

    Each agent can work on tasks, communicate with other agents, and maintain
    its own state and memory.
    """
    __tablename__ = "agents"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Agent Identity
    name = Column(String(255), nullable=False, unique=True, index=True)
    role = Column(
        Enum(AgentRole),
        nullable=False,
        index=True
    )

    # Agent Description
    description = Column(Text, nullable=True)
    capabilities = Column(JSON, nullable=True)  # List of specific capabilities

    # Status
    status = Column(
        Enum(AgentStatus),
        default=AgentStatus.IDLE,
        nullable=False,
        index=True
    )

    # Current Work
    current_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    current_task = relationship(
        "Task",
        foreign_keys=[current_task_id],
        post_update=True
    )

    # Assigned Tasks
    assigned_tasks = relationship(
        "Task",
        foreign_keys="Task.assigned_agent_id",
        back_populates="assigned_agent"
    )

    # LLM Configuration
    llm_provider = Column(String(50), default="openai")  # openai, anthropic
    llm_model = Column(String(100), nullable=True)  # gpt-4-turbo-preview, claude-3-sonnet
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=4000)

    # System Prompt
    system_prompt = Column(Text, nullable=True)  # Custom system prompt for this agent

    # Agent Memory and Context
    memory = Column(JSON, nullable=True)  # Agent's working memory
    long_term_memory = Column(JSON, nullable=True)  # Persistent knowledge
    conversation_history = Column(JSON, nullable=True)  # Recent interactions

    # Performance Metrics
    tasks_completed = Column(Integer, default=0)
    tasks_failed = Column(Integer, default=0)
    total_execution_time_seconds = Column(Integer, default=0)
    average_task_duration_seconds = Column(Float, default=0.0)

    # Cost Tracking
    total_cost = Column(Float, default=0.0)
    total_tokens_used = Column(Integer, default=0)

    # Configuration
    is_active = Column(Boolean, default=True)
    max_concurrent_tasks = Column(Integer, default=1)
    timeout_seconds = Column(Integer, default=300)
    max_iterations = Column(Integer, default=10)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_active_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Agent(id={self.id}, name='{self.name}', role='{self.role}', status='{self.status}')>"

    def is_available(self) -> bool:
        """Check if agent is available to take on new tasks"""
        return (
            self.is_active and
            self.status == AgentStatus.IDLE and
            self.current_task_id is None
        )

    def update_metrics(self, task_duration: int, success: bool, cost: float = 0.0):
        """Update agent performance metrics after task completion"""
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1

        self.total_execution_time_seconds += task_duration

        # Update average duration
        total_tasks = self.tasks_completed + self.tasks_failed
        if total_tasks > 0:
            self.average_task_duration_seconds = self.total_execution_time_seconds / total_tasks

        self.total_cost += cost
        self.last_active_at = datetime.utcnow()
