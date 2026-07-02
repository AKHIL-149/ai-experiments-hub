"""
Workflow orchestration using LangGraph
"""

# Original imports
from src.workflows.graph import create_workflow_graph
from src.workflows.state import WorkflowState as LegacyWorkflowState
from src.workflows.nodes import (
    research_node,
    code_node,
    review_node,
    test_node,
    document_node
)

# New agent-based workflow system
from src.workflows.base_workflow import BaseWorkflow, WorkflowState, WorkflowConfig
from src.workflows.agent_graph import AgentGraph, GraphNode, GraphEdge
from src.workflows.templates import (
    ResearchWriteWorkflow,
    CodeReviewWorkflow,
    AnalysisPlanningWorkflow,
    get_workflow_template,
    list_workflow_templates
)

__all__ = [
    # Legacy
    'create_workflow_graph',
    'LegacyWorkflowState',
    'research_node',
    'code_node',
    'review_node',
    'test_node',
    'document_node',
    # New system
    "BaseWorkflow",
    "WorkflowState",
    "WorkflowConfig",
    "AgentGraph",
    "GraphNode",
    "GraphEdge",
    "ResearchWriteWorkflow",
    "CodeReviewWorkflow",
    "AnalysisPlanningWorkflow",
    "get_workflow_template",
    "list_workflow_templates",
]
