"""Dynamic tool registry for agent execution."""

import sys
import importlib
import inspect
from pathlib import Path
from typing import Dict, List, Any
from tools.base_tool import BaseTool


class ToolRegistry:
    """Manages tool discovery, registration, and execution."""

    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self._discover_tools()

    def _discover_tools(self):
        """Auto-discover all tools in the tools directory."""
        tools_dir = Path(__file__).parent / "tools"

        for file_path in tools_dir.glob("*.py"):
            if file_path.name.startswith("_") or file_path.name == "base_tool.py":
                continue

            module_name = file_path.stem

            try:
                module = importlib.import_module(f"tools.{module_name}")

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BaseTool) and
                        obj is not BaseTool and
                        not inspect.isabstract(obj)):

                        tool_instance = obj()
                        self.tools[tool_instance.name] = tool_instance
                        print(f"Registered tool: {tool_instance.name}", file=sys.stderr)

            except Exception as e:
                print(f"Failed to load tool from {module_name}: {e}", file=sys.stderr)

    def get_tool(self, name: str) -> BaseTool:
        """Get a tool by name."""
        tool = self.tools.get(name)
        if not tool:
            raise ValueError(f"Tool not found: {name}")
        return tool

    def get_tool_descriptions(self) -> List[Dict[str, Any]]:
        """Get function calling schemas for all tools."""
        return [tool.to_function_schema() for tool in self.tools.values()]

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool with validation.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters

        Returns:
            Tool execution result
        """
        tool = self.get_tool(tool_name)

        try:
            validated_params = tool.validate_inputs(parameters)
            result = tool.execute(**validated_params)
            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool": tool_name
            }

    def list_tools(self) -> List[str]:
        """List all available tool names."""
        return list(self.tools.keys())
