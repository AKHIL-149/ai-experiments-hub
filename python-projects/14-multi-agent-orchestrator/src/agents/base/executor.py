"""
Agent Executor

Handles agent execution with error handling, retries, and timeouts.
"""

import asyncio
from typing import Optional
from datetime import datetime

from src.agents.base.agent import BaseAgent, AgentContext, AgentResult, AgentStatus
from src.agents.base.memory import AgentMemory, MemoryType
from src.core.logging import logger


class AgentExecutor:
    """
    Agent Executor

    Features:
    - Execute agents with context
    - Automatic retry on failure
    - Timeout handling
    - Memory integration
    - Execution tracking
    """

    def __init__(self, agent: BaseAgent, memory: Optional[AgentMemory] = None):
        """
        Initialize executor

        Args:
            agent: Agent to execute
            memory: Optional memory system
        """
        self.agent = agent
        self.memory = memory or AgentMemory()

        logger.info(f"Initialized executor for agent: {agent.config.name}")

    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute agent with context

        Args:
            context: Execution context

        Returns:
            AgentResult: Execution result
        """
        started_at = datetime.utcnow()

        # Record execution start in memory
        if self.agent.config.memory_enabled:
            self.memory.add(
                content=f"Starting execution for task: {context.task_id}",
                memory_type=MemoryType.ACTION,
                importance=0.5,
                metadata={"task_id": context.task_id, "workflow_id": context.workflow_id}
            )

        # Validate input
        try:
            is_valid = await self.agent.validate_input(context.input_data)
            if not is_valid:
                return AgentResult(
                    status=AgentStatus.FAILED,
                    error="Input validation failed",
                    started_at=started_at
                )
        except Exception as e:
            logger.error(f"Input validation error: {e}")
            return AgentResult(
                status=AgentStatus.FAILED,
                error=f"Input validation error: {str(e)}",
                started_at=started_at
            )

        # Prepare context
        try:
            context = await self.agent.prepare_context(context)
        except Exception as e:
            logger.error(f"Context preparation error: {e}")
            return AgentResult(
                status=AgentStatus.FAILED,
                error=f"Context preparation error: {str(e)}",
                started_at=started_at
            )

        # Execute with retries
        result = await self._execute_with_retry(context, started_at)

        # Post-process result
        try:
            result = await self.agent.post_process(result, context)
        except Exception as e:
            logger.error(f"Post-processing error: {e}")
            result.metadata["post_process_error"] = str(e)

        # Record execution result in memory
        if self.agent.config.memory_enabled:
            self.memory.add(
                content=f"Execution completed with status: {result.status}",
                memory_type=MemoryType.RESULT,
                importance=0.7 if result.status == AgentStatus.COMPLETED else 0.9,
                metadata={
                    "task_id": context.task_id,
                    "status": result.status,
                    "execution_time": result.execution_time
                }
            )

        return result

    async def _execute_with_retry(
        self,
        context: AgentContext,
        started_at: datetime
    ) -> AgentResult:
        """
        Execute agent with automatic retry

        Args:
            context: Execution context
            started_at: Execution start time

        Returns:
            AgentResult: Execution result
        """
        last_error = None

        max_attempts = self.agent.config.max_retries + 1 if self.agent.config.retry_on_failure else 1

        for attempt in range(max_attempts):
            try:
                # Update agent status
                self.agent.status = AgentStatus.RUNNING
                self.agent.current_context = context

                # Execute with timeout
                result = await asyncio.wait_for(
                    self.agent.execute(context),
                    timeout=self.agent.config.timeout
                )

                # Calculate execution time
                completed_at = datetime.utcnow()
                execution_time = (completed_at - started_at).total_seconds()

                result.completed_at = completed_at
                result.execution_time = execution_time

                # Update agent status
                self.agent.status = result.status

                # If successful, return result
                if result.status == AgentStatus.COMPLETED:
                    logger.info(
                        f"Agent {self.agent.config.name} completed successfully "
                        f"(attempt {attempt + 1}/{max_attempts})"
                    )
                    return result

                # If failed but not retrying, return result
                if not self.agent.config.retry_on_failure:
                    return result

                last_error = result.error

            except asyncio.TimeoutError:
                logger.warning(
                    f"Agent {self.agent.config.name} timed out "
                    f"(attempt {attempt + 1}/{max_attempts})"
                )
                last_error = f"Execution timeout after {self.agent.config.timeout} seconds"

            except Exception as e:
                logger.error(
                    f"Agent {self.agent.config.name} error: {e} "
                    f"(attempt {attempt + 1}/{max_attempts})"
                )
                last_error = str(e)

            # Wait before retry (exponential backoff)
            if attempt < max_attempts - 1:
                wait_time = min(2 ** attempt, 30)  # Max 30 seconds
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)

        # All attempts failed
        self.agent.status = AgentStatus.FAILED

        completed_at = datetime.utcnow()
        execution_time = (completed_at - started_at).total_seconds()

        return AgentResult(
            status=AgentStatus.FAILED,
            error=last_error or "Unknown error",
            metadata={"max_retries_exceeded": True, "attempts": max_attempts},
            started_at=started_at,
            completed_at=completed_at,
            execution_time=execution_time
        )

    def get_memory(self) -> AgentMemory:
        """Get agent memory"""
        return self.memory

    def clear_memory(self):
        """Clear agent memory"""
        self.memory.clear_all()
        logger.info(f"Cleared memory for agent: {self.agent.config.name}")

    def __repr__(self) -> str:
        return f"<AgentExecutor(agent={self.agent.config.name}, memory_items={len(self.memory)})>"
