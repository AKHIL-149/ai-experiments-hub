#!/usr/bin/env python3
"""
Smart Email Responder - Generate contextual email responses.
"""

import argparse
import re
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

from llm_client import OllamaClient, GenerationError
from email_templates import build_prompt, list_templates, get_template

# Chatty framing models wrap around the email itself
_PREAMBLE_RE = re.compile(
    r"^\s*(here('s| is| are)|sure|certainly|of course|below (is|are))\b[^\n]*:\s*$",
    re.IGNORECASE,
)
_TRAILING_NOTE_RE = re.compile(
    r"^\s*(note\b|please note|i hope this helps|feel free to|let me know if you)",
    re.IGNORECASE,
)


def clean_response(text: str) -> str:
    """Strip "Here is your email:" lead-ins, code fences and trailing meta notes."""
    text = (text or "").strip()
    lines = text.split("\n")
    while lines and (not lines[0].strip() or _PREAMBLE_RE.match(lines[0]) or lines[0].strip().startswith("```")):
        lines.pop(0)
    while lines and (not lines[-1].strip() or lines[-1].strip() == "```"):
        lines.pop()
    text = "\n".join(lines).strip()

    paragraphs = re.split(r"\n\s*\n", text)
    while len(paragraphs) > 1 and _TRAILING_NOTE_RE.match(paragraphs[-1]):
        paragraphs.pop()
    return "\n\n".join(paragraphs).strip()


def setup_environment():
    """Load environment variables."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        root_env = Path(__file__).parent.parent.parent.parent / ".env"
        if root_env.exists():
            load_dotenv(root_env)


def decode_email_bytes(data: bytes) -> str:
    """Decode an email file: UTF-8 first, then Windows-1252 (common for Outlook exports)."""
    if b"\x00" in data:
        raise ValueError("this does not look like a text file")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def read_email_from_file(file_path: str) -> str:
    """Read email content from a file, or from stdin when the path is '-'."""
    try:
        if file_path == "-":
            return decode_email_bytes(sys.stdin.buffer.read())
        return decode_email_bytes(Path(file_path).read_bytes())
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
        help="Read email from a file ('-' for stdin) instead of the command line"
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
        "--max-tokens",
        type=int,
        default=1000,
        help="Maximum tokens to generate (default: 1000)"
    )

    parser.add_argument(
        "--name", "-n",
        default="",
        help="Your name, used to sign the reply instead of a [Your Name] placeholder"
    )

    parser.add_argument(
        "--output", "-o",
        help="Save response to file"
    )

    parser.add_argument(
        "--plain",
        action="store_true",
        help="Print only the reply, without decoration (automatic when piped)"
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

    # Validate numeric options
    if not 0.0 <= args.temperature <= 2.0:
        print("Error: temperature must be between 0.0 and 2.0", file=sys.stderr)
        sys.exit(1)
    if args.max_tokens < 1:
        print("Error: --max-tokens must be at least 1", file=sys.stderr)
        sys.exit(1)

    # Get email content
    if args.file:
        if args.email_body:
            print("Warning: both an email and --file were given; using the file", file=sys.stderr)
        email_body = read_email_from_file(args.file)
    elif args.email_body is not None:
        email_body = args.email_body
    else:
        print("Error: Provide email content or use --file", file=sys.stderr)
        sys.exit(1)

    if not email_body.strip():
        print("Error: the email to respond to is empty", file=sys.stderr)
        sys.exit(1)

    # Validate template
    try:
        template_info = get_template(args.template)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nUse --list-templates to see available options", file=sys.stderr)
        sys.exit(1)

    # Build prompt
    prompt = build_prompt(args.template, email_body, args.instructions, args.name)

    # Initialize client
    client = OllamaClient(model=args.model)

    print(f"Generating {template_info['description']}...", file=sys.stderr)
    print(f"Using model: {client.model}", file=sys.stderr)

    try:
        response = client.generate(
            prompt, temperature=args.temperature, max_tokens=args.max_tokens
        )

        if client.truncated:
            print(
                f"Warning: the reply was cut off at --max-tokens {args.max_tokens}; "
                "increase it for a complete reply.",
                file=sys.stderr
            )
        response = clean_response(response)
        if not response:
            hint = (
                " The model likely spent its whole token budget on hidden reasoning "
                "(thinking models do this); increase --max-tokens."
                if client.truncated else ""
            )
            print(f"Error: the model returned an empty response.{hint}", file=sys.stderr)
            sys.exit(1)

        # Output
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(response + "\n", encoding="utf-8")
            print(f"\nResponse saved to: {args.output}", file=sys.stderr)
        elif args.plain or not sys.stdout.isatty():
            print(response)
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
