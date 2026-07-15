"""
Content Generation Workflow Example

This workflow demonstrates how to orchestrate agents to create
high-quality content with research, writing, and review stages.
"""

from typing import Dict, Any


def create_blog_post_workflow() -> Dict[str, Any]:
    """
    Create a blog post generation workflow that:
    1. Researches the topic
    2. Creates an outline
    3. Writes the content
    4. Reviews and refines
    5. Generates SEO metadata

    Returns:
        Workflow configuration dictionary
    """
    return {
        "name": "Blog Post Generation Workflow",
        "description": "Create high-quality blog posts with research and SEO optimization",
        "workflow_type": "custom",
        "steps": [
            {
                "step_name": "research_topic",
                "step_type": "agent",
                "agent_role": "research",
                "config": {
                    "task": "Research topic and gather relevant information",
                    "research_areas": [
                        "key_concepts",
                        "current_trends",
                        "statistics_data",
                        "expert_opinions",
                        "related_topics"
                    ],
                    "depth": "comprehensive"
                },
                "dependencies": []
            },
            {
                "step_name": "create_outline",
                "step_type": "agent",
                "agent_role": "planner",
                "config": {
                    "task": "Create structured content outline",
                    "include": [
                        "introduction",
                        "main_sections",
                        "key_points",
                        "conclusion",
                        "call_to_action"
                    ],
                    "target_word_count": 1500
                },
                "dependencies": ["research_topic"]
            },
            {
                "step_name": "write_introduction",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Write engaging introduction",
                    "style": "conversational_professional",
                    "include_hook": True,
                    "target_length": 150
                },
                "dependencies": ["create_outline"]
            },
            {
                "step_name": "write_main_content",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Write main content sections",
                    "style": "informative_engaging",
                    "formatting": [
                        "subheadings",
                        "bullet_points",
                        "examples",
                        "transitions"
                    ],
                    "tone": "professional"
                },
                "dependencies": ["create_outline", "research_topic"]
            },
            {
                "step_name": "write_conclusion",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Write conclusion and call-to-action",
                    "elements": [
                        "summary",
                        "key_takeaways",
                        "call_to_action",
                        "next_steps"
                    ]
                },
                "dependencies": ["write_main_content"]
            },
            {
                "step_name": "review_content",
                "step_type": "agent",
                "agent_role": "research",
                "config": {
                    "task": "Review content for accuracy and quality",
                    "check": [
                        "factual_accuracy",
                        "logical_flow",
                        "clarity",
                        "grammar_spelling"
                    ],
                    "suggest_improvements": True
                },
                "dependencies": [
                    "write_introduction",
                    "write_main_content",
                    "write_conclusion"
                ]
            },
            {
                "step_name": "refine_content",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Refine content based on review feedback",
                    "focus": [
                        "improve_clarity",
                        "enhance_readability",
                        "fix_issues",
                        "polish_writing"
                    ]
                },
                "dependencies": ["review_content"]
            },
            {
                "step_name": "generate_seo_metadata",
                "step_type": "agent",
                "agent_role": "research",
                "config": {
                    "task": "Generate SEO-optimized metadata",
                    "create": [
                        "title_tag",
                        "meta_description",
                        "keywords",
                        "slug",
                        "social_media_snippets"
                    ],
                    "optimize_for": "search_engines"
                },
                "dependencies": ["refine_content"]
            }
        ],
        "metadata": {
            "category": "content_creation",
            "estimated_duration_minutes": 25,
            "required_agents": ["research", "planner", "writer"],
            "tags": ["blog", "seo", "content-marketing"]
        }
    }


def create_documentation_workflow() -> Dict[str, Any]:
    """
    Technical documentation generation workflow
    """
    return {
        "name": "Technical Documentation Workflow",
        "description": "Generate comprehensive technical documentation",
        "workflow_type": "custom",
        "steps": [
            {
                "step_name": "analyze_codebase",
                "step_type": "agent",
                "agent_role": "code",
                "config": {
                    "task": "Analyze code structure and functionality",
                    "extract": [
                        "modules",
                        "classes",
                        "functions",
                        "dependencies",
                        "apis"
                    ]
                },
                "dependencies": []
            },
            {
                "step_name": "create_documentation_structure",
                "step_type": "agent",
                "agent_role": "planner",
                "config": {
                    "task": "Plan documentation structure",
                    "sections": [
                        "overview",
                        "installation",
                        "configuration",
                        "api_reference",
                        "examples",
                        "troubleshooting"
                    ]
                },
                "dependencies": ["analyze_codebase"]
            },
            {
                "step_name": "write_overview",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Write project overview and introduction",
                    "include": [
                        "purpose",
                        "features",
                        "architecture",
                        "prerequisites"
                    ],
                    "style": "clear_concise"
                },
                "dependencies": ["create_documentation_structure"]
            },
            {
                "step_name": "generate_api_docs",
                "step_type": "agent",
                "agent_role": "code",
                "config": {
                    "task": "Generate API reference documentation",
                    "format": "markdown",
                    "include": [
                        "endpoints",
                        "parameters",
                        "responses",
                        "examples",
                        "error_codes"
                    ]
                },
                "dependencies": ["analyze_codebase"]
            },
            {
                "step_name": "create_code_examples",
                "step_type": "agent",
                "agent_role": "code",
                "config": {
                    "task": "Create usage examples and tutorials",
                    "languages": ["python", "curl"],
                    "example_types": [
                        "quick_start",
                        "common_use_cases",
                        "advanced_scenarios"
                    ],
                    "include_output": True
                },
                "dependencies": ["generate_api_docs"]
            },
            {
                "step_name": "write_guides",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Write installation and configuration guides",
                    "format": "step_by_step",
                    "include_screenshots": False,
                    "platforms": ["linux", "macos", "windows"]
                },
                "dependencies": ["create_documentation_structure"]
            },
            {
                "step_name": "compile_documentation",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Compile all documentation sections",
                    "output_format": "markdown",
                    "generate_toc": True,
                    "add_navigation": True
                },
                "dependencies": [
                    "write_overview",
                    "generate_api_docs",
                    "create_code_examples",
                    "write_guides"
                ]
            }
        ],
        "metadata": {
            "category": "documentation",
            "estimated_duration_minutes": 30,
            "required_agents": ["code", "planner", "writer"],
            "tags": ["technical-docs", "api-docs", "developer-docs"]
        }
    }


def create_social_media_content_workflow() -> Dict[str, Any]:
    """
    Social media content generation workflow
    """
    return {
        "name": "Social Media Content Workflow",
        "description": "Generate multi-platform social media content",
        "workflow_type": "custom",
        "steps": [
            {
                "step_name": "research_trends",
                "step_type": "agent",
                "agent_role": "research",
                "config": {
                    "task": "Research current trends and topics",
                    "platforms": ["twitter", "linkedin", "instagram"],
                    "analyze": [
                        "trending_topics",
                        "hashtags",
                        "engagement_patterns"
                    ]
                },
                "dependencies": []
            },
            {
                "step_name": "create_content_calendar",
                "step_type": "agent",
                "agent_role": "planner",
                "config": {
                    "task": "Plan content calendar",
                    "duration_days": 7,
                    "posts_per_day": 3,
                    "variety": [
                        "promotional",
                        "educational",
                        "engagement",
                        "curated"
                    ]
                },
                "dependencies": ["research_trends"]
            },
            {
                "step_name": "write_twitter_posts",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Write Twitter posts",
                    "max_length": 280,
                    "include_hashtags": True,
                    "include_cta": True,
                    "count": 7
                },
                "dependencies": ["create_content_calendar"]
            },
            {
                "step_name": "write_linkedin_posts",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Write LinkedIn posts",
                    "style": "professional_thought_leadership",
                    "length": "medium",
                    "count": 5
                },
                "dependencies": ["create_content_calendar"]
            },
            {
                "step_name": "compile_content_package",
                "step_type": "agent",
                "agent_role": "planner",
                "config": {
                    "task": "Organize all content with scheduling recommendations",
                    "output_format": "structured_json",
                    "include": [
                        "post_text",
                        "platform",
                        "suggested_time",
                        "hashtags",
                        "media_suggestions"
                    ]
                },
                "dependencies": [
                    "write_twitter_posts",
                    "write_linkedin_posts"
                ]
            }
        ],
        "metadata": {
            "category": "social_media",
            "estimated_duration_minutes": 15,
            "required_agents": ["research", "planner", "writer"],
            "tags": ["social-media", "content-marketing", "engagement"]
        }
    }


# Example usage:
if __name__ == "__main__":
    import json

    workflows = [
        ("Blog Post", create_blog_post_workflow()),
        ("Technical Documentation", create_documentation_workflow()),
        ("Social Media Content", create_social_media_content_workflow())
    ]

    for name, workflow in workflows:
        print(f"\n{name} Workflow:")
        print("=" * 80)
        print(json.dumps(workflow, indent=2))
        print()
