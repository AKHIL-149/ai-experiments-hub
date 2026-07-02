"""
Base Workflow Classes

Foundation for LangGraph-based agent workflows.
"""

from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor

from src.core.logging import logger


class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class WorkflowState(BaseModel):
    """
    Workflow State

    Maintains the state throughout workflow execution.
    Passed between nodes in the LangGraph.
    """
    # Workflow Metadata
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_node: Optional[str] = None

    # Input/Output
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)

    # Intermediate Results
    agent_results: Dict[str, Any] = Field(default_factory=dict)
    node_outputs: Dict[str, Any] = Field(default_factory=dict)

    # Execution Context
    task_id: Optional[int] = None
    user_id: Optional[int] = None
    session_id: Optional[str] = None

    # Error Handling
    errors: List[Dict[str, str]] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    # Metrics
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_cost: float = 0.0
    total_tokens: int = 0

    # Conditional Routing
    next_action: Optional[str] = None
    conditions: Dict[str, bool] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True
        use_enum_values = True


class WorkflowConfig(BaseModel):
    """Workflow configuration"""
    name: str
    description: str
    version: str = "1.0.0"
    timeout_seconds: int = 600  # 10 minutes
    max_retries: int = 3
    parallel_execution: bool = False
    auto_checkpoint: bool = True
    error_handling: str = "continue"  # continue, stop, retry

    class Config:
        use_enum_values = True


class BaseWorkflow:
    """
    Base Workflow Class

    Foundation for all LangGraph-based workflows.
    Provides common functionality for workflow execution.
    """

    def __init__(self, config: WorkflowConfig):
        """
        Initialize workflow

        Args:
            config: Workflow configuration
        """
        self.config = config
        self.graph: Optional[StateGraph] = None
        self.compiled_graph = None

        logger.info(f"Initialized workflow: {self.config.name}")

    def build_graph(self) -> StateGraph:
        """
        Build the workflow graph

        Must be implemented by subclasses.

        Returns:
            StateGraph: Constructed workflow graph
        """
        raise NotImplementedError("Subclasses must implement build_graph()")

    def compile(self) -> Any:
        """
        Compile the workflow graph for execution

        Returns:
            Compiled graph ready for execution
        """
        if not self.graph:
            self.graph = self.build_graph()

        self.compiled_graph = self.graph.compile()

        logger.info(f"Compiled workflow: {self.config.name}")
        return self.compiled_graph

    async def execute(
        self,
        input_data: Dict[str, Any],
        workflow_id: Optional[str] = None,
        task_id: Optional[int] = None,
        user_id: Optional[int] = None
    ) -> WorkflowState:
        """
        Execute the workflow

        Args:
            input_data: Input data for workflow
            workflow_id: Workflow identifier
            task_id: Associated task ID
            user_id: User ID

        Returns:
            WorkflowState: Final workflow state
        """
        if not self.compiled_graph:
            self.compile()

        # Initialize state
        initial_state = WorkflowState(
            workflow_id=workflow_id or f"wf_{datetime.utcnow().timestamp()}",
            input_data=input_data,
            task_id=task_id,
            user_id=user_id,
            status=WorkflowStatus.RUNNING,
            started_at=datetime.utcnow(),
            max_retries=self.config.max_retries
        )

        logger.info(f"Starting workflow {self.config.name}: {initial_state.workflow_id}")

        try:
            # Execute the compiled graph
            final_state = await self._execute_graph(initial_state)

            # Mark as completed
            final_state.status = WorkflowStatus.COMPLETED
            final_state.completed_at = datetime.utcnow()

            logger.info(
                f"Workflow {initial_state.workflow_id} completed: "
                f"cost=${final_state.total_cost}, tokens={final_state.total_tokens}"
            )

            return final_state

        except Exception as e:
            logger.error(f"Workflow {initial_state.workflow_id} failed: {e}")

            initial_state.status = WorkflowStatus.FAILED
            initial_state.completed_at = datetime.utcnow()
            initial_state.errors.append({
                "error": str(e),
                "type": type(e).__name__,
                "timestamp": datetime.utcnow().isoformat()
            })

            return initial_state

    async def _execute_graph(self, state: WorkflowState) -> WorkflowState:
        """
        Execute the compiled graph

        Args:
            state: Initial workflow state

        Returns:
            WorkflowState: Final state after execution
        """
        # Convert state to dict for LangGraph
        state_dict = state.dict()

        # Execute graph
        result = await self.compiled_graph.ainvoke(state_dict)

        # Convert back to WorkflowState
        final_state = WorkflowState(**result)

        return final_state

    def add_agent_node(
        self,
        graph: StateGraph,
        node_name: str,
        agent_function: Callable,
        description: Optional[str] = None
    ):
        """
        Add an agent node to the graph

        Args:
            graph: StateGraph instance
            node_name: Name of the node
            agent_function: Function that executes the agent
            description: Node description
        """
        graph.add_node(node_name, agent_function)

        logger.debug(f"Added node: {node_name}" + (f" - {description}" if description else ""))

    def add_conditional_edge(
        self,
        graph: StateGraph,
        source_node: str,
        routing_function: Callable,
        edge_map: Dict[str, str]
    ):
        """
        Add a conditional edge between nodes

        Args:
            graph: StateGraph instance
            source_node: Source node name
            routing_function: Function that determines next node
            edge_map: Map of condition results to node names
        """
        graph.add_conditional_edges(source_node, routing_function, edge_map)

        logger.debug(f"Added conditional edge from {source_node}: {edge_map}")

    def add_edge(
        self,
        graph: StateGraph,
        source_node: str,
        target_node: str
    ):
        """
        Add a direct edge between nodes

        Args:
            graph: StateGraph instance
            source_node: Source node name
            target_node: Target node name
        """
        graph.add_edge(source_node, target_node)

        logger.debug(f"Added edge: {source_node} -> {target_node}")

    def get_state_summary(self, state: WorkflowState) -> Dict[str, Any]:
        """Get workflow state summary"""
        return {
            "workflow_id": state.workflow_id,
            "status": state.status,
            "current_node": state.current_node,
            "total_cost": state.total_cost,
            "total_tokens": state.total_tokens,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "completed_at": state.completed_at.isoformat() if state.completed_at else None,
            "agent_results": list(state.agent_results.keys()),
            "errors": len(state.errors)
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.config.name}, version={self.config.version})>"
