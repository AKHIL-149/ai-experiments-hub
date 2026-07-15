#!/usr/bin/env python3
"""
Workflow Runner Script

Helper script to easily run example workflows.

Usage:
    python examples/run_workflow.py --workflow code_review --input myfile.py
    python examples/run_workflow.py --workflow data_analysis --input data.csv
    python examples/run_workflow.py --workflow blog_post --topic "AI Trends"
    python examples/run_workflow.py --list
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from workflows.code_review_workflow import (
    create_code_review_workflow,
    create_quick_code_review_workflow
)
from workflows.data_analysis_workflow import (
    create_data_analysis_workflow,
    create_quick_data_summary_workflow,
    create_predictive_analysis_workflow
)
from workflows.content_generation_workflow import (
    create_blog_post_workflow,
    create_documentation_workflow,
    create_social_media_content_workflow
)


AVAILABLE_WORKFLOWS = {
    "code_review": {
        "func": create_code_review_workflow,
        "description": "Comprehensive code review with security and performance analysis",
        "input_type": "file"
    },
    "code_review_quick": {
        "func": create_quick_code_review_workflow,
        "description": "Quick code review for rapid feedback",
        "input_type": "file"
    },
    "data_analysis": {
        "func": create_data_analysis_workflow,
        "description": "End-to-end data analysis with insights",
        "input_type": "file"
    },
    "data_summary": {
        "func": create_quick_data_summary_workflow,
        "description": "Quick statistical data summary",
        "input_type": "file"
    },
    "predictive_analysis": {
        "func": create_predictive_analysis_workflow,
        "description": "Build and evaluate predictive models",
        "input_type": "file"
    },
    "blog_post": {
        "func": create_blog_post_workflow,
        "description": "Generate SEO-optimized blog post",
        "input_type": "topic"
    },
    "documentation": {
        "func": create_documentation_workflow,
        "description": "Generate comprehensive technical documentation",
        "input_type": "file"
    },
    "social_media": {
        "func": create_social_media_content_workflow,
        "description": "Create multi-platform social media content",
        "input_type": "topic"
    }
}


def list_workflows():
    """List all available workflows"""
    print("\n📋 Available Workflows:\n")
    print(f"{'Workflow ID':<25} {'Description':<60} {'Input Type':<10}")
    print("=" * 95)

    for wf_id, wf_info in AVAILABLE_WORKFLOWS.items():
        print(f"{wf_id:<25} {wf_info['description']:<60} {wf_info['input_type']:<10}")

    print("\n💡 Usage Examples:")
    print("  python examples/run_workflow.py --workflow code_review --input myfile.py")
    print("  python examples/run_workflow.py --workflow data_analysis --input data.csv")
    print("  python examples/run_workflow.py --workflow blog_post --topic 'AI Trends 2026'")
    print()


def display_workflow(workflow_config):
    """Display workflow configuration"""
    print("\n🔧 Workflow Configuration:")
    print("=" * 80)
    print(f"Name: {workflow_config['name']}")
    print(f"Description: {workflow_config['description']}")
    print(f"Type: {workflow_config['workflow_type']}")

    if 'metadata' in workflow_config:
        meta = workflow_config['metadata']
        print(f"\nMetadata:")
        print(f"  Category: {meta.get('category', 'N/A')}")
        print(f"  Estimated Duration: {meta.get('estimated_duration_minutes', 'N/A')} minutes")
        print(f"  Required Agents: {', '.join(meta.get('required_agents', []))}")
        print(f"  Tags: {', '.join(meta.get('tags', []))}")

    print(f"\nSteps ({len(workflow_config['steps'])} total):")
    for idx, step in enumerate(workflow_config['steps'], 1):
        deps = ", ".join(step['dependencies']) if step['dependencies'] else "None"
        agent = step.get('agent_role', step.get('step_type'))
        print(f"  {idx}. {step['step_name']} ({agent}) - Dependencies: {deps}")

    print("\n" + "=" * 80)


def create_task_input(workflow_config, input_data=None, topic=None):
    """Create task input from workflow config and user input"""
    task_input = {
        "workflow_config": workflow_config,
        "input_data": {},
        "metadata": {}
    }

    if input_data:
        # Read file if it's a path
        input_path = Path(input_data)
        if input_path.exists():
            task_input["input_data"]["file_path"] = str(input_path)
            task_input["input_data"]["file_name"] = input_path.name

            # Try to read file content (for small files)
            if input_path.stat().st_size < 1_000_000:  # < 1MB
                try:
                    with open(input_path, 'r', encoding='utf-8') as f:
                        task_input["input_data"]["content"] = f.read()
                except Exception as e:
                    print(f"⚠️  Could not read file content: {e}")
        else:
            task_input["input_data"]["raw_input"] = input_data

    if topic:
        task_input["input_data"]["topic"] = topic

    return task_input


def submit_to_api(workflow_config, task_input):
    """Submit workflow to API endpoint"""
    try:
        import requests

        API_BASE = "http://localhost:8001/api"

        # Create workflow
        print("\n📤 Submitting workflow to API...")
        response = requests.post(
            f"{API_BASE}/workflow-engine/workflows",
            json=workflow_config,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            workflow_id = result.get("workflow_id")
            print(f"✅ Workflow created: ID {workflow_id}")

            # Execute workflow
            exec_response = requests.post(
                f"{API_BASE}/workflow-engine/workflows/{workflow_id}/execute",
                json=task_input
            )

            if exec_response.status_code == 200:
                exec_result = exec_response.json()
                print(f"✅ Workflow execution started")
                print(f"\n📊 Monitor at: http://localhost:8001/api/workflow-engine/workflows/{workflow_id}")
                return True
            else:
                print(f"❌ Execution failed: {exec_response.text}")
                return False
        else:
            print(f"❌ Workflow creation failed: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API server at http://localhost:8001")
        print("   Make sure the server is running: python3 server.py")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def save_workflow_config(workflow_config, output_path):
    """Save workflow configuration to file"""
    with open(output_path, 'w') as f:
        json.dump(workflow_config, f, indent=2)
    print(f"\n💾 Workflow configuration saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Run example workflows for Multi-Agent Task Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available workflows
  python examples/run_workflow.py --list

  # Run code review
  python examples/run_workflow.py --workflow code_review --input myfile.py

  # Run data analysis
  python examples/run_workflow.py --workflow data_analysis --input data.csv

  # Generate blog post
  python examples/run_workflow.py --workflow blog_post --topic "AI Trends 2026"

  # Save workflow config to file
  python examples/run_workflow.py --workflow code_review --save workflow.json

  # Display workflow without executing
  python examples/run_workflow.py --workflow data_analysis --dry-run
        """
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available workflows"
    )

    parser.add_argument(
        "--workflow",
        type=str,
        choices=list(AVAILABLE_WORKFLOWS.keys()),
        help="Workflow to run"
    )

    parser.add_argument(
        "--input",
        type=str,
        help="Input file path or data"
    )

    parser.add_argument(
        "--topic",
        type=str,
        help="Topic for content generation workflows"
    )

    parser.add_argument(
        "--save",
        type=str,
        help="Save workflow configuration to file"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display workflow without executing"
    )

    parser.add_argument(
        "--submit",
        action="store_true",
        default=True,
        help="Submit workflow to API (default: True)"
    )

    args = parser.parse_args()

    # List workflows
    if args.list:
        list_workflows()
        return

    # Validate workflow selection
    if not args.workflow:
        parser.print_help()
        print("\n❌ Error: --workflow is required (or use --list to see available workflows)")
        sys.exit(1)

    # Get workflow function
    workflow_info = AVAILABLE_WORKFLOWS[args.workflow]
    workflow_func = workflow_info["func"]

    # Create workflow configuration
    print(f"\n🚀 Creating workflow: {args.workflow}")
    workflow_config = workflow_func()

    # Display workflow
    display_workflow(workflow_config)

    # Save to file if requested
    if args.save:
        save_workflow_config(workflow_config, args.save)

    # Exit if dry-run
    if args.dry_run:
        print("\n✨ Dry-run complete. Use --submit to execute workflow.")
        return

    # Create task input
    task_input = create_task_input(
        workflow_config,
        input_data=args.input,
        topic=args.topic
    )

    # Submit to API
    if args.submit:
        success = submit_to_api(workflow_config, task_input)
        sys.exit(0 if success else 1)
    else:
        print("\n✨ Workflow configuration ready. Use --submit to execute.")


if __name__ == "__main__":
    main()
