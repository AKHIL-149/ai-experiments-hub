#!/usr/bin/env python3
"""CLI for Content Analyzer - AI-powered image analysis tool."""
import sys
import argparse
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.core.vision_client import VisionClient
from src.core.image_processor import ImageProcessor
from src.core.prompt_templates import get_prompt, list_templates


def describe_image(args):
    """Describe an image using vision AI.

    Args:
        args: Parsed command-line arguments
    """
    try:
        # Initialize components
        print(f"Initializing vision client ({args.provider})...")
        vision_client = VisionClient(
            backend=args.provider,
            model=args.model
        )

        print(f"Loading image: {args.image}...")
        image_processor = ImageProcessor()
        image = image_processor.load_image(args.image)

        # Validate image
        validation = image_processor.validate_image(image)
        if not validation['valid']:
            print(f"❌ Image validation failed: {', '.join(validation['errors'])}")
            return 1

        # Get metadata
        metadata = image_processor.extract_metadata(image)
        print(f"📊 Image: {metadata['format']} | "
              f"{metadata['dimensions']} | "
              f"{metadata['size_mb']} MB")

        # Save the image for verification (optional)
        if args.save_image:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = Path(args.save_image) if args.save_image != True else Path(f"analyzed_image_{timestamp}.jpg")
            image.save(save_path)
            print(f"💾 Image saved to: {save_path}")

        # Get prompt (custom, template, or default)
        prompt = get_prompt(
            template_name=getattr(args, 'preset', None),
            custom_prompt=args.prompt
        )

        print(f"\n🔍 Analyzing image...")
        if hasattr(args, 'preset') and args.preset:
            print(f"Using preset: {args.preset}")
        print(f"Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"Prompt: {prompt}\n")

        response = vision_client.analyze(
            prompt=prompt,
            images=[image],
            max_tokens=args.max_tokens,
            temperature=args.temperature
        )

        # Display result
        print("✨ Analysis Result:")
        print("-" * 60)
        print(response)
        print("-" * 60)

        # Save to file if requested
        if args.output_file:
            output_path = Path(args.output_file)
            output_path.write_text(response)
            print(f"\n💾 Saved to: {output_path}")

        return 0

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Content Analyzer - AI-powered image analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Describe an image
  python analyze.py describe photo.jpg

  # Use preset for better accuracy (racing cars, vehicles)
  python analyze.py describe car.jpg --preset vehicle

  # Custom prompt
  python analyze.py describe photo.jpg --prompt "What colors are in this image?"

  # Save analyzed image for verification
  python analyze.py describe https://example.com/image.jpg --save-image

  # Adjust accuracy (lower temperature = more factual)
  python analyze.py describe image.jpg --temperature 0.3 --preset object
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Describe command
    describe_parser = subparsers.add_parser(
        'describe',
        help='Describe image content'
    )
    describe_parser.add_argument(
        'image',
        type=str,
        help='Path to image file or URL'
    )
    describe_parser.add_argument(
        '--prompt',
        type=str,
        default=None,
        help='Custom prompt (overrides --preset)'
    )
    describe_parser.add_argument(
        '--preset',
        choices=['vehicle', 'document', 'object', 'scene', 'person', 'technical', 'simple'],
        default=None,
        help='Use a preset prompt template for better accuracy'
    )
    describe_parser.add_argument(
        '--provider',
        choices=['ollama', 'anthropic', 'openai'],
        default='ollama',
        help='Vision provider (default: ollama)'
    )
    describe_parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Model name (defaults per provider)'
    )
    describe_parser.add_argument(
        '--max-tokens',
        type=int,
        default=1000,
        help='Maximum tokens in response (default: 1000)'
    )
    describe_parser.add_argument(
        '--temperature',
        type=float,
        default=0.7,
        help='Sampling temperature 0-2 (default: 0.7)'
    )
    describe_parser.add_argument(
        '--output-file',
        type=str,
        default=None,
        help='Save output to file'
    )
    describe_parser.add_argument(
        '--save-image',
        nargs='?',
        const=True,
        default=None,
        help='Save the analyzed image (auto-named or specify path)'
    )

    args = parser.parse_args()

    # Show help if no command provided
    if not args.command:
        parser.print_help()
        return 0

    # Route to appropriate command handler
    if args.command == 'describe':
        return describe_image(args)

    return 0


if __name__ == '__main__':
    sys.exit(main())
