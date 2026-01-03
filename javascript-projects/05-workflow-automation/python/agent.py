#!/usr/bin/env python3
"""AI agent for workflow task execution."""

import sys
import json
import argparse
import os
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

from llm_client import LLMClient
from tool_registry import ToolRegistry


class WorkflowAgent:
    """Autonomous agent that executes tasks using LLM reasoning and tools."""

    def __init__(self, backend: str = "ollama", model: str = None):
        self.llm_client = LLMClient(backend=backend, model=model)
        self.tool_registry = ToolRegistry()
        self.tools_used = []
        self.execution_steps = []

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task by analyzing it, selecting tools, and synthesizing results.

        Args:
            task: Task definition containing 'instruction' and optional parameters

        Returns:
            Execution result with status and output
        """
        instruction = task.get("instruction", "")
        context = task.get("context", {})

        if not instruction:
            raise ValueError("Task must contain 'instruction' field")

        try:
            # Step 1: Analyze task and determine tools needed
            analysis = self._analyze_task(instruction, context)
            self.execution_steps.append({"step": "analyze", "result": analysis})

            # Step 2: Execute selected tools
            tool_results = self._execute_tools(analysis.get("tools", []))
            self.execution_steps.append({"step": "execute_tools", "results": tool_results})

            # Step 3: Synthesize final result
            final_result = self._synthesize_result(instruction, tool_results, context)
            self.execution_steps.append({"step": "synthesize", "result": final_result})

            return {
                "success": True,
                "result": final_result,
                "tools_used": self.tools_used,
                "execution_steps": len(self.execution_steps)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tools_used": self.tools_used,
                "execution_steps": self.execution_steps
            }

    def _analyze_task(self, instruction: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to analyze task and determine which tools to use."""
        available_tools = self.tool_registry.get_tool_descriptions()

        tools_desc = "\n".join([
            f"- {tool['name']}: {tool['description']}"
            for tool in available_tools
        ])

        prompt = f"""You are an AI agent analyzing a task to determine which tools to use.

Available Tools:
{tools_desc}

Task: {instruction}

Context: {json.dumps(context) if context else "None"}

Analyze this task and respond with a JSON object containing:
1. "tools": array of tool calls needed to complete this task
2. "reasoning": your thought process

Each tool call should have:
- "name": tool name
- "parameters": object with tool parameters

Example response:
{{
  "reasoning": "To complete this task, I need to read a file first, then process the content",
  "tools": [
    {{"name": "file_operations", "parameters": {{"operation": "read", "path": "data.txt"}}}}
  ]
}}

Respond ONLY with valid JSON:"""

        response = self.llm_client.generate(prompt, temperature=0.3, max_tokens=800)

        try:
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                # Fallback: no tools needed
                return {"reasoning": "No tools required", "tools": []}
        except json.JSONDecodeError:
            print(f"Failed to parse LLM response as JSON: {response}", file=sys.stderr)
            return {"reasoning": "Parse error", "tools": []}

    def _execute_tools(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute a list of tool calls."""
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            parameters = tool_call.get("parameters", {})

            if not tool_name:
                continue

            print(f"Executing tool: {tool_name}", file=sys.stderr)
            self.tools_used.append(tool_name)

            result = self.tool_registry.execute_tool(tool_name, parameters)
            results.append({
                "tool": tool_name,
                "parameters": parameters,
                "result": result
            })

        return results

    def _synthesize_result(
        self,
        instruction: str,
        tool_results: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> str:
        """Synthesize final result from tool outputs."""
        if not tool_results:
            # No tools were used, just generate a response
            prompt = f"""Task: {instruction}

Context: {json.dumps(context) if context else "None"}

Provide a brief response to this task:"""
            return self.llm_client.generate(prompt, temperature=0.5, max_tokens=300)

        # Synthesize from tool results
        results_summary = "\n".join([
            f"- {tr['tool']}: {json.dumps(tr['result'])}"
            for tr in tool_results
        ])

        prompt = f"""You executed tools to complete this task.

Task: {instruction}

Tool Results:
{results_summary}

Based on these results, provide a concise summary of what was accomplished:"""

        return self.llm_client.generate(prompt, temperature=0.5, max_tokens=300)


def setup_environment():
    """Load environment variables."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="AI workflow agent")
    parser.add_argument(
        "--task-type",
        default="workflow",
        help="Type of task to execute"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="JSON task definition"
    )
    parser.add_argument(
        "--backend",
        default="ollama",
        choices=["ollama", "anthropic", "openai"],
        help="LLM backend to use"
    )
    parser.add_argument(
        "--model",
        help="Model name (optional)"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    setup_environment()
    args = parse_args()

    try:
        # Parse task input
        task_data = json.loads(args.input)

        # Create agent
        agent = WorkflowAgent(backend=args.backend, model=args.model)

        # Execute task
        result = agent.execute(task_data)

        # Output JSON to stdout for Node.js
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        # Output error as JSON
        error_result = {
            "success": False,
            "error": str(e),
            "type": type(e).__name__
        }
        print(json.dumps(error_result, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
