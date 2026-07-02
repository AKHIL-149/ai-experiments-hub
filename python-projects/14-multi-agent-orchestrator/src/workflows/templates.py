"""
Workflow Templates

Pre-built workflow templates for common multi-agent patterns.
"""

from typing import Dict, Any
from langgraph.graph import END

from src.workflows.base_workflow import BaseWorkflow, WorkflowConfig, WorkflowState
from src.workflows.agent_graph import AgentGraph
from src.core.logging import logger


class ResearchWriteWorkflow(BaseWorkflow):
    """
    Research → Write Workflow

    Sequential workflow where a research agent gathers information,
    then a writer agent creates content based on the research.
    """

    def __init__(self):
        """Initialize research-write workflow"""
        config = WorkflowConfig(
            name="Research & Write",
            description="Research a topic then write content about it",
            version="1.0.0",
            timeout_seconds=600,
            max_retries=2
        )
        super().__init__(config)

    def build_graph(self):
        """Build the research-write graph"""
        # Create agent graph
        agent_graph = AgentGraph("research_write")

        # Add nodes
        agent_graph.add_agent_node(
            name="research",
            agent_type="research",
            description="Research the topic"
        )

        agent_graph.add_agent_node(
            name="write",
            agent_type="writer",
            description="Write content based on research"
        )

        # Add edges
        agent_graph.add_edge("research", "write")
        agent_graph.add_edge("write", END)

        # Set entry point
        graph = agent_graph.build()
        graph.set_entry_point("research")

        logger.info("Built Research & Write workflow")
        return graph


class CodeReviewWorkflow(BaseWorkflow):
    """
    Code → Review → Fix Workflow

    Workflow for code generation with automatic review and fixes.
    """

    def __init__(self):
        """Initialize code review workflow"""
        config = WorkflowConfig(
            name="Code Review",
            description="Generate code, review it, and apply fixes",
            version="1.0.0",
            timeout_seconds=900,
            max_retries=3
        )
        super().__init__(config)

    def build_graph(self):
        """Build the code review graph"""
        agent_graph = AgentGraph("code_review")

        # Add nodes
        agent_graph.add_agent_node(
            name="code_generation",
            agent_type="code",
            description="Generate code from requirements"
        )

        agent_graph.add_agent_node(
            name="code_review",
            agent_type="code",
            description="Review generated code"
        )

        # Add conditional node for review decision
        def check_review_result(state: Dict[str, Any]) -> str:
            """Check if code passed review"""
            workflow_state = WorkflowState(**state)

            review_result = workflow_state.agent_results.get("code_review", {})

            # Simple heuristic: check if there are issues in the review
            if review_result.get("error"):
                return "needs_fix"

            review_output = review_result.get("output", {})

            # If review found issues, fix them
            if isinstance(review_output, dict):
                explanation = review_output.get("explanation", "")
                if any(word in explanation.lower() for word in ["issue", "problem", "bug", "error", "fix"]):
                    return "needs_fix"

            return "approved"

        agent_graph.add_agent_node(
            name="apply_fixes",
            agent_type="code",
            description="Apply fixes based on review"
        )

        # Add edges
        agent_graph.add_edge("code_generation", "code_review")

        # Conditional edge based on review result
        agent_graph.add_conditional_edge(
            source="code_review",
            condition=check_review_result,
            condition_map={
                "approved": END,
                "needs_fix": "apply_fixes"
            }
        )

        agent_graph.add_edge("apply_fixes", END)

        # Set entry point
        graph = agent_graph.build()
        graph.set_entry_point("code_generation")

        logger.info("Built Code Review workflow")
        return graph


class AnalysisPlanningWorkflow(BaseWorkflow):
    """
    Analysis → Planning → Execution Workflow

    Parallel analysis followed by planning and execution.
    """

    def __init__(self):
        """Initialize analysis-planning workflow"""
        config = WorkflowConfig(
            name="Analysis & Planning",
            description="Analyze data, create plan, and execute",
            version="1.0.0",
            timeout_seconds=1200,
            parallel_execution=True
        )
        super().__init__(config)

    def build_graph(self):
        """Build the analysis-planning graph"""
        agent_graph = AgentGraph("analysis_planning")

        # Add parallel analysis nodes
        agent_graph.add_parallel_node(
            name="parallel_analysis",
            agent_types=["research", "data_analyst"],
            description="Research and analyze in parallel"
        )

        # Add planning node
        agent_graph.add_agent_node(
            name="planning",
            agent_type="planner",
            description="Create execution plan"
        )

        # Add conditional node for complexity check
        def check_plan_complexity(state: Dict[str, Any]) -> str:
            """Check if plan is simple or complex"""
            workflow_state = WorkflowState(**state)

            plan_result = workflow_state.agent_results.get("planning", {})
            plan_output = plan_result.get("output", {})

            # Check number of tasks
            tasks = plan_output.get("tasks", [])

            if len(tasks) > 5:
                return "complex"
            return "simple"

        # Add execution nodes
        agent_graph.add_agent_node(
            name="simple_execution",
            agent_type="code",
            description="Execute simple plan"
        )

        agent_graph.add_agent_node(
            name="complex_execution",
            agent_type="planner",
            description="Break down and execute complex plan"
        )

        # Add edges
        agent_graph.add_edge("parallel_analysis", "planning")

        # Conditional routing based on plan complexity
        agent_graph.add_conditional_edge(
            source="planning",
            condition=check_plan_complexity,
            condition_map={
                "simple": "simple_execution",
                "complex": "complex_execution"
            }
        )

        agent_graph.add_edge("simple_execution", END)
        agent_graph.add_edge("complex_execution", END)

        # Set entry point
        graph = agent_graph.build()
        graph.set_entry_point("parallel_analysis")

        logger.info("Built Analysis & Planning workflow")
        return graph


# Workflow Registry
WORKFLOW_TEMPLATES = {
    "research_write": ResearchWriteWorkflow,
    "code_review": CodeReviewWorkflow,
    "analysis_planning": AnalysisPlanningWorkflow
}


def get_workflow_template(template_name: str) -> BaseWorkflow:
    """
    Get a workflow template by name

    Args:
        template_name: Template identifier

    Returns:
        Workflow instance

    Raises:
        ValueError: If template not found
    """
    if template_name not in WORKFLOW_TEMPLATES:
        available = list(WORKFLOW_TEMPLATES.keys())
        raise ValueError(f"Unknown workflow template: {template_name}. Available: {available}")

    workflow_class = WORKFLOW_TEMPLATES[template_name]
    return workflow_class()


def list_workflow_templates() -> Dict[str, str]:
    """
    List all available workflow templates

    Returns:
        Dict mapping template names to descriptions
    """
    templates = {}

    for name, workflow_class in WORKFLOW_TEMPLATES.items():
        instance = workflow_class()
        templates[name] = instance.config.description

    return templates
