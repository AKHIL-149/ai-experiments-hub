"""
Agent Execution Model

Tracks individual agent execution records with results and metrics.
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


class ExecutionStatus(str, enum.Enum):
    """Agent execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class AgentExecution(Base):
    """
    Agent Execution Model

    Tracks individual agent execution records with full context,
    results, and performance metrics.
    """
    __tablename__ = "agent_executions"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Agent Reference
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    agent = relationship("Agent", backref="executions")

    # Task Reference (optional)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)
    task = relationship("Task", backref="agent_executions")

    # Workflow Reference (optional)
    workflow_id = Column(String(100), nullable=True, index=True)

    # User Reference (optional)
    user_id = Column(Integer, nullable=True, index=True)

    # Execution Context
    session_id = Column(String(100), nullable=True, index=True)
    parent_execution_id = Column(Integer, ForeignKey("agent_executions.id"), nullable=True)
    parent_execution = relationship(
        "AgentExecution",
        foreign_keys=[parent_execution_id],
        remote_side=[id],
        backref="child_executions"
    )

    # Input Data
    input_data = Column(JSON, nullable=False)
    input_metadata = Column(JSON, nullable=True)

    # Execution Status
    status = Column(
        Enum(ExecutionStatus),
        default=ExecutionStatus.PENDING,
        nullable=False,
        index=True
    )

    # Output Data
    output_data = Column(JSON, nullable=True)
    output_metadata = Column(JSON, nullable=True)

    # Error Information
    error_message = Column(Text, nullable=True)
    error_type = Column(String(255), nullable=True)
    error_traceback = Column(Text, nullable=True)

    # Performance Metrics
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    execution_time_seconds = Column(Float, nullable=True)

    # LLM Metrics
    tokens_used = Column(Integer, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    cost = Column(Float, default=0.0)

    # Configuration Used
    llm_provider = Column(String(50), nullable=True)
    llm_model = Column(String(100), nullable=True)
    temperature = Column(Float, nullable=True)
    max_tokens = Column(Integer, nullable=True)

    # Retry Information
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=0)
    is_retry = Column(Boolean, default=False)
    original_execution_id = Column(Integer, ForeignKey("agent_executions.id"), nullable=True)

    # Memory Snapshot
    memory_before = Column(JSON, nullable=True)
    memory_after = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AgentExecution(id={self.id}, agent_id={self.agent_id}, status='{self.status}')>"

    def to_dict(self) -> dict:
        """Convert execution to dictionary"""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "execution_time_seconds": self.execution_time_seconds,
            "tokens_used": self.tokens_used,
            "cost": self.cost,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @property
    def is_complete(self) -> bool:
        """Check if execution is complete (success or failure)"""
        return self.status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.CANCELLED
        ]

    @property
    def is_successful(self) -> bool:
        """Check if execution completed successfully"""
        return self.status == ExecutionStatus.COMPLETED

    def calculate_execution_time(self):
        """Calculate execution time if not set"""
        if self.started_at and self.completed_at and not self.execution_time_seconds:
            delta = self.completed_at - self.started_at
            self.execution_time_seconds = delta.total_seconds()
