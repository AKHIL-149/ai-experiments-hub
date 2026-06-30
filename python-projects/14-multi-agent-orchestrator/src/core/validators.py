"""
Input validation utilities
"""

import re
from typing import Any, List, Dict, Optional
from enum import Enum

from src.core.exceptions import InvalidInputError
from src.models import TaskStatus, AgentRole, AgentStatus


class Validators:
    """
    Input validation utilities
    """

    @staticmethod
    def validate_required(value: Any, field_name: str) -> Any:
        """
        Validate that a required field is not None or empty

        Args:
            value: Value to validate
            field_name: Field name for error message

        Returns:
            Any: The validated value

        Raises:
            InvalidInputError: If value is None or empty
        """
        if value is None:
            raise InvalidInputError(field_name, "Field is required")

        if isinstance(value, str) and not value.strip():
            raise InvalidInputError(field_name, "Field cannot be empty")

        return value

    @staticmethod
    def validate_string(
        value: str,
        field_name: str,
        min_length: int = None,
        max_length: int = None,
        pattern: str = None
    ) -> str:
        """
        Validate string input

        Args:
            value: String to validate
            field_name: Field name for error message
            min_length: Minimum length
            max_length: Maximum length
            pattern: Regex pattern to match

        Returns:
            str: The validated string

        Raises:
            InvalidInputError: If validation fails
        """
        if not isinstance(value, str):
            raise InvalidInputError(field_name, f"Must be a string, got {type(value).__name__}")

        value = value.strip()

        if min_length and len(value) < min_length:
            raise InvalidInputError(field_name, f"Must be at least {min_length} characters long")

        if max_length and len(value) > max_length:
            raise InvalidInputError(field_name, f"Must be at most {max_length} characters long")

        if pattern and not re.match(pattern, value):
            raise InvalidInputError(field_name, f"Must match pattern: {pattern}")

        return value

    @staticmethod
    def validate_integer(
        value: int,
        field_name: str,
        min_value: int = None,
        max_value: int = None
    ) -> int:
        """
        Validate integer input

        Args:
            value: Integer to validate
            field_name: Field name for error message
            min_value: Minimum value
            max_value: Maximum value

        Returns:
            int: The validated integer

        Raises:
            InvalidInputError: If validation fails
        """
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvalidInputError(field_name, f"Must be an integer, got {type(value).__name__}")

        if min_value is not None and value < min_value:
            raise InvalidInputError(field_name, f"Must be at least {min_value}")

        if max_value is not None and value > max_value:
            raise InvalidInputError(field_name, f"Must be at most {max_value}")

        return value

    @staticmethod
    def validate_float(
        value: float,
        field_name: str,
        min_value: float = None,
        max_value: float = None
    ) -> float:
        """
        Validate float input

        Args:
            value: Float to validate
            field_name: Field name for error message
            min_value: Minimum value
            max_value: Maximum value

        Returns:
            float: The validated float

        Raises:
            InvalidInputError: If validation fails
        """
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise InvalidInputError(field_name, f"Must be a number, got {type(value).__name__}")

        value = float(value)

        if min_value is not None and value < min_value:
            raise InvalidInputError(field_name, f"Must be at least {min_value}")

        if max_value is not None and value > max_value:
            raise InvalidInputError(field_name, f"Must be at most {max_value}")

        return value

    @staticmethod
    def validate_enum(value: str, enum_class: type, field_name: str) -> Enum:
        """
        Validate enum value

        Args:
            value: Enum value as string
            enum_class: Enum class
            field_name: Field name for error message

        Returns:
            Enum: The validated enum value

        Raises:
            InvalidInputError: If validation fails
        """
        try:
            return enum_class(value)
        except (ValueError, KeyError):
            valid_values = [e.value for e in enum_class]
            raise InvalidInputError(
                field_name,
                f"Must be one of: {', '.join(valid_values)}"
            )

    @staticmethod
    def validate_list(
        value: List[Any],
        field_name: str,
        min_length: int = None,
        max_length: int = None,
        item_validator: callable = None
    ) -> List[Any]:
        """
        Validate list input

        Args:
            value: List to validate
            field_name: Field name for error message
            min_length: Minimum length
            max_length: Maximum length
            item_validator: Function to validate each item

        Returns:
            List[Any]: The validated list

        Raises:
            InvalidInputError: If validation fails
        """
        if not isinstance(value, list):
            raise InvalidInputError(field_name, f"Must be a list, got {type(value).__name__}")

        if min_length is not None and len(value) < min_length:
            raise InvalidInputError(field_name, f"Must have at least {min_length} items")

        if max_length is not None and len(value) > max_length:
            raise InvalidInputError(field_name, f"Must have at most {max_length} items")

        if item_validator:
            for i, item in enumerate(value):
                try:
                    item_validator(item, f"{field_name}[{i}]")
                except InvalidInputError:
                    raise

        return value

    @staticmethod
    def validate_dict(
        value: Dict[str, Any],
        field_name: str,
        required_keys: List[str] = None
    ) -> Dict[str, Any]:
        """
        Validate dictionary input

        Args:
            value: Dictionary to validate
            field_name: Field name for error message
            required_keys: List of required keys

        Returns:
            Dict[str, Any]: The validated dictionary

        Raises:
            InvalidInputError: If validation fails
        """
        if not isinstance(value, dict):
            raise InvalidInputError(field_name, f"Must be a dictionary, got {type(value).__name__}")

        if required_keys:
            missing_keys = [key for key in required_keys if key not in value]
            if missing_keys:
                raise InvalidInputError(
                    field_name,
                    f"Missing required keys: {', '.join(missing_keys)}"
                )

        return value

    @staticmethod
    def validate_task_status(status: str) -> TaskStatus:
        """
        Validate task status

        Args:
            status: Status string

        Returns:
            TaskStatus: Validated status enum

        Raises:
            InvalidInputError: If status is invalid
        """
        return Validators.validate_enum(status, TaskStatus, "status")

    @staticmethod
    def validate_agent_role(role: str) -> AgentRole:
        """
        Validate agent role

        Args:
            role: Role string

        Returns:
            AgentRole: Validated role enum

        Raises:
            InvalidInputError: If role is invalid
        """
        return Validators.validate_enum(role, AgentRole, "role")

    @staticmethod
    def validate_agent_status(status: str) -> AgentStatus:
        """
        Validate agent status

        Args:
            status: Status string

        Returns:
            AgentStatus: Validated status enum

        Raises:
            InvalidInputError: If status is invalid
        """
        return Validators.validate_enum(status, AgentStatus, "status")

    @staticmethod
    def validate_priority(priority: int) -> int:
        """
        Validate task priority (1-10)

        Args:
            priority: Priority value

        Returns:
            int: Validated priority

        Raises:
            InvalidInputError: If priority is invalid
        """
        return Validators.validate_integer(priority, "priority", min_value=1, max_value=10)

    @staticmethod
    def validate_temperature(temperature: float) -> float:
        """
        Validate LLM temperature (0.0-2.0)

        Args:
            temperature: Temperature value

        Returns:
            float: Validated temperature

        Raises:
            InvalidInputError: If temperature is invalid
        """
        return Validators.validate_float(temperature, "temperature", min_value=0.0, max_value=2.0)

    @staticmethod
    def validate_max_tokens(max_tokens: int) -> int:
        """
        Validate max tokens (1-100000)

        Args:
            max_tokens: Max tokens value

        Returns:
            int: Validated max tokens

        Raises:
            InvalidInputError: If max tokens is invalid
        """
        return Validators.validate_integer(max_tokens, "max_tokens", min_value=1, max_value=100000)


# Singleton instance
validators = Validators()
