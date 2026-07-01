"""
Workflow state management for LangGraph
"""

from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime


class WorkflowState(TypedDict, total=False):
    """
    State object for LangGraph workflows

    This state is passed between nodes in the workflow graph
    and contains all information needed for task execution.
    """
    # Task information
    task_id: int
    task_title: str
    task_description: str
    task_type: str
    priority: int

    # Input and output data
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]

    # Workflow execution
    current_node: str
    next_node: Optional[str]
    workflow_path: List[str]

    # Agent assignments
    assigned_agents: Dict[str, int]  # node_name -> agent_id

    # Node outputs
    research_output: Optional[Dict[str, Any]]
    code_output: Optional[Dict[str, Any]]
    review_output: Optional[Dict[str, Any]]
    test_output: Optional[Dict[str, Any]]
    document_output: Optional[Dict[str, Any]]

    # Status and progress
    status: str
    progress: int
    error: Optional[str]

    # Metadata
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    execution_time: Optional[float]

    # Human-in-the-loop
    requires_approval: bool
    approval_status: Optional[str]
    approval_feedback: Optional[str]

    # Cost tracking
    total_tokens: int
    total_cost: float
    llm_calls: List[Dict[str, Any]]

    # Messages and logs
    messages: List[Dict[str, str]]
    logs: List[str]


def create_initial_state(
    task_id: int,
    task_title: str,
    task_description: str,
    task_type: str,
    priority: int = 5,
    input_data: Optional[Dict[str, Any]] = None
) -> WorkflowState:
    """
    Create initial workflow state

    Args:
        task_id: Task ID
        task_title: Task title
        task_description: Task description
        task_type: Task type (research, coding, review, etc.)
        priority: Task priority (1-10)
        input_data: Additional input data

    Returns:
        WorkflowState: Initial state object
    """
    return WorkflowState(
        task_id=task_id,
        task_title=task_title,
        task_description=task_description,
        task_type=task_type,
        priority=priority,
        input_data=input_data or {},
        output_data={},
        current_node="start",
        next_node=None,
        workflow_path=["start"],
        assigned_agents={},
        research_output=None,
        code_output=None,
        review_output=None,
        test_output=None,
        document_output=None,
        status="pending",
        progress=0,
        error=None,
        started_at=None,
        completed_at=None,
        execution_time=None,
        requires_approval=False,
        approval_status=None,
        approval_feedback=None,
        total_tokens=0,
        total_cost=0.0,
        llm_calls=[],
        messages=[],
        logs=[]
    )


def update_node_output(
    state: WorkflowState,
    node_name: str,
    output: Dict[str, Any]
) -> WorkflowState:
    """
    Update state with node output

    Args:
        state: Current workflow state
        node_name: Name of the node
        output: Node output data

    Returns:
        WorkflowState: Updated state
    """
    state_copy = state.copy()

    # Update specific node output
    if node_name == "research":
        state_copy["research_output"] = output
    elif node_name == "code":
        state_copy["code_output"] = output
    elif node_name == "review":
        state_copy["review_output"] = output
    elif node_name == "test":
        state_copy["test_output"] = output
    elif node_name == "document":
        state_copy["document_output"] = output

    # Update workflow path
    if node_name not in state_copy.get("workflow_path", []):
        state_copy["workflow_path"].append(node_name)

    # Update current node
    state_copy["current_node"] = node_name

    # Add log entry
    state_copy["logs"].append(f"Completed node: {node_name}")

    return state_copy


def add_message(
    state: WorkflowState,
    role: str,
    content: str
) -> WorkflowState:
    """
    Add message to workflow state

    Args:
        state: Current workflow state
        role: Message role (user, assistant, system)
        content: Message content

    Returns:
        WorkflowState: Updated state
    """
    state_copy = state.copy()
    state_copy["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat()
    })
    return state_copy


def track_llm_call(
    state: WorkflowState,
    model: str,
    tokens: int,
    cost: float
) -> WorkflowState:
    """
    Track LLM API call

    Args:
        state: Current workflow state
        model: Model name
        tokens: Tokens used
        cost: Cost in USD

    Returns:
        WorkflowState: Updated state
    """
    state_copy = state.copy()

    # Add LLM call record
    state_copy["llm_calls"].append({
        "model": model,
        "tokens": tokens,
        "cost": cost,
        "timestamp": datetime.utcnow().isoformat()
    })

    # Update totals
    state_copy["total_tokens"] += tokens
    state_copy["total_cost"] += cost

    return state_copy
