"""
Task model for orchestrating work across agents
"""

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum,
    ForeignKey, JSON, Float, Boolean
)
from sqlalchemy.orm import relationship

from src.core.database import Base


class TaskStatus(str, enum.Enum):
    """Task execution status"""
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    """Task priority levels"""
    CRITICAL = "critical"  # Priority 1-2
    HIGH = "high"          # Priority 3-4
    NORMAL = "normal"      # Priority 5-6
    LOW = "low"            # Priority 7-8
    MINIMAL = "minimal"    # Priority 9-10


class Task(Base):
    """
    Task model representing a unit of work in the multi-agent system.

    Tasks can have dependencies on other tasks, forming a DAG (Directed Acyclic Graph)
    for complex workflows.
    """
    __tablename__ = "tasks"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Task Information
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)

    # Task Type and Priority
    task_type = Column(String(50), nullable=False, index=True)
    priority = Column(Integer, default=5, index=True)  # 1 (highest) to 10 (lowest)

    # Status
    status = Column(
        Enum(TaskStatus),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True
    )

    # Agent Assignment
    assigned_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    assigned_agent = relationship(
        "Agent",
        foreign_keys=[assigned_agent_id],
        back_populates="assigned_tasks"
    )

    # Task Execution Details
    input_data = Column(JSON, nullable=True)  # Input parameters for the task
    output_data = Column(JSON, nullable=True)  # Results/output from task execution
    error_message = Column(Text, nullable=True)  # Error details if task fails

    # Context and Memory
    context = Column(JSON, nullable=True)  # Shared context across agents
    agent_messages = Column(JSON, nullable=True)  # Communication between agents

    # Progress Tracking
    progress_percentage = Column(Float, default=0.0)
    estimated_duration_seconds = Column(Integer, nullable=True)
    actual_duration_seconds = Column(Integer, nullable=True)

    # Approval Workflow
    requires_approval = Column(Boolean, default=False)
    approved_by = Column(String(255), nullable=True)
    approval_notes = Column(Text, nullable=True)

    # Cost Tracking
    estimated_cost = Column(Float, default=0.0)
    actual_cost = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Parent/Child Tasks (for task decomposition)
    parent_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    parent_task = relationship("Task", remote_side=[id], backref="subtasks")

    # Dependencies
    dependencies = relationship(
        "TaskDependency",
        foreign_keys="TaskDependency.task_id",
        back_populates="task"
    )

    dependent_tasks = relationship(
        "TaskDependency",
        foreign_keys="TaskDependency.depends_on_task_id",
        back_populates="depends_on_task"
    )

    def __repr__(self):
        return f"<Task(id={self.id}, title='{self.title}', status='{self.status}')>"

    def is_ready_to_execute(self) -> bool:
        """
        Check if all dependencies are completed and task is ready to execute
        """
        if self.status != TaskStatus.PENDING and self.status != TaskStatus.QUEUED:
            return False

        for dependency in self.dependencies:
            if dependency.depends_on_task.status != TaskStatus.COMPLETED:
                return False

        return True

    def get_dependency_ids(self) -> List[int]:
        """Get list of task IDs this task depends on"""
        return [dep.depends_on_task_id for dep in self.dependencies]


class TaskDependency(Base):
    """
    Task dependency relationship for DAG-based workflow orchestration.

    Defines that task_id depends on depends_on_task_id to be completed first.
    """
    __tablename__ = "task_dependencies"

    id = Column(Integer, primary_key=True, index=True)

    # Task that has the dependency
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    task = relationship("Task", foreign_keys=[task_id], back_populates="dependencies")

    # Task that must be completed first
    depends_on_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    depends_on_task = relationship("Task", foreign_keys=[depends_on_task_id], back_populates="dependent_tasks")

    # Dependency metadata
    dependency_type = Column(String(50), default="completion")  # completion, approval, etc.
    is_blocking = Column(Boolean, default=True)  # If False, soft dependency (can proceed with warning)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<TaskDependency(task_id={self.task_id}, depends_on={self.depends_on_task_id})>"
