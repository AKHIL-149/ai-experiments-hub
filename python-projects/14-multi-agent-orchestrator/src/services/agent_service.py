"""
Agent service for managing agent operations and lifecycle
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.models.agent import Agent, AgentRole, AgentStatus
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.agents import agent_registry, AgentConfig, AgentContext, AgentResult, AgentExecutor
from src.agents.base.llm_provider import create_llm_provider
from src.core.logging import logger
from src.core.exceptions import AgentNotFoundError, ValidationError


def _run_async(coro):
    """
    Helper to run async functions from sync code

    Args:
        coro: Coroutine to run

    Returns:
        Result of coroutine
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        # If loop is running, create task without waiting
        asyncio.create_task(coro)
        return None
    else:
        # If loop is not running, run until complete
        return loop.run_until_complete(coro)


class AgentService:
    """Service for agent management and operations"""

    @staticmethod
    def create_agent(
        session: Session,
        name: str,
        role: AgentRole,
        description: Optional[str] = None,
        llm_provider: str = "openai",
        llm_model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> Agent:
        """
        Create a new agent

        Args:
            session: Database session
            name: Agent name
            role: Agent role
            description: Agent description
            llm_provider: LLM provider (openai, anthropic)
            llm_model: LLM model name
            system_prompt: Custom system prompt
            temperature: LLM temperature
            max_tokens: Max tokens for LLM

        Returns:
            Agent: Created agent

        Raises:
            ValidationError: If validation fails
        """
        try:
            # Check if agent with same name exists
            existing = session.query(Agent).filter(Agent.name == name).first()
            if existing:
                raise ValidationError(f"Agent with name '{name}' already exists")

            # Set default model based on provider
            if not llm_model:
                llm_model = "gpt-4-turbo-preview" if llm_provider == "openai" else "claude-3-sonnet-20240229"

            # Create agent
            agent = Agent(
                name=name,
                role=role,
                description=description,
                llm_provider=llm_provider,
                llm_model=llm_model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                status=AgentStatus.IDLE,
                is_active=True
            )

            session.add(agent)
            session.commit()
            session.refresh(agent)

            logger.info(f"Created agent: {name} ({role})")

            return agent

        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create agent: {e}")
            raise

    @staticmethod
    def get_agent_by_id(session: Session, agent_id: int) -> Agent:
        """
        Get agent by ID

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Agent: Agent instance

        Raises:
            AgentNotFoundError: If agent not found
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            raise AgentNotFoundError(agent_id)

        return agent

    @staticmethod
    def get_agents_by_role(
        session: Session,
        role: AgentRole,
        only_active: bool = True
    ) -> List[Agent]:
        """
        Get all agents with specific role

        Args:
            session: Database session
            role: Agent role
            only_active: Only return active agents

        Returns:
            list: Agents with specified role
        """
        query = session.query(Agent).filter(Agent.role == role)

        if only_active:
            query = query.filter(Agent.is_active == True)

        return query.all()

    @staticmethod
    def get_available_agents(
        session: Session,
        role: Optional[AgentRole] = None
    ) -> List[Agent]:
        """
        Get all available (idle) agents

        Args:
            session: Database session
            role: Optional role filter

        Returns:
            list: Available agents
        """
        query = session.query(Agent).filter(
            and_(
                Agent.is_active == True,
                Agent.status == AgentStatus.IDLE,
                Agent.current_task_id == None
            )
        )

        if role:
            query = query.filter(Agent.role == role)

        return query.all()

    @staticmethod
    def assign_agent_to_task(
        session: Session,
        agent_id: int,
        task_id: int
    ) -> Agent:
        """
        Assign agent to a task

        Args:
            session: Database session
            agent_id: Agent ID
            task_id: Task ID

        Returns:
            Agent: Updated agent

        Raises:
            AgentNotFoundError: If agent not found
            ValidationError: If agent is not available
        """
        agent = AgentService.get_agent_by_id(session, agent_id)

        if not agent.is_available():
            raise ValidationError(
                f"Agent {agent_id} is not available (status: {agent.status})"
            )

        agent.current_task_id = task_id
        agent.status = AgentStatus.BUSY
        agent.last_active_at = datetime.utcnow()

        session.commit()
        session.refresh(agent)

        logger.info(f"Assigned agent {agent_id} to task {task_id}")

        # Send WebSocket notification
        try:
            from src.core.websocket import notify_agent_update
            _run_async(notify_agent_update(
                agent_id=agent.id,
                event_type="assigned",
                data={
                    "task_id": task_id,
                    "status": agent.status.value,
                    "name": agent.name,
                    "role": agent.role.value
                }
            ))
        except Exception as e:
            logger.warning(f"Failed to send WebSocket notification: {e}")

        return agent

    @staticmethod
    def update_agent_status(
        session: Session,
        agent_id: int,
        status: AgentStatus,
        current_task_id: Optional[int] = None
    ) -> Agent:
        """
        Update agent status

        Args:
            session: Database session
            agent_id: Agent ID
            status: New status
            current_task_id: Current task ID (optional)

        Returns:
            Agent: Updated agent

        Raises:
            AgentNotFoundError: If agent not found
        """
        agent = AgentService.get_agent_by_id(session, agent_id)

        agent.status = status
        if current_task_id is not None:
            agent.current_task_id = current_task_id

        # If agent becomes idle, clear current task
        if status == AgentStatus.IDLE:
            agent.current_task_id = None

        agent.last_active_at = datetime.utcnow()

        session.commit()
        session.refresh(agent)

        logger.info(f"Updated agent {agent_id} status to {status}")

        # Send WebSocket notification
        try:
            from src.core.websocket import notify_agent_update
            _run_async(notify_agent_update(
                agent_id=agent.id,
                event_type="status_changed",
                data={
                    "status": agent.status.value,
                    "current_task_id": agent.current_task_id,
                    "name": agent.name,
                    "role": agent.role.value
                }
            ))
        except Exception as e:
            logger.warning(f"Failed to send WebSocket notification: {e}")

        return agent

    @staticmethod
    def update_agent_metrics(
        session: Session,
        agent_id: int,
        task_duration: int,
        success: bool,
        cost: float = 0.0,
        tokens_used: int = 0
    ) -> Agent:
        """
        Update agent performance metrics after task completion

        Args:
            session: Database session
            agent_id: Agent ID
            task_duration: Task duration in seconds
            success: Whether task succeeded
            cost: Task cost
            tokens_used: Tokens used

        Returns:
            Agent: Updated agent

        Raises:
            AgentNotFoundError: If agent not found
        """
        agent = AgentService.get_agent_by_id(session, agent_id)

        # Update metrics using model method
        agent.update_metrics(task_duration, success, cost)
        agent.total_tokens_used += tokens_used

        session.commit()
        session.refresh(agent)

        logger.info(
            f"Updated metrics for agent {agent_id}: "
            f"duration={task_duration}s, success={success}, cost=${cost:.4f}"
        )

        return agent

    @staticmethod
    def get_agent_metrics(session: Session, agent_id: int) -> Dict[str, Any]:
        """
        Get agent performance metrics

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            dict: Agent metrics

        Raises:
            AgentNotFoundError: If agent not found
        """
        agent = AgentService.get_agent_by_id(session, agent_id)

        total_tasks = agent.tasks_completed + agent.tasks_failed
        success_rate = (agent.tasks_completed / total_tasks * 100) if total_tasks > 0 else 0

        return {
            "agent_id": agent.id,
            "name": agent.name,
            "role": agent.role.value,
            "tasks_completed": agent.tasks_completed,
            "tasks_failed": agent.tasks_failed,
            "total_tasks": total_tasks,
            "success_rate": round(success_rate, 2),
            "average_duration_seconds": agent.average_task_duration_seconds,
            "total_execution_time_seconds": agent.total_execution_time_seconds,
            "total_cost": agent.total_cost,
            "total_tokens_used": agent.total_tokens_used,
            "last_active_at": agent.last_active_at.isoformat() if agent.last_active_at else None
        }

    @staticmethod
    def deactivate_agent(session: Session, agent_id: int) -> Agent:
        """
        Deactivate an agent

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Agent: Deactivated agent

        Raises:
            AgentNotFoundError: If agent not found
            ValidationError: If agent is busy
        """
        agent = AgentService.get_agent_by_id(session, agent_id)

        if agent.status == AgentStatus.BUSY:
            raise ValidationError("Cannot deactivate agent while busy")

        agent.is_active = False
        agent.status = AgentStatus.OFFLINE

        session.commit()
        session.refresh(agent)

        logger.info(f"Deactivated agent {agent_id}")

        return agent

    @staticmethod
    def find_best_agent_for_role(
        session: Session,
        role: AgentRole
    ) -> Optional[Agent]:
        """
        Find the best available agent for a specific role

        Selection criteria:
        1. Must be available (idle, active, no current task)
        2. Prefer agents with higher success rate
        3. Prefer agents with fewer completed tasks (load balancing)

        Args:
            session: Database session
            role: Required agent role

        Returns:
            Agent or None: Best available agent, or None if none available
        """
        available_agents = AgentService.get_available_agents(session, role)

        if not available_agents:
            return None

        # Sort by success rate (descending) and tasks completed (ascending)
        def agent_score(agent: Agent) -> tuple:
            total_tasks = agent.tasks_completed + agent.tasks_failed
            success_rate = (agent.tasks_completed / total_tasks) if total_tasks > 0 else 1.0
            # Return tuple: (success_rate desc, tasks_completed asc)
            return (-success_rate, agent.tasks_completed)

        sorted_agents = sorted(available_agents, key=agent_score)

        best_agent = sorted_agents[0]
        logger.info(f"Selected agent {best_agent.id} ({best_agent.name}) for role {role}")

        return best_agent

    @staticmethod
    async def execute_agent(
        session: Session,
        agent_id: int,
        input_data: Dict[str, Any],
        task_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        agent_type: Optional[str] = None
    ) -> AgentExecution:
        """
        Execute an agent and track the execution

        Args:
            session: Database session
            agent_id: Agent ID
            input_data: Input data for agent
            task_id: Optional task ID
            workflow_id: Optional workflow ID
            user_id: Optional user ID
            session_id: Optional session ID
            agent_type: Override agent type (defaults to inferred from role)

        Returns:
            AgentExecution: Execution record

        Raises:
            AgentNotFoundError: If agent not found
            ValidationError: If agent is not active
        """
        # Get agent from database
        agent_model = AgentService.get_agent_by_id(session, agent_id)

        if not agent_model.is_active:
            raise ValidationError(f"Agent {agent_id} is not active")

        # Create execution record
        execution = AgentExecution(
            agent_id=agent_id,
            task_id=task_id,
            workflow_id=workflow_id,
            user_id=user_id,
            session_id=session_id,
            input_data=input_data,
            status=ExecutionStatus.PENDING,
            llm_provider=agent_model.llm_provider,
            llm_model=agent_model.llm_model,
            temperature=agent_model.temperature,
            max_tokens=agent_model.max_tokens
        )

        session.add(execution)
        session.flush()

        try:
            # Update agent status
            agent_model.status = AgentStatus.BUSY
            agent_model.current_task_id = task_id
            session.flush()

            # Create LLM provider
            llm = create_llm_provider(
                provider=agent_model.llm_provider,
                model=agent_model.llm_model
            )

            # Determine agent type
            type_to_use = agent_type or AgentService._infer_agent_type(agent_model.role)

            # Create agent instance from registry
            agent_instance = agent_registry.create_agent(
                agent_type=type_to_use,
                llm_provider=llm
            )

            # Create executor
            executor = AgentExecutor(agent_instance)

            # Prepare context
            context = AgentContext(
                task_id=str(task_id) if task_id else None,
                workflow_id=workflow_id,
                user_id=user_id,
                session_id=session_id,
                input_data=input_data
            )

            # Update execution status
            execution.status = ExecutionStatus.RUNNING
            execution.started_at = datetime.utcnow()
            session.flush()

            # Execute agent
            result = await executor.execute(context)

            # Update execution with results
            execution.status = ExecutionStatus.COMPLETED if result.status.value == "completed" else ExecutionStatus.FAILED
            execution.completed_at = datetime.utcnow()
            execution.output_data = result.output
            execution.output_metadata = result.metadata
            execution.tokens_used = result.tokens_used
            execution.cost = result.cost
            execution.calculate_execution_time()

            if result.error:
                execution.error_message = result.error
                execution.error_type = "AgentExecutionError"

            # Update agent metrics
            agent_model.update_metrics(
                task_duration=int(execution.execution_time_seconds or 0),
                success=execution.is_successful,
                cost=execution.cost or 0.0
            )

            # Update token tracking
            agent_model.total_tokens_used += (execution.tokens_used or 0)

            # Reset agent status
            agent_model.status = AgentStatus.IDLE
            agent_model.current_task_id = None

            session.flush()

            logger.info(
                f"Agent {agent_id} execution {execution.id} completed: "
                f"status={execution.status}, time={execution.execution_time_seconds}s, "
                f"cost=${execution.cost}"
            )

        except Exception as e:
            # Update execution with error
            execution.status = ExecutionStatus.FAILED
            execution.completed_at = datetime.utcnow()
            execution.error_message = str(e)
            execution.error_type = type(e).__name__
            execution.calculate_execution_time()

            # Reset agent status
            agent_model.status = AgentStatus.ERROR
            agent_model.current_task_id = None

            # Update failure metrics
            agent_model.tasks_failed += 1

            session.flush()

            logger.error(f"Agent {agent_id} execution {execution.id} failed: {e}")

        return execution

    @staticmethod
    def _infer_agent_type(role: AgentRole) -> str:
        """Infer agent type from role"""
        role_to_type = {
            AgentRole.RESEARCHER: "research",
            AgentRole.CODER: "code",
            AgentRole.WRITER: "writer",
            AgentRole.REVIEWER: "code",
            AgentRole.COORDINATOR: "planner",
            AgentRole.TESTER: "code"
        }
        return role_to_type.get(role, "research")

    @staticmethod
    def get_agent_executions(
        session: Session,
        agent_id: Optional[int] = None,
        task_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        status: Optional[ExecutionStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AgentExecution]:
        """
        Get agent executions with filters

        Args:
            session: Database session
            agent_id: Filter by agent ID
            task_id: Filter by task ID
            workflow_id: Filter by workflow ID
            status: Filter by status
            limit: Result limit
            offset: Result offset

        Returns:
            List of executions
        """
        query = session.query(AgentExecution)

        if agent_id:
            query = query.filter(AgentExecution.agent_id == agent_id)
        if task_id:
            query = query.filter(AgentExecution.task_id == task_id)
        if workflow_id:
            query = query.filter(AgentExecution.workflow_id == workflow_id)
        if status:
            query = query.filter(AgentExecution.status == status)

        return query.order_by(AgentExecution.created_at.desc()).limit(limit).offset(offset).all()

    @staticmethod
    def get_execution_by_id(session: Session, execution_id: int) -> Optional[AgentExecution]:
        """Get execution by ID"""
        return session.query(AgentExecution).filter(AgentExecution.id == execution_id).first()

    @staticmethod
    def get_agent_statistics(session: Session, agent_id: int) -> Dict[str, Any]:
        """Get comprehensive agent statistics including executions"""
        agent = AgentService.get_agent_by_id(session, agent_id)

        total_executions = session.query(AgentExecution).filter(
            AgentExecution.agent_id == agent_id
        ).count()

        successful_executions = session.query(AgentExecution).filter(
            AgentExecution.agent_id == agent_id,
            AgentExecution.status == ExecutionStatus.COMPLETED
        ).count()

        failed_executions = session.query(AgentExecution).filter(
            AgentExecution.agent_id == agent_id,
            AgentExecution.status == ExecutionStatus.FAILED
        ).count()

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "agent_role": agent.role.value,
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": failed_executions,
            "execution_success_rate": (successful_executions / total_executions * 100) if total_executions > 0 else 0,
            "total_cost": agent.total_cost,
            "total_tokens_used": agent.total_tokens_used,
            "average_execution_time": agent.average_task_duration_seconds,
            "tasks_completed": agent.tasks_completed,
            "tasks_failed": agent.tasks_failed,
            "task_success_rate": (agent.tasks_completed / (agent.tasks_completed + agent.tasks_failed) * 100) if (agent.tasks_completed + agent.tasks_failed) > 0 else 0,
            "is_active": agent.is_active,
            "status": agent.status.value,
            "created_at": agent.created_at.isoformat() if agent.created_at else None,
            "last_active_at": agent.last_active_at.isoformat() if agent.last_active_at else None
        }
