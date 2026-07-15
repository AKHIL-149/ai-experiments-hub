"""
Data Analysis Workflow Example

This workflow demonstrates how to orchestrate agents to perform
comprehensive data analysis with insights and visualizations.
"""

from typing import Dict, Any


def create_data_analysis_workflow() -> Dict[str, Any]:
    """
    Create a data analysis workflow that:
    1. Explores and validates data
    2. Performs statistical analysis
    3. Identifies patterns and trends
    4. Generates insights and recommendations
    5. Creates visualization suggestions

    Returns:
        Workflow configuration dictionary
    """
    return {
        "name": "Data Analysis Workflow",
        "description": "End-to-end data analysis with insights and recommendations",
        "workflow_type": "custom",
        "steps": [
            {
                "step_name": "data_validation",
                "step_type": "agent",
                "agent_role": "data_analyst",
                "config": {
                    "task": "Validate data quality and completeness",
                    "checks": [
                        "missing_values",
                        "data_types",
                        "outliers",
                        "duplicates",
                        "data_consistency"
                    ],
                    "generate_report": True
                },
                "dependencies": []
            },
            {
                "step_name": "exploratory_analysis",
                "step_type": "agent",
                "agent_role": "data_analyst",
                "config": {
                    "task": "Perform exploratory data analysis",
                    "analyses": [
                        "descriptive_statistics",
                        "distribution_analysis",
                        "correlation_analysis",
                        "feature_importance"
                    ],
                    "output_format": "structured_json"
                },
                "dependencies": ["data_validation"]
            },
            {
                "step_name": "pattern_detection",
                "step_type": "agent",
                "agent_role": "research",
                "config": {
                    "task": "Identify patterns, trends, and anomalies",
                    "methods": [
                        "time_series_analysis",
                        "clustering",
                        "anomaly_detection",
                        "trend_analysis"
                    ]
                },
                "dependencies": ["exploratory_analysis"]
            },
            {
                "step_name": "statistical_testing",
                "step_type": "agent",
                "agent_role": "data_analyst",
                "config": {
                    "task": "Perform statistical hypothesis testing",
                    "tests": [
                        "t_test",
                        "chi_square",
                        "anova",
                        "correlation_tests"
                    ],
                    "significance_level": 0.05
                },
                "dependencies": ["exploratory_analysis"]
            },
            {
                "step_name": "generate_insights",
                "step_type": "agent",
                "agent_role": "data_analyst",
                "config": {
                    "task": "Generate actionable insights from analysis results",
                    "focus_areas": [
                        "key_findings",
                        "business_implications",
                        "recommendations",
                        "risk_factors"
                    ]
                },
                "dependencies": [
                    "pattern_detection",
                    "statistical_testing"
                ]
            },
            {
                "step_name": "create_visualizations",
                "step_type": "agent",
                "agent_role": "code",
                "config": {
                    "task": "Generate visualization code for key findings",
                    "libraries": ["matplotlib", "seaborn", "plotly"],
                    "chart_types": [
                        "distribution_plots",
                        "correlation_heatmaps",
                        "time_series_plots",
                        "scatter_plots"
                    ]
                },
                "dependencies": ["generate_insights"]
            },
            {
                "step_name": "write_analysis_report",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Create comprehensive data analysis report",
                    "output_format": "markdown",
                    "sections": [
                        "executive_summary",
                        "data_overview",
                        "methodology",
                        "key_findings",
                        "statistical_results",
                        "visualizations",
                        "conclusions",
                        "recommendations"
                    ],
                    "include_code_samples": True
                },
                "dependencies": [
                    "data_validation",
                    "generate_insights",
                    "create_visualizations"
                ]
            }
        ],
        "metadata": {
            "category": "data_analysis",
            "estimated_duration_minutes": 20,
            "required_agents": ["data_analyst", "research", "code", "writer"],
            "tags": ["analytics", "statistics", "insights"]
        }
    }


def create_quick_data_summary_workflow() -> Dict[str, Any]:
    """
    Quick data summary workflow for rapid insights
    """
    return {
        "name": "Quick Data Summary",
        "description": "Fast data summary with key statistics and insights",
        "workflow_type": "custom",
        "steps": [
            {
                "step_name": "calculate_statistics",
                "step_type": "agent",
                "agent_role": "data_analyst",
                "config": {
                    "task": "Calculate descriptive statistics",
                    "metrics": [
                        "mean", "median", "std", "min", "max",
                        "quartiles", "missing_rate"
                    ]
                },
                "dependencies": []
            },
            {
                "step_name": "generate_summary",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Create concise data summary",
                    "output_format": "bullet_points",
                    "max_length_words": 200
                },
                "dependencies": ["calculate_statistics"]
            }
        ],
        "metadata": {
            "category": "data_analysis",
            "estimated_duration_minutes": 3,
            "required_agents": ["data_analyst", "writer"],
            "tags": ["analytics", "quick-summary"]
        }
    }


def create_predictive_analysis_workflow() -> Dict[str, Any]:
    """
    Predictive analytics workflow with model recommendations
    """
    return {
        "name": "Predictive Analysis Workflow",
        "description": "Build and evaluate predictive models with recommendations",
        "workflow_type": "custom",
        "steps": [
            {
                "step_name": "feature_engineering",
                "step_type": "agent",
                "agent_role": "data_analyst",
                "config": {
                    "task": "Create and select features for modeling",
                    "techniques": [
                        "encoding_categorical",
                        "scaling_numerical",
                        "feature_selection",
                        "interaction_terms"
                    ]
                },
                "dependencies": []
            },
            {
                "step_name": "model_selection",
                "step_type": "agent",
                "agent_role": "research",
                "config": {
                    "task": "Recommend suitable models based on data characteristics",
                    "consider": [
                        "problem_type",
                        "data_size",
                        "feature_types",
                        "interpretability_requirements"
                    ]
                },
                "dependencies": ["feature_engineering"]
            },
            {
                "step_name": "generate_model_code",
                "step_type": "agent",
                "agent_role": "code",
                "config": {
                    "task": "Generate model training and evaluation code",
                    "frameworks": ["scikit-learn", "xgboost"],
                    "include_validation": True,
                    "include_metrics": True
                },
                "dependencies": ["model_selection"]
            },
            {
                "step_name": "interpret_results",
                "step_type": "agent",
                "agent_role": "data_analyst",
                "config": {
                    "task": "Interpret model results and feature importance",
                    "explain": [
                        "model_performance",
                        "feature_importance",
                        "prediction_confidence",
                        "limitations"
                    ]
                },
                "dependencies": ["generate_model_code"]
            },
            {
                "step_name": "create_report",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Create predictive analysis report",
                    "sections": [
                        "problem_definition",
                        "data_preparation",
                        "model_selection",
                        "results",
                        "recommendations"
                    ]
                },
                "dependencies": ["interpret_results"]
            }
        ],
        "metadata": {
            "category": "predictive_analytics",
            "estimated_duration_minutes": 30,
            "required_agents": ["data_analyst", "research", "code", "writer"],
            "tags": ["machine-learning", "predictions", "modeling"]
        }
    }


# Example usage:
if __name__ == "__main__":
    import json

    workflows = [
        ("Full Data Analysis", create_data_analysis_workflow()),
        ("Quick Summary", create_quick_data_summary_workflow()),
        ("Predictive Analysis", create_predictive_analysis_workflow())
    ]

    for name, workflow in workflows:
        print(f"\n{name} Workflow:")
        print("=" * 80)
        print(json.dumps(workflow, indent=2))
        print()
