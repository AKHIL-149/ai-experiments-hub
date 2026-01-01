#!/usr/bin/env python3
"""
AI Text Generator - CLI tool for generating various types of content.
"""

import argparse
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

from llm_client import LLMClient
from templates import apply_template, TEMPLATES


def setup_environment():
    """Load environment variables from .env file."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # Try loading from root .env
        root_env = Path(__file__).parent.parent.parent.parent / ".env"
        if root_env.exists():
            load_dotenv(root_env)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate text content using LLMs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Write a haiku about coding"
  %(prog)s --template email "Respond to client about project delay"
  %(prog)s --backend anthropic "Explain quantum computing simply"
  %(prog)s --model llama3.2 --temperature 0.9 "Write a creative story"
        """
    )

    parser.add_argument(
        "prompt",
        help="The prompt or topic for text generation"
    )

    parser.add_argument(
        "--backend",
        choices=["ollama", "anthropic", "openai"],
        default="ollama",
        help="LLM backend to use (default: ollama)"
    )

    parser.add_argument(
        "--model",
        help="Specific model to use (defaults vary by backend)"
    )

    parser.add_argument(
        "--template",
        choices=list(TEMPLATES.keys()),
        help="Use a predefined template for the prompt"
    )

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1000,
        help="Maximum tokens to generate (default: 1000)"
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Sampling temperature 0.0-2.0 (default: 0.7)"
    )

    parser.add_argument(
        "--output",
        "-o",
        help="Save output to file instead of printing to stdout"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    setup_environment()
    args = parse_args()

    # Validate temperature
    if not 0.0 <= args.temperature <= 2.0:
        print("Error: temperature must be between 0.0 and 2.0", file=sys.stderr)
        sys.exit(1)

    # Apply template if specified
    prompt = args.prompt
    if args.template:
        prompt = apply_template(args.template, args.prompt)

    try:
        # Initialize LLM client
        client = LLMClient(backend=args.backend, model=args.model)

        print(f"Generating with {client.backend} ({client.model})...", file=sys.stderr)

        # Generate text
        result = client.generate(
            prompt=prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature
        )

        # Output results
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(result)
            print(f"Output saved to {args.output}", file=sys.stderr)
        else:
            print("\n" + "=" * 70)
            print(result)
            print("=" * 70)

    except KeyboardInterrupt:
        print("\nGeneration cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
