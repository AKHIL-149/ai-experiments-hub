"""
Workflow execution service
"""

from typing import Dict, Any, Optional, List
from datetime import datetime

from src.workflows.graph import default_workflow, simple_workflow, create_custom_workflow
from src.workflows.state import create_initial_state, WorkflowState
from src.core.logging import logger
from src.core.exceptions import WorkflowExecutionError


class WorkflowService:
    """Service for executing LangGraph workflows"""

    def __init__(self):
        """Initialize workflow service"""
        self.workflows = {
            "default": default_workflow,
            "simple": simple_workflow
        }

    def execute_workflow(
        self,
        task_id: int,
        task_title: str,
        task_description: str,
        task_type: str,
        priority: int = 5,
        input_data: Optional[Dict[str, Any]] = None,
        workflow_type: str = "simple"
    ) -> WorkflowState:
        """
        Execute a workflow

        Args:
            task_id: Task ID
            task_title: Task title
            task_description: Task description
            task_type: Task type
            priority: Task priority
            input_data: Additional input data
            workflow_type: Type of workflow to execute

        Returns:
            WorkflowState: Final workflow state

        Raises:
            WorkflowExecutionError: If workflow execution fails
        """
        try:
            logger.info(f"Starting workflow execution for task {task_id}")

            # Create initial state
            initial_state = create_initial_state(
                task_id=task_id,
                task_title=task_title,
                task_description=task_description,
                task_type=task_type,
                priority=priority,
                input_data=input_data
            )

            # Update start time
            initial_state["started_at"] = datetime.utcnow()

            # Get workflow
            workflow = self.workflows.get(workflow_type)
            if not workflow:
                raise WorkflowExecutionError(
                    workflow_id=workflow_type,
                    error=f"Unknown workflow type: {workflow_type}"
                )

            # Execute workflow
            logger.info(f"Executing {workflow_type} workflow for task {task_id}")
            final_state = workflow.invoke(initial_state)

            # Calculate execution time
            if final_state.get("started_at"):
                execution_time = (datetime.utcnow() - final_state["started_at"]).total_seconds()
                final_state["execution_time"] = execution_time

            logger.info(
                f"Workflow completed for task {task_id} "
                f"(status: {final_state.get('status')}, "
                f"progress: {final_state.get('progress')}%)"
            )

            return final_state

        except Exception as e:
            logger.error(f"Workflow execution failed for task {task_id}: {e}")
            raise WorkflowExecutionError(
                workflow_id=workflow_type,
                error=str(e)
            )

    def execute_custom_workflow(
        self,
        task_id: int,
        task_title: str,
        task_description: str,
        nodes: List[str],
        edges: List[tuple],
        input_data: Optional[Dict[str, Any]] = None
    ) -> WorkflowState:
        """
        Execute a custom workflow

        Args:
            task_id: Task ID
            task_title: Task title
            task_description: Task description
            nodes: List of node names
            edges: List of (from, to) edges
            input_data: Additional input data

        Returns:
            WorkflowState: Final workflow state
        """
        try:
            logger.info(f"Creating custom workflow for task {task_id}")

            # Create custom workflow graph
            custom_graph = create_custom_workflow(nodes, edges)
            custom_workflow = custom_graph.compile()

            # Create initial state
            initial_state = create_initial_state(
                task_id=task_id,
                task_title=task_title,
                task_description=task_description,
                task_type="custom",
                input_data=input_data
            )

            initial_state["started_at"] = datetime.utcnow()

            # Execute workflow
            final_state = custom_workflow.invoke(initial_state)

            # Calculate execution time
            if final_state.get("started_at"):
                execution_time = (datetime.utcnow() - final_state["started_at"]).total_seconds()
                final_state["execution_time"] = execution_time

            logger.info(f"Custom workflow completed for task {task_id}")

            return final_state

        except Exception as e:
            logger.error(f"Custom workflow execution failed for task {task_id}: {e}")
            raise WorkflowExecutionError(
                workflow_id="custom",
                error=str(e)
            )

    def get_workflow_info(self, workflow_type: str = "default") -> Dict[str, Any]:
        """
        Get workflow information

        Args:
            workflow_type: Type of workflow

        Returns:
            dict: Workflow information
        """
        workflow = self.workflows.get(workflow_type)
        if not workflow:
            return {"error": f"Unknown workflow type: {workflow_type}"}

        return {
            "type": workflow_type,
            "available": True,
            "nodes": ["research", "code", "review", "test", "document"],
            "description": f"{workflow_type.capitalize()} multi-agent workflow"
        }

    def list_workflows(self) -> List[Dict[str, Any]]:
        """
        List available workflows

        Returns:
            list: List of workflow information
        """
        return [
            {
                "type": "default",
                "description": "Complete workflow with all nodes and routing",
                "nodes": ["research", "code", "review", "test", "document", "approval"]
            },
            {
                "type": "simple",
                "description": "Simple linear workflow for quick execution",
                "nodes": ["research", "code", "document"]
            },
            {
                "type": "custom",
                "description": "Custom workflow with user-defined nodes and edges",
                "nodes": "variable"
            }
        ]


# Singleton instance
workflow_service = WorkflowService()
