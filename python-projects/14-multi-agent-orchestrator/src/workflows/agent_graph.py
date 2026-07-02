"""
Agent Graph

LangGraph integration for agent orchestration with conditional routing.
"""

from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass

from langgraph.graph import StateGraph, END

from src.agents import agent_registry, AgentExecutor, AgentContext
from src.agents.base.llm_provider import create_llm_provider
from src.workflows.base_workflow import WorkflowState
from src.core.logging import logger


class NodeType(str, Enum):
    """Graph node types"""
    AGENT = "agent"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    AGGREGATOR = "aggregator"


@dataclass
class GraphNode:
    """Graph node definition"""
    name: str
    node_type: NodeType
    agent_type: Optional[str] = None  # For AGENT nodes
    function: Optional[Callable] = None  # For custom nodes
    description: Optional[str] = None


@dataclass
class GraphEdge:
    """Graph edge definition"""
    source: str
    target: str
    condition: Optional[Callable] = None  # For conditional edges
    condition_map: Optional[Dict[str, str]] = None  # For multi-way conditional


class AgentGraph:
    """
    Agent Graph

    Builds and manages LangGraph StateGraphs for agent orchestration.
    """

    def __init__(self, name: str):
        """
        Initialize agent graph

        Args:
            name: Graph name
        """
        self.name = name
        self.nodes: List[GraphNode] = []
        self.edges: List[GraphEdge] = []
        self.graph: Optional[StateGraph] = None

        logger.info(f"Initialized agent graph: {name}")

    def add_agent_node(
        self,
        name: str,
        agent_type: str,
        description: Optional[str] = None
    ) -> 'AgentGraph':
        """
        Add an agent execution node

        Args:
            name: Node name
            agent_type: Type of agent (research, code, data_analyst, writer, planner)
            description: Node description

        Returns:
            Self for chaining
        """
        node = GraphNode(
            name=name,
            node_type=NodeType.AGENT,
            agent_type=agent_type,
            description=description
        )

        self.nodes.append(node)

        logger.debug(f"Added agent node: {name} ({agent_type})")
        return self

    def add_conditional_node(
        self,
        name: str,
        condition_function: Callable,
        description: Optional[str] = None
    ) -> 'AgentGraph':
        """
        Add a conditional routing node

        Args:
            name: Node name
            condition_function: Function that determines routing
            description: Node description

        Returns:
            Self for chaining
        """
        node = GraphNode(
            name=name,
            node_type=NodeType.CONDITIONAL,
            function=condition_function,
            description=description
        )

        self.nodes.append(node)

        logger.debug(f"Added conditional node: {name}")
        return self

    def add_parallel_node(
        self,
        name: str,
        agent_types: List[str],
        description: Optional[str] = None
    ) -> 'AgentGraph':
        """
        Add a parallel execution node (executes multiple agents concurrently)

        Args:
            name: Node name
            agent_types: List of agent types to execute in parallel
            description: Node description

        Returns:
            Self for chaining
        """
        async def parallel_execution(state: Dict[str, Any]) -> Dict[str, Any]:
            """Execute multiple agents in parallel"""
            import asyncio

            workflow_state = WorkflowState(**state)

            # Create tasks for each agent
            tasks = []
            for agent_type in agent_types:
                task = self._execute_agent(workflow_state, agent_type, name)
                tasks.append(task)

            # Execute in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Aggregate results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    workflow_state.errors.append({
                        "agent_type": agent_types[i],
                        "error": str(result),
                        "node": name
                    })
                else:
                    # Merge agent result
                    workflow_state.agent_results[f"{name}_{agent_types[i]}"] = result

            return workflow_state.dict()

        node = GraphNode(
            name=name,
            node_type=NodeType.PARALLEL,
            function=parallel_execution,
            description=description
        )

        self.nodes.append(node)

        logger.debug(f"Added parallel node: {name} with {len(agent_types)} agents")
        return self

    def add_edge(
        self,
        source: str,
        target: str
    ) -> 'AgentGraph':
        """
        Add a direct edge between nodes

        Args:
            source: Source node name
            target: Target node name or END

        Returns:
            Self for chaining
        """
        edge = GraphEdge(source=source, target=target)
        self.edges.append(edge)

        logger.debug(f"Added edge: {source} -> {target}")
        return self

    def add_conditional_edge(
        self,
        source: str,
        condition: Callable,
        condition_map: Dict[str, str]
    ) -> 'AgentGraph':
        """
        Add a conditional edge with multiple possible targets

        Args:
            source: Source node name
            condition: Function that returns condition key
            condition_map: Map of condition results to target nodes

        Returns:
            Self for chaining
        """
        edge = GraphEdge(
            source=source,
            target="",  # Determined by condition
            condition=condition,
            condition_map=condition_map
        )

        self.edges.append(edge)

        logger.debug(f"Added conditional edge from {source}: {list(condition_map.keys())}")
        return self

    def build(self) -> StateGraph:
        """
        Build the LangGraph StateGraph

        Returns:
            StateGraph: Built graph
        """
        # Create graph
        self.graph = StateGraph(WorkflowState)

        # Add all nodes
        for node in self.nodes:
            if node.node_type == NodeType.AGENT:
                # Create agent execution function
                async def agent_func(state: Dict[str, Any], agent_type=node.agent_type, node_name=node.name) -> Dict[str, Any]:
                    workflow_state = WorkflowState(**state)
                    result = await self._execute_agent(workflow_state, agent_type, node_name)
                    workflow_state.agent_results[node_name] = result
                    workflow_state.current_node = node_name
                    return workflow_state.dict()

                self.graph.add_node(node.name, agent_func)

            elif node.function:
                # Use custom function
                self.graph.add_node(node.name, node.function)

        # Add all edges
        for edge in self.edges:
            if edge.condition and edge.condition_map:
                # Conditional edge
                self.graph.add_conditional_edges(
                    edge.source,
                    edge.condition,
                    edge.condition_map
                )
            else:
                # Direct edge
                self.graph.add_edge(edge.source, edge.target)

        logger.info(f"Built graph '{self.name}' with {len(self.nodes)} nodes and {len(self.edges)} edges")

        return self.graph

    async def _execute_agent(
        self,
        state: WorkflowState,
        agent_type: str,
        node_name: str
    ) -> Dict[str, Any]:
        """
        Execute an agent and update state

        Args:
            state: Current workflow state
            agent_type: Type of agent to execute
            node_name: Name of current node

        Returns:
            Agent execution result
        """
        try:
            # Create LLM provider (use default for now)
            llm = create_llm_provider(provider="openai", model="gpt-4")

            # Create agent from registry
            agent = agent_registry.create_agent(agent_type=agent_type, llm_provider=llm)

            # Create executor
            executor = AgentExecutor(agent)

            # Prepare context
            context = AgentContext(
                task_id=str(state.task_id) if state.task_id else None,
                workflow_id=state.workflow_id,
                user_id=state.user_id,
                input_data=state.input_data
            )

            # Execute agent
            result = await executor.execute(context)

            # Update state metrics
            state.total_cost += (result.cost or 0)
            state.total_tokens += (result.tokens_used or 0)

            logger.info(
                f"Agent {agent_type} completed in node {node_name}: "
                f"status={result.status}, cost=${result.cost}"
            )

            return {
                "status": result.status.value,
                "output": result.output,
                "metadata": result.metadata,
                "tokens_used": result.tokens_used,
                "cost": result.cost,
                "error": result.error
            }

        except Exception as e:
            logger.error(f"Agent execution failed in node {node_name}: {e}")

            state.errors.append({
                "node": node_name,
                "agent_type": agent_type,
                "error": str(e),
                "type": type(e).__name__
            })

            return {
                "status": "failed",
                "output": None,
                "error": str(e)
            }

    def visualize(self) -> str:
        """
        Generate a text visualization of the graph

        Returns:
            Text representation of the graph
        """
        lines = [f"Graph: {self.name}", "=" * 50, ""]

        lines.append("Nodes:")
        for node in self.nodes:
            node_info = f"  - {node.name} ({node.node_type})"
            if node.agent_type:
                node_info += f" [agent: {node.agent_type}]"
            if node.description:
                node_info += f" - {node.description}"
            lines.append(node_info)

        lines.append("")
        lines.append("Edges:")
        for edge in self.edges:
            if edge.condition_map:
                lines.append(f"  - {edge.source} -> conditional: {list(edge.condition_map.values())}")
            else:
                lines.append(f"  - {edge.source} -> {edge.target}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<AgentGraph(name={self.name}, nodes={len(self.nodes)}, edges={len(self.edges)})>"
