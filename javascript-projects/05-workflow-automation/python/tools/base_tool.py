"""Base class for all agent tools."""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    """Abstract base class that all tools must inherit from."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for the LLM to understand the tool's purpose."""
        pass

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Return JSON Schema defining the tool's parameters.

        Example:
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri"},
                "selector": {"type": "string"}
            },
            "required": ["url"]
        }
        """
        pass

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the tool with the provided parameters.

        Args:
            **kwargs: Tool parameters matching the schema

        Returns:
            Dictionary with execution results
        """
        pass

    def validate_inputs(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate input parameters against the schema.

        Basic validation - can be overridden for complex validation.
        """
        schema = self.get_parameters_schema()
        required = schema.get("required", [])

        for field in required:
            if field not in parameters:
                raise ValueError(f"Missing required parameter: {field}")

        return parameters

    def to_function_schema(self) -> Dict[str, Any]:
        """
        Convert to LLM function calling format.

        Returns format compatible with Anthropic/OpenAI function calling.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameters_schema()
        }
