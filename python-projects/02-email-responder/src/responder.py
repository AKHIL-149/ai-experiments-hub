#!/usr/bin/env python3
"""
Smart Email Responder - Generate contextual email responses.
"""

import argparse
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

from llm_client import OllamaClient
from email_templates import build_prompt, list_templates, get_template


def setup_environment():
    """Load environment variables."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        root_env = Path(__file__).parent.parent.parent.parent / ".env"
        if root_env.exists():
            load_dotenv(root_env)


def read_email_from_file(file_path: str) -> str:
    """Read email content from a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate smart email responses using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate response from email text
  %(prog)s --template professional "Can we meet next Tuesday?"

  # Read email from file
  %(prog)s --template thank_you --file incoming_email.txt

  # Custom instructions
  %(prog)s --template decline --instructions "Suggest alternative date" "Meeting invite"

  # List available templates
  %(prog)s --list-templates
        """
    )

    parser.add_argument(
        "email_body",
        nargs="?",
        help="Email content to respond to (or use --file)"
    )

    parser.add_argument(
        "--template", "-t",
        default="professional",
        help="Response template to use (default: professional)"
    )

    parser.add_argument(
        "--file", "-f",
        help="Read email from file instead of command line"
    )

    parser.add_argument(
        "--instructions", "-i",
        default="",
        help="Custom instructions for the response"
    )

    parser.add_argument(
        "--model", "-m",
        help="Ollama model to use (default: from .env or llama3.2)"
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Temperature for generation (default: 0.7)"
    )

    parser.add_argument(
        "--output", "-o",
        help="Save response to file"
    )

    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="List all available templates"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    setup_environment()
    args = parse_args()

    if args.list_templates:
        print("\nAvailable Email Templates:")
        print("=" * 60)
        for template in list_templates():
            print(f"\n{template['name']:20} - {template['description']}")
        print("\n" + "=" * 60)
        sys.exit(0)

    # Get email content
    if args.file:
        email_body = read_email_from_file(args.file)
    elif args.email_body:
        email_body = args.email_body
    else:
        print("Error: Provide email content or use --file", file=sys.stderr)
        sys.exit(1)

    # Validate template
    try:
        template_info = get_template(args.template)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nUse --list-templates to see available options", file=sys.stderr)
        sys.exit(1)

    # Build prompt
    prompt = build_prompt(args.template, email_body, args.instructions)

    # Initialize client
    client = OllamaClient(model=args.model)

    print(f"Generating {template_info['description']}...", file=sys.stderr)
    print(f"Using model: {client.model}", file=sys.stderr)

    try:
        response = client.generate(prompt, temperature=args.temperature)

        # Output
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(response)
            print(f"\nResponse saved to: {args.output}", file=sys.stderr)
        else:
            print("\n" + "=" * 70)
            print(response)
            print("=" * 70)

    except KeyboardInterrupt:
        print("\nGeneration cancelled", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
