"""
Agent Orchestration Service for coordinating multiple agents
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from src.models.agent import Agent, AgentRole, AgentStatus
from src.models.task import Task, TaskStatus
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.models.agent_message import AgentMessage, MessageType, MessagePriority
from src.services.agent_communication import AgentCommunicationService
from src.services.memory_service import MemoryService
from src.models.shared_memory import MemoryScope, MemoryType
from src.core.logging import logger


class OrchestrationPattern:
    """Orchestration patterns for multi-agent coordination"""
    SEQUENTIAL = "sequential"  # Agents execute one after another
    PARALLEL = "parallel"      # Agents execute simultaneously
    HIERARCHICAL = "hierarchical"  # Supervisor delegates to workers
    PIPELINE = "pipeline"      # Output of one agent feeds into next
    BROADCAST = "broadcast"    # Same task distributed to all agents


class AgentOrchestrationService:
    """
    Service for orchestrating multiple agents to work on tasks together.

    Handles task distribution, agent coordination, result aggregation,
    and workflow state management across multiple agents.
    """

    @staticmethod
    def discover_agents(
        session: Session,
        role: Optional[AgentRole] = None,
        capabilities: Optional[List[str]] = None,
        status: AgentStatus = AgentStatus.IDLE,
        limit: int = 10
    ) -> List[Agent]:
        """
        Discover available agents based on criteria.

        Args:
            session: Database session
            role: Filter by agent role
            capabilities: Required capabilities (JSON field match)
            status: Filter by agent status
            limit: Maximum number of agents to return

        Returns:
            List of matching agents
        """
        query = session.query(Agent).filter(Agent.status == status)

        if role:
            query = query.filter(Agent.role == role)

        if capabilities:
            # Filter agents that have all required capabilities
            for capability in capabilities:
                query = query.filter(Agent.capabilities.contains([capability]))

        agents = query.order_by(
            Agent.successful_tasks.desc(),
            Agent.average_response_time.asc()
        ).limit(limit).all()

        logger.info(f"Discovered {len(agents)} agents with role={role}, capabilities={capabilities}")

        return agents

    @staticmethod
    def assign_task_to_agent(
        session: Session,
        task_id: int,
        agent_id: int,
        priority: MessagePriority = MessagePriority.NORMAL,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[AgentExecution, AgentMessage]:
        """
        Assign a task to a specific agent.

        Args:
            session: Database session
            task_id: Task ID to assign
            agent_id: Agent ID to assign to
            priority: Message priority
            context: Additional context for the task

        Returns:
            Tuple of (AgentExecution, AgentMessage)
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Create execution record
        execution = AgentExecution(
            agent_id=agent_id,
            task_id=task_id,
            status=ExecutionStatus.ASSIGNED,
            input_data=context or {},
            started_at=datetime.utcnow()
        )
        session.add(execution)
        session.flush()

        # Send task assignment message
        message = AgentCommunicationService.send_message(
            session=session,
            sender_agent_id=None,  # System message
            receiver_agent_id=agent_id,
            content=f"Task assigned: {task.title}",
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=priority,
            requires_response=True,
            payload={
                "task_id": task_id,
                "execution_id": execution.id,
                "task_title": task.title,
                "task_description": task.description,
                "context": context or {}
            }
        )

        # Update agent status
        agent.status = AgentStatus.BUSY
        agent.current_task_id = task_id

        # Update task status
        task.status = TaskStatus.IN_PROGRESS
        task.assigned_agent_id = agent_id

        session.flush()

        logger.info(f"Assigned task {task_id} to agent {agent_id} (execution {execution.id})")

        return execution, message

    @staticmethod
    def orchestrate_sequential(
        session: Session,
        task_ids: List[int],
        workflow_id: Optional[str] = None,
        auto_assign: bool = True
    ) -> List[AgentExecution]:
        """
        Orchestrate tasks in sequential order.

        Tasks execute one after another, with each task starting only
        after the previous one completes.

        Args:
            session: Database session
            task_ids: List of task IDs in execution order
            workflow_id: Workflow ID for context
            auto_assign: Automatically assign agents based on capabilities

        Returns:
            List of AgentExecution records
        """
        executions = []

        for i, task_id in enumerate(task_ids):
            task = session.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.warning(f"Task {task_id} not found, skipping")
                continue

            # Find suitable agent if auto-assign
            if auto_assign:
                agents = AgentOrchestrationService.discover_agents(
                    session=session,
                    status=AgentStatus.IDLE,
                    limit=1
                )

                if not agents:
                    logger.error(f"No available agents for task {task_id}")
                    continue

                agent = agents[0]
            else:
                if not task.assigned_agent_id:
                    logger.warning(f"Task {task_id} has no assigned agent")
                    continue
                agent = session.query(Agent).filter(Agent.id == task.assigned_agent_id).first()

            # Build context from previous execution
            context = {
                "sequence_position": i,
                "total_tasks": len(task_ids),
                "workflow_id": workflow_id,
                "is_first": i == 0,
                "is_last": i == len(task_ids) - 1
            }

            if i > 0 and executions:
                # Add previous task result to context
                prev_execution = executions[-1]
                context["previous_execution_id"] = prev_execution.id
                context["previous_task_id"] = task_ids[i-1]
                context["previous_result"] = prev_execution.output_data

            # Assign task
            execution, _ = AgentOrchestrationService.assign_task_to_agent(
                session=session,
                task_id=task_id,
                agent_id=agent.id,
                priority=MessagePriority.NORMAL,
                context=context
            )

            executions.append(execution)

        # Store orchestration metadata in shared memory
        if workflow_id:
            MemoryService.set(
                session=session,
                key="orchestration_sequential",
                value={
                    "pattern": OrchestrationPattern.SEQUENTIAL,
                    "task_ids": task_ids,
                    "execution_ids": [e.id for e in executions],
                    "started_at": datetime.utcnow().isoformat()
                },
                scope=MemoryScope.WORKFLOW,
                scope_id=workflow_id,
                memory_type=MemoryType.STATE
            )

        logger.info(f"Sequential orchestration started: {len(executions)} tasks")

        return executions

    @staticmethod
    def orchestrate_parallel(
        session: Session,
        task_ids: List[int],
        workflow_id: Optional[str] = None,
        auto_assign: bool = True
    ) -> List[AgentExecution]:
        """
        Orchestrate tasks in parallel.

        All tasks are assigned to available agents simultaneously
        and execute concurrently.

        Args:
            session: Database session
            task_ids: List of task IDs to execute in parallel
            workflow_id: Workflow ID for context
            auto_assign: Automatically assign agents based on capabilities

        Returns:
            List of AgentExecution records
        """
        executions = []

        # Find enough agents for all tasks
        if auto_assign:
            agents = AgentOrchestrationService.discover_agents(
                session=session,
                status=AgentStatus.IDLE,
                limit=len(task_ids)
            )

            if len(agents) < len(task_ids):
                logger.warning(
                    f"Not enough agents available: {len(agents)} for {len(task_ids)} tasks"
                )

        for i, task_id in enumerate(task_ids):
            task = session.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.warning(f"Task {task_id} not found, skipping")
                continue

            # Assign agent
            if auto_assign:
                if i >= len(agents):
                    logger.error(f"No available agent for task {task_id}")
                    continue
                agent = agents[i]
            else:
                if not task.assigned_agent_id:
                    logger.warning(f"Task {task_id} has no assigned agent")
                    continue
                agent = session.query(Agent).filter(Agent.id == task.assigned_agent_id).first()

            # Build context
            context = {
                "parallel_position": i,
                "total_parallel_tasks": len(task_ids),
                "workflow_id": workflow_id,
                "task_ids": task_ids  # All parallel task IDs
            }

            # Assign task
            execution, _ = AgentOrchestrationService.assign_task_to_agent(
                session=session,
                task_id=task_id,
                agent_id=agent.id,
                priority=MessagePriority.NORMAL,
                context=context
            )

            executions.append(execution)

        # Store orchestration metadata in shared memory
        if workflow_id:
            MemoryService.set(
                session=session,
                key="orchestration_parallel",
                value={
                    "pattern": OrchestrationPattern.PARALLEL,
                    "task_ids": task_ids,
                    "execution_ids": [e.id for e in executions],
                    "started_at": datetime.utcnow().isoformat()
                },
                scope=MemoryScope.WORKFLOW,
                scope_id=workflow_id,
                memory_type=MemoryType.STATE
            )

        logger.info(f"Parallel orchestration started: {len(executions)} tasks")

        return executions

    @staticmethod
    def orchestrate_hierarchical(
        session: Session,
        supervisor_agent_id: int,
        worker_task_ids: List[int],
        workflow_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Orchestrate tasks in hierarchical pattern.

        A supervisor agent delegates tasks to worker agents and
        aggregates their results.

        Args:
            session: Database session
            supervisor_agent_id: Supervisor agent ID
            worker_task_ids: List of task IDs for workers
            workflow_id: Workflow ID for context

        Returns:
            Orchestration result with supervisor and worker executions
        """
        supervisor = session.query(Agent).filter(Agent.id == supervisor_agent_id).first()
        if not supervisor:
            raise ValueError(f"Supervisor agent {supervisor_agent_id} not found")

        if supervisor.role != AgentRole.SUPERVISOR:
            logger.warning(f"Agent {supervisor_agent_id} is not a supervisor role")

        # Find worker agents
        workers = AgentOrchestrationService.discover_agents(
            session=session,
            role=AgentRole.WORKER,
            status=AgentStatus.IDLE,
            limit=len(worker_task_ids)
        )

        if len(workers) < len(worker_task_ids):
            logger.warning(
                f"Not enough workers: {len(workers)} for {len(worker_task_ids)} tasks"
            )

        # Assign tasks to workers
        worker_executions = []
        for i, task_id in enumerate(worker_task_ids):
            if i >= len(workers):
                logger.error(f"No available worker for task {task_id}")
                continue

            context = {
                "supervisor_agent_id": supervisor_agent_id,
                "worker_position": i,
                "total_workers": len(worker_task_ids),
                "workflow_id": workflow_id
            }

            execution, message = AgentOrchestrationService.assign_task_to_agent(
                session=session,
                task_id=task_id,
                agent_id=workers[i].id,
                priority=MessagePriority.HIGH,
                context=context
            )

            worker_executions.append(execution)

            # Notify supervisor about worker assignment
            AgentCommunicationService.send_message(
                session=session,
                sender_agent_id=workers[i].id,
                receiver_agent_id=supervisor_agent_id,
                content=f"Worker assigned to task {task_id}",
                message_type=MessageType.NOTIFICATION,
                priority=MessagePriority.NORMAL,
                thread_id=message.thread_id,
                payload={
                    "task_id": task_id,
                    "execution_id": execution.id,
                    "worker_agent_id": workers[i].id
                }
            )

        # Update supervisor status
        supervisor.status = AgentStatus.BUSY
        session.flush()

        # Store orchestration metadata
        orchestration_data = {
            "pattern": OrchestrationPattern.HIERARCHICAL,
            "supervisor_agent_id": supervisor_agent_id,
            "worker_agent_ids": [w.id for w in workers[:len(worker_executions)]],
            "task_ids": worker_task_ids,
            "execution_ids": [e.id for e in worker_executions],
            "started_at": datetime.utcnow().isoformat()
        }

        if workflow_id:
            MemoryService.set(
                session=session,
                key="orchestration_hierarchical",
                value=orchestration_data,
                scope=MemoryScope.WORKFLOW,
                scope_id=workflow_id,
                memory_type=MemoryType.STATE
            )

        logger.info(
            f"Hierarchical orchestration: supervisor {supervisor_agent_id}, "
            f"{len(worker_executions)} workers"
        )

        return {
            "supervisor": supervisor,
            "workers": workers[:len(worker_executions)],
            "executions": worker_executions,
            "orchestration": orchestration_data
        }

    @staticmethod
    def aggregate_results(
        session: Session,
        execution_ids: List[int],
        aggregation_strategy: str = "collect"
    ) -> Dict[str, Any]:
        """
        Aggregate results from multiple agent executions.

        Args:
            session: Database session
            execution_ids: List of execution IDs to aggregate
            aggregation_strategy: Strategy for aggregation
                - "collect": Collect all results in a list
                - "merge": Merge all results into single dict
                - "vote": Majority voting (for classification tasks)
                - "average": Average numeric results

        Returns:
            Aggregated result
        """
        executions = session.query(AgentExecution).filter(
            AgentExecution.id.in_(execution_ids)
        ).all()

        if not executions:
            return {"error": "No executions found"}

        # Check if all executions are completed
        pending = [e for e in executions if e.status != ExecutionStatus.COMPLETED]
        if pending:
            logger.warning(f"{len(pending)} executions still pending")

        results = []
        for execution in executions:
            if execution.output_data:
                results.append(execution.output_data)

        if aggregation_strategy == "collect":
            aggregated = {
                "strategy": "collect",
                "count": len(results),
                "results": results
            }

        elif aggregation_strategy == "merge":
            merged = {}
            for result in results:
                if isinstance(result, dict):
                    merged.update(result)
            aggregated = {
                "strategy": "merge",
                "count": len(results),
                "result": merged
            }

        elif aggregation_strategy == "vote":
            # Count occurrences of each result
            votes = {}
            for result in results:
                key = str(result)
                votes[key] = votes.get(key, 0) + 1

            # Find majority
            if votes:
                winner = max(votes.items(), key=lambda x: x[1])
                aggregated = {
                    "strategy": "vote",
                    "count": len(results),
                    "winner": winner[0],
                    "votes": votes
                }
            else:
                aggregated = {"strategy": "vote", "count": 0, "winner": None}

        elif aggregation_strategy == "average":
            # Average numeric results
            numeric_results = []
            for result in results:
                if isinstance(result, (int, float)):
                    numeric_results.append(result)
                elif isinstance(result, dict) and "value" in result:
                    if isinstance(result["value"], (int, float)):
                        numeric_results.append(result["value"])

            if numeric_results:
                avg = sum(numeric_results) / len(numeric_results)
                aggregated = {
                    "strategy": "average",
                    "count": len(numeric_results),
                    "average": avg,
                    "min": min(numeric_results),
                    "max": max(numeric_results)
                }
            else:
                aggregated = {"strategy": "average", "count": 0, "average": None}

        else:
            aggregated = {
                "strategy": "unknown",
                "count": len(results),
                "results": results
            }

        logger.info(f"Aggregated {len(results)} results using strategy '{aggregation_strategy}'")

        return aggregated

    @staticmethod
    def get_orchestration_status(
        session: Session,
        workflow_id: str
    ) -> Dict[str, Any]:
        """
        Get status of orchestration for a workflow.

        Args:
            session: Database session
            workflow_id: Workflow ID

        Returns:
            Orchestration status
        """
        # Get orchestration metadata from shared memory
        orchestration_keys = [
            "orchestration_sequential",
            "orchestration_parallel",
            "orchestration_hierarchical"
        ]

        status = {
            "workflow_id": workflow_id,
            "orchestrations": []
        }

        for key in orchestration_keys:
            memory = MemoryService.get(
                session=session,
                key=key,
                scope=MemoryScope.WORKFLOW,
                scope_id=workflow_id
            )

            if memory:
                orchestration_data = memory.value
                execution_ids = orchestration_data.get("execution_ids", [])

                # Get execution statuses
                executions = session.query(AgentExecution).filter(
                    AgentExecution.id.in_(execution_ids)
                ).all()

                execution_statuses = {}
                for exec_status in ExecutionStatus:
                    count = len([e for e in executions if e.status == exec_status])
                    if count > 0:
                        execution_statuses[exec_status.value] = count

                status["orchestrations"].append({
                    "pattern": orchestration_data.get("pattern"),
                    "task_count": len(orchestration_data.get("task_ids", [])),
                    "execution_count": len(execution_ids),
                    "execution_statuses": execution_statuses,
                    "started_at": orchestration_data.get("started_at"),
                    "metadata": orchestration_data
                })

        return status
