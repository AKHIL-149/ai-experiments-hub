#!/usr/bin/env python3
"""Run a single registered tool directly (no LLM involved)."""

import sys
import json
import argparse

from tool_registry import ToolRegistry


def main():
    parser = argparse.ArgumentParser(description="Run one workflow tool")
    parser.add_argument("--tool", required=True, help="Tool name, e.g. file_operations")
    parser.add_argument("--params", required=True, help="JSON object of tool parameters")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
        if not isinstance(params, dict):
            raise ValueError("--params must be a JSON object")

        result = ToolRegistry().execute_tool(args.tool, params)
        success = not (isinstance(result, dict) and result.get("success") is False)
        output = {"success": success, "result": result}
        if not success:
            output["error"] = result.get("error", "Tool failed")
    except Exception as e:
        output = {"success": False, "error": str(e)}

    print(json.dumps(output))
    sys.exit(0 if output["success"] else 1)


if __name__ == "__main__":
    main()
