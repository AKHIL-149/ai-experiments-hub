"""Sample Python module for testing the parser.

This module contains various Python constructs to test the parser's
ability to extract functions, classes, type hints, and docstrings.
"""
from typing import List, Optional, Dict
import os
import sys


# Global variables
MAX_RETRIES: int = 3
DEFAULT_TIMEOUT = 30
config = {'debug': True, 'verbose': False}


def simple_function(name: str) -> str:
    """A simple function with type hints.

    Args:
        name: The name to greet

    Returns:
        A greeting message
    """
    return f"Hello, {name}!"


async def async_function(url: str, timeout: int = 30) -> Dict[str, str]:
    """An async function example."""
    return {"url": url, "status": "fetched"}


def complex_function(
    data: List[int],
    threshold: float = 0.5,
    *args,
    **kwargs
) -> Optional[List[int]]:
    """Function with multiple parameters including *args and **kwargs.

    Args:
        data: List of integers to process
        threshold: Minimum threshold value
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments

    Returns:
        Filtered list or None
    """
    result = []
    for item in data:
        if item > threshold:
            result.append(item)

    if kwargs.get('verbose'):
        print(f"Processed {len(data)} items")

    return result if result else None


@staticmethod
def decorated_function(value: int) -> int:
    """Function with decorator."""
    return value * 2


class SimpleClass:
    """A simple class for testing."""

    def __init__(self, name: str):
        """Initialize the class.

        Args:
            name: Instance name
        """
        self.name = name

    def greet(self) -> str:
        """Return a greeting."""
        return f"Hello from {self.name}"


class ComplexClass(SimpleClass):
    """A more complex class with inheritance.

    This class demonstrates inheritance, class variables,
    and various method types.
    """

    class_variable: int = 42
    _private_var = "secret"

    def __init__(self, name: str, age: int):
        """Initialize with name and age.

        Args:
            name: Person's name
            age: Person's age
        """
        super().__init__(name)
        self.age = age
        self._count = 0

    def instance_method(self, value: int) -> int:
        """Regular instance method.

        Args:
            value: Input value

        Returns:
            Processed value
        """
        self._count += 1
        return value + self.age

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> 'ComplexClass':
        """Create instance from dictionary.

        Args:
            data: Dictionary with name and age keys

        Returns:
            New ComplexClass instance
        """
        return cls(data['name'], data['age'])

    @staticmethod
    def utility_function(x: int, y: int) -> int:
        """Static utility function.

        Args:
            x: First number
            y: Second number

        Returns:
            Sum of x and y
        """
        return x + y

    async def async_method(self, url: str) -> str:
        """Async method example.

        Args:
            url: URL to fetch

        Returns:
            Response content
        """
        return f"Fetched from {url}"


class DataClass:
    """Class with type-annotated attributes."""

    name: str
    age: int
    email: Optional[str] = None
    tags: List[str] = []

    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age
