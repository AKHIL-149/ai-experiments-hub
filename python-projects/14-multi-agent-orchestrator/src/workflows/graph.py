"""
LangGraph workflow graph definition
"""

from langgraph.graph import StateGraph, END
from src.workflows.state import WorkflowState
from src.workflows.nodes import (
    research_node,
    code_node,
    review_node,
    test_node,
    document_node,
    router_node,
    approval_node,
    error_handler_node
)
from src.core.logging import logger


def create_workflow_graph() -> StateGraph:
    """
    Create LangGraph workflow graph

    Returns:
        StateGraph: Configured workflow graph
    """
    logger.info("Creating LangGraph workflow graph")

    # Create state graph
    graph = StateGraph(WorkflowState)

    # Add nodes
    graph.add_node("research", research_node)
    graph.add_node("code", code_node)
    graph.add_node("review", review_node)
    graph.add_node("test", test_node)
    graph.add_node("document", document_node)
    graph.add_node("approval", approval_node)
    graph.add_node("error_handler", error_handler_node)

    # Set entry point
    graph.set_entry_point("research")

    # Add conditional edges using router
    graph.add_conditional_edges(
        "research",
        router_node,
        {
            "code": "code",
            "approval": "approval",
            "error_handler": "error_handler",
            "end": END
        }
    )

    graph.add_conditional_edges(
        "code",
        router_node,
        {
            "review": "review",
            "approval": "approval",
            "error_handler": "error_handler",
            "end": END
        }
    )

    graph.add_conditional_edges(
        "review",
        router_node,
        {
            "test": "test",
            "approval": "approval",
            "error_handler": "error_handler",
            "end": END
        }
    )

    graph.add_conditional_edges(
        "test",
        router_node,
        {
            "document": "document",
            "approval": "approval",
            "error_handler": "error_handler",
            "end": END
        }
    )

    graph.add_conditional_edges(
        "document",
        router_node,
        {
            "end": END,
            "approval": "approval",
            "error_handler": "error_handler"
        }
    )

    # Approval and error handler edges
    graph.add_edge("approval", END)
    graph.add_edge("error_handler", END)

    logger.info("LangGraph workflow graph created successfully")

    return graph


def create_simple_workflow() -> StateGraph:
    """
    Create a simple linear workflow for testing

    Returns:
        StateGraph: Simple workflow graph
    """
    logger.info("Creating simple workflow graph")

    graph = StateGraph(WorkflowState)

    # Add subset of nodes
    graph.add_node("research", research_node)
    graph.add_node("code", code_node)
    graph.add_node("document", document_node)

    # Set entry point
    graph.set_entry_point("research")

    # Add direct edges (no routing)
    graph.add_edge("research", "code")
    graph.add_edge("code", "document")
    graph.add_edge("document", END)

    logger.info("Simple workflow graph created successfully")

    return graph


def create_custom_workflow(nodes: list, edges: list) -> StateGraph:
    """
    Create a custom workflow graph

    Args:
        nodes: List of node names to include
        edges: List of (from_node, to_node) tuples

    Returns:
        StateGraph: Custom workflow graph
    """
    logger.info(f"Creating custom workflow with {len(nodes)} nodes")

    graph = StateGraph(WorkflowState)

    # Map node names to functions
    node_map = {
        "research": research_node,
        "code": code_node,
        "review": review_node,
        "test": test_node,
        "document": document_node,
        "approval": approval_node,
        "error_handler": error_handler_node
    }

    # Add specified nodes
    for node in nodes:
        if node in node_map:
            graph.add_node(node, node_map[node])
        else:
            logger.warning(f"Unknown node: {node}")

    # Set entry point to first node
    if nodes:
        graph.set_entry_point(nodes[0])

    # Add edges
    for from_node, to_node in edges:
        if to_node == "END":
            graph.add_edge(from_node, END)
        else:
            graph.add_edge(from_node, to_node)

    logger.info("Custom workflow graph created successfully")

    return graph


# Compile graphs for immediate use
default_workflow = create_workflow_graph().compile()
simple_workflow = create_simple_workflow().compile()
