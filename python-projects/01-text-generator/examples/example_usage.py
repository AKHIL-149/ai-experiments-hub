#!/usr/bin/env python3
"""
Example usage of the LLM client programmatically.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_client import LLMClient
from templates import apply_template


def example_basic_generation():
    """Basic text generation example."""
    print("=" * 70)
    print("Example 1: Basic Generation")
    print("=" * 70)

    client = LLMClient(backend="ollama", model="llama3.2")
    prompt = "Explain what a neural network is in simple terms."

    result = client.generate(prompt, max_tokens=300)
    print(result)
    print()


def example_with_template():
    """Using a template for structured output."""
    print("=" * 70)
    print("Example 2: Email Template")
    print("=" * 70)

    client = LLMClient(backend="ollama")

    user_request = "Thank client for feedback and mention the fix will be deployed tomorrow"
    prompt = apply_template("email", user_request)

    result = client.generate(prompt, max_tokens=500, temperature=0.7)
    print(result)
    print()


def example_creative_writing():
    """Higher temperature for creative content."""
    print("=" * 70)
    print("Example 3: Creative Story (High Temperature)")
    print("=" * 70)

    client = LLMClient(backend="ollama")

    prompt = apply_template("story", "A programmer discovers their code is sentient")

    result = client.generate(prompt, max_tokens=800, temperature=1.0)
    print(result)
    print()


def example_multiple_backends():
    """Compare outputs from different backends."""
    print("=" * 70)
    print("Example 4: Comparing Backends")
    print("=" * 70)

    prompt = "Write a haiku about debugging code"

    # Note: Only Ollama will work without API keys
    backends = ["ollama"]

    for backend in backends:
        try:
            client = LLMClient(backend=backend)
            print(f"\n{backend.upper()}:")
            print("-" * 40)
            result = client.generate(prompt, max_tokens=100)
            print(result)
        except Exception as e:
            print(f"Skipped {backend}: {e}")

    print()


if __name__ == "__main__":
    # Run examples
    # Uncomment the ones you want to try

    example_basic_generation()
    # example_with_template()
    # example_creative_writing()
    # example_multiple_backends()
