"""
Code Review Workflow Example

This workflow demonstrates how to orchestrate multiple agents to perform
a comprehensive code review with automated analysis and suggestions.
"""

from typing import Dict, Any
from src.workflows.state import WorkflowState


def create_code_review_workflow() -> Dict[str, Any]:
    """
    Create a code review workflow that:
    1. Analyzes code quality and structure
    2. Identifies potential bugs and security issues
    3. Suggests improvements and refactorings
    4. Generates comprehensive review report

    Returns:
        Workflow configuration dictionary
    """
    return {
        "name": "Code Review Workflow",
        "description": "Automated code review with quality analysis and improvement suggestions",
        "workflow_type": "custom",
        "steps": [
            {
                "step_name": "analyze_code_quality",
                "step_type": "agent",
                "agent_role": "code",
                "config": {
                    "task": "Analyze code quality, structure, and adherence to best practices",
                    "output_format": "structured_analysis",
                    "focus_areas": [
                        "code organization",
                        "naming conventions",
                        "code complexity",
                        "duplication detection"
                    ]
                },
                "dependencies": []
            },
            {
                "step_name": "security_scan",
                "step_type": "agent",
                "agent_role": "research",
                "config": {
                    "task": "Identify security vulnerabilities and potential risks",
                    "output_format": "security_report",
                    "check_items": [
                        "SQL injection risks",
                        "XSS vulnerabilities",
                        "authentication issues",
                        "data validation",
                        "sensitive data exposure"
                    ]
                },
                "dependencies": []
            },
            {
                "step_name": "performance_analysis",
                "step_type": "agent",
                "agent_role": "data_analyst",
                "config": {
                    "task": "Analyze performance bottlenecks and optimization opportunities",
                    "output_format": "performance_metrics",
                    "metrics": [
                        "time complexity",
                        "space complexity",
                        "database query efficiency",
                        "algorithm optimization"
                    ]
                },
                "dependencies": []
            },
            {
                "step_name": "suggest_refactorings",
                "step_type": "agent",
                "agent_role": "code",
                "config": {
                    "task": "Generate refactoring suggestions based on analysis results",
                    "output_format": "refactoring_plan",
                    "include_code_samples": True
                },
                "dependencies": [
                    "analyze_code_quality",
                    "security_scan",
                    "performance_analysis"
                ]
            },
            {
                "step_name": "generate_review_report",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Create comprehensive code review report",
                    "output_format": "markdown",
                    "include_sections": [
                        "executive_summary",
                        "quality_assessment",
                        "security_findings",
                        "performance_analysis",
                        "refactoring_suggestions",
                        "priority_recommendations"
                    ]
                },
                "dependencies": [
                    "analyze_code_quality",
                    "security_scan",
                    "performance_analysis",
                    "suggest_refactorings"
                ]
            },
            {
                "step_name": "human_review",
                "step_type": "approval_gate",
                "config": {
                    "approval_type": "review_acceptance",
                    "timeout_hours": 24,
                    "reviewers": ["team_lead", "senior_developer"]
                },
                "dependencies": ["generate_review_report"]
            }
        ],
        "metadata": {
            "category": "code_quality",
            "estimated_duration_minutes": 15,
            "required_agents": ["code", "research", "data_analyst", "writer"],
            "tags": ["code-review", "quality-assurance", "security"]
        }
    }


def create_quick_code_review_workflow() -> Dict[str, Any]:
    """
    Simplified code review workflow for faster feedback
    """
    return {
        "name": "Quick Code Review",
        "description": "Fast code review focusing on critical issues only",
        "workflow_type": "custom",
        "steps": [
            {
                "step_name": "quick_analysis",
                "step_type": "agent",
                "agent_role": "code",
                "config": {
                    "task": "Perform quick code analysis focusing on critical issues",
                    "priority": "high",
                    "time_limit_minutes": 5
                },
                "dependencies": []
            },
            {
                "step_name": "generate_feedback",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Generate concise feedback report",
                    "output_format": "bullet_points"
                },
                "dependencies": ["quick_analysis"]
            }
        ],
        "metadata": {
            "category": "code_quality",
            "estimated_duration_minutes": 5,
            "required_agents": ["code", "writer"],
            "tags": ["code-review", "quick-feedback"]
        }
    }


# Example usage:
if __name__ == "__main__":
    import json

    # Full code review
    full_review = create_code_review_workflow()
    print("Full Code Review Workflow:")
    print(json.dumps(full_review, indent=2))

    print("\n" + "="*80 + "\n")

    # Quick review
    quick_review = create_quick_code_review_workflow()
    print("Quick Code Review Workflow:")
    print(json.dumps(quick_review, indent=2))
