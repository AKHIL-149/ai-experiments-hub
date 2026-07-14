"""
Workflow database model for tracking workflow metadata
"""

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum as SQLEnum, JSON, ForeignKey
from sqlalchemy.orm import relationship

from src.core.database import Base


class WorkflowStatus(str, enum.Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowType(str, enum.Enum):
    """Workflow type"""
    SIMPLE = "simple"
    DEFAULT = "default"
    CUSTOM = "custom"
    DAG = "dag"


class Workflow(Base):
    """Workflow model for tracking workflow execution metadata"""

    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    workflow_type = Column(SQLEnum(WorkflowType), default=WorkflowType.SIMPLE, nullable=False)
    status = Column(SQLEnum(WorkflowStatus), default=WorkflowStatus.PENDING, nullable=False, index=True)

    # Workflow definition (DAG structure, steps, etc.)
    definition = Column(JSON, nullable=True)

    # Execution metadata
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # User who created the workflow
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Additional metadata (configuration, parameters, etc.)
    extra_metadata = Column(JSON, nullable=True)

    # Execution results
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    # tasks relationship would be defined in task.py to avoid circular imports


class WorkflowStep(Base):
    """Individual steps within a workflow"""

    __tablename__ = "workflow_steps"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False, index=True)

    step_name = Column(String(255), nullable=False)
    step_type = Column(String(100), nullable=False)  # agent, decision, parallel, etc.
    step_order = Column(Integer, nullable=False)  # Execution order

    # Dependencies (parent step IDs)
    dependencies = Column(JSON, nullable=True)  # List of step IDs this depends on

    # Step configuration
    config = Column(JSON, nullable=True)

    # Execution status
    status = Column(String(50), default="pending", nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Step results
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
