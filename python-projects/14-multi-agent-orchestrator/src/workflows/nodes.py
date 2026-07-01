"""
Workflow nodes for LangGraph

Each node represents a step in the workflow graph
and is executed by a specialized agent.
"""

from typing import Dict, Any
from datetime import datetime

from src.workflows.state import WorkflowState, update_node_output, add_message, track_llm_call
from src.core.logging import logger


def research_node(state: WorkflowState) -> WorkflowState:
    """
    Research node - Gathers information and context

    Args:
        state: Current workflow state

    Returns:
        WorkflowState: Updated state with research output
    """
    logger.info(f"Executing research node for task {state['task_id']}")

    # Simulate research (will be replaced with actual LLM call)
    output = {
        "findings": f"Research findings for: {state['task_description']}",
        "sources": ["source1", "source2"],
        "summary": "Research completed successfully",
        "confidence": 0.85,
        "completed_at": datetime.utcnow().isoformat()
    }

    # Update state
    updated_state = update_node_output(state, "research", output)
    updated_state = add_message(
        updated_state,
        "assistant",
        f"Research completed: {output['summary']}"
    )

    # Track simulated LLM call (replace with actual tracking)
    updated_state = track_llm_call(updated_state, "gpt-4", 500, 0.01)

    updated_state["next_node"] = "code"
    updated_state["progress"] = 20

    logger.info(f"Research node completed for task {state['task_id']}")

    return updated_state


def code_node(state: WorkflowState) -> WorkflowState:
    """
    Code node - Implements solutions and writes code

    Args:
        state: Current workflow state

    Returns:
        WorkflowState: Updated state with code output
    """
    logger.info(f"Executing code node for task {state['task_id']}")

    # Get research context
    research_output = state.get("research_output", {})

    # Simulate coding (will be replaced with actual LLM call)
    output = {
        "code": f"# Implementation based on research\n# {research_output.get('summary', '')}",
        "language": "python",
        "files_created": ["main.py"],
        "lines_of_code": 50,
        "completed_at": datetime.utcnow().isoformat()
    }

    # Update state
    updated_state = update_node_output(state, "code", output)
    updated_state = add_message(
        updated_state,
        "assistant",
        f"Code implementation completed: {output['lines_of_code']} lines"
    )

    # Track simulated LLM call
    updated_state = track_llm_call(updated_state, "gpt-4", 1000, 0.02)

    updated_state["next_node"] = "review"
    updated_state["progress"] = 40

    logger.info(f"Code node completed for task {state['task_id']}")

    return updated_state


def review_node(state: WorkflowState) -> WorkflowState:
    """
    Review node - Reviews code quality and suggests improvements

    Args:
        state: Current workflow state

    Returns:
        WorkflowState: Updated state with review output
    """
    logger.info(f"Executing review node for task {state['task_id']}")

    # Get code context
    code_output = state.get("code_output", {})

    # Simulate code review (will be replaced with actual LLM call)
    output = {
        "issues_found": 0,
        "suggestions": ["Consider adding error handling"],
        "quality_score": 8.5,
        "approved": True,
        "completed_at": datetime.utcnow().isoformat()
    }

    # Update state
    updated_state = update_node_output(state, "review", output)
    updated_state = add_message(
        updated_state,
        "assistant",
        f"Code review completed: Quality score {output['quality_score']}/10"
    )

    # Track simulated LLM call
    updated_state = track_llm_call(updated_state, "gpt-4", 800, 0.016)

    updated_state["next_node"] = "test"
    updated_state["progress"] = 60

    logger.info(f"Review node completed for task {state['task_id']}")

    return updated_state


def test_node(state: WorkflowState) -> WorkflowState:
    """
    Test node - Creates and runs tests

    Args:
        state: Current workflow state

    Returns:
        WorkflowState: Updated state with test output
    """
    logger.info(f"Executing test node for task {state['task_id']}")

    # Get code context
    code_output = state.get("code_output", {})

    # Simulate testing (will be replaced with actual LLM call)
    output = {
        "tests_created": 5,
        "tests_passed": 5,
        "tests_failed": 0,
        "coverage": 85.0,
        "passed": True,
        "completed_at": datetime.utcnow().isoformat()
    }

    # Update state
    updated_state = update_node_output(state, "test", output)
    updated_state = add_message(
        updated_state,
        "assistant",
        f"Tests completed: {output['tests_passed']}/{output['tests_created']} passed"
    )

    # Track simulated LLM call
    updated_state = track_llm_call(updated_state, "gpt-4", 700, 0.014)

    updated_state["next_node"] = "document"
    updated_state["progress"] = 80

    logger.info(f"Test node completed for task {state['task_id']}")

    return updated_state


def document_node(state: WorkflowState) -> WorkflowState:
    """
    Document node - Generates documentation

    Args:
        state: Current workflow state

    Returns:
        WorkflowState: Updated state with documentation output
    """
    logger.info(f"Executing document node for task {state['task_id']}")

    # Get all previous outputs
    code_output = state.get("code_output", {})
    test_output = state.get("test_output", {})

    # Simulate documentation (will be replaced with actual LLM call)
    output = {
        "documentation": f"# {state['task_title']}\n\n## Overview\n{state['task_description']}",
        "sections": ["Overview", "Usage", "API Reference"],
        "word_count": 500,
        "completed_at": datetime.utcnow().isoformat()
    }

    # Update state
    updated_state = update_node_output(state, "document", output)
    updated_state = add_message(
        updated_state,
        "assistant",
        f"Documentation completed: {output['word_count']} words"
    )

    # Track simulated LLM call
    updated_state = track_llm_call(updated_state, "gpt-4", 600, 0.012)

    updated_state["next_node"] = "end"
    updated_state["progress"] = 100
    updated_state["status"] = "completed"
    updated_state["completed_at"] = datetime.utcnow()

    logger.info(f"Document node completed for task {state['task_id']}")

    return updated_state


def router_node(state: WorkflowState) -> str:
    """
    Router node - Determines next node based on state

    Args:
        state: Current workflow state

    Returns:
        str: Name of next node to execute
    """
    # Check if approval is required
    if state.get("requires_approval") and state.get("approval_status") != "approved":
        return "approval"

    # Check if there was an error
    if state.get("error"):
        return "error_handler"

    # Return next node from state
    next_node = state.get("next_node")
    if next_node:
        return next_node

    # Default to end
    return "end"


def approval_node(state: WorkflowState) -> WorkflowState:
    """
    Approval node - Waits for human approval

    Args:
        state: Current workflow state

    Returns:
        WorkflowState: Updated state
    """
    logger.info(f"Waiting for approval for task {state['task_id']}")

    state_copy = state.copy()
    state_copy["status"] = "waiting_approval"
    state_copy = add_message(
        state_copy,
        "system",
        "Task requires human approval to continue"
    )

    return state_copy


def error_handler_node(state: WorkflowState) -> WorkflowState:
    """
    Error handler node - Handles workflow errors

    Args:
        state: Current workflow state

    Returns:
        WorkflowState: Updated state
    """
    logger.error(f"Error in workflow for task {state['task_id']}: {state.get('error')}")

    state_copy = state.copy()
    state_copy["status"] = "failed"
    state_copy = add_message(
        state_copy,
        "system",
        f"Workflow failed: {state.get('error', 'Unknown error')}"
    )

    return state_copy
