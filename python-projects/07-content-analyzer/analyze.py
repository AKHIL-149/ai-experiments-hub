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
from src.core.ocr_processor import OCRProcessor
from src.core.cache_manager import CacheManager
from src.core.image_comparator import ImageComparator
from src.core.batch_processor import BatchProcessor


def describe_image(args):
    """Describe an image using vision AI.

    Args:
        args: Parsed command-line arguments
    """
    try:
        # Initialize cache manager if enabled
        cache_manager = None
        if getattr(args, 'enable_cache', True):
            cache_manager = CacheManager()

        # Initialize components
        print(f"Initializing vision client ({args.provider})...")
        vision_client = VisionClient(
            backend=args.provider,
            model=args.model,
            cache_manager=cache_manager,
            enable_cache=getattr(args, 'enable_cache', True)
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


def ocr_text(args):
    """Extract text from image using OCR.

    Args:
        args: Parsed command-line arguments
    """
    try:
        # Initialize components
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

        # Initialize vision client for fallback (if requested)
        vision_client = None
        if args.fallback:
            print(f"Initializing vision client ({args.provider}) for fallback...")
            vision_client = VisionClient(
                backend=args.provider,
                model=args.model
            )

        # Initialize OCR processor
        print(f"\n🔍 Extracting text with OCR...")
        if args.method == 'tesseract':
            print("Method: Tesseract OCR")
        elif args.method == 'vision':
            print(f"Method: Vision model ({args.provider})")
            # Force vision-only mode
            if not vision_client:
                vision_client = VisionClient(
                    backend=args.provider,
                    model=args.model
                )
        else:  # auto
            print("Method: Auto (Tesseract with vision fallback)")

        ocr_processor = OCRProcessor(
            use_tesseract=(args.method != 'vision'),
            vision_client=vision_client
        )

        # Extract text
        result = ocr_processor.extract_text(
            image=image,
            language=args.language,
            fallback_to_vision=args.fallback,
            confidence_threshold=args.confidence
        )

        # Display results
        print("\n✨ OCR Results:")
        print("-" * 60)
        print(f"Method Used: {result['method']}")
        print(f"Confidence: {result['confidence']}%")
        print(f"Language: {result['language']}")
        print("-" * 60)
        print("\nExtracted Text:")
        print(result['text'])
        print("-" * 60)

        # Show additional details if verbose
        if args.verbose and result.get('details'):
            print("\nDetails:")
            for key, value in result['details'].items():
                if key != 'bounding_boxes':  # Skip boxes in simple display
                    print(f"  {key}: {value}")

        # Save to file if requested
        if args.output_file:
            output_path = Path(args.output_file)
            output_path.write_text(result['text'])
            print(f"\n💾 Text saved to: {output_path}")

        # Save structured output if requested
        if args.output_json:
            import json
            json_path = Path(args.output_json)
            json_path.write_text(json.dumps(result, indent=2))
            print(f"💾 Full results saved to: {json_path}")

        return 0

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def detect_language(args):
    """Detect language in image text.

    Args:
        args: Parsed command-line arguments
    """
    try:
        # Initialize components
        print(f"Loading image: {args.image}...")
        image_processor = ImageProcessor()
        image = image_processor.load_image(args.image)

        # Initialize vision client if needed
        vision_client = None
        if args.use_vision:
            print(f"Initializing vision client ({args.provider})...")
            vision_client = VisionClient(
                backend=args.provider,
                model=args.model
            )

        # Initialize OCR processor
        ocr_processor = OCRProcessor(
            use_tesseract=True,
            vision_client=vision_client
        )

        print("\n🔍 Detecting language...")
        result = ocr_processor.detect_language(image)

        # Display results
        print("\n✨ Language Detection Results:")
        print("-" * 60)
        print(f"Method: {result['method']}")

        if result.get('primary_language'):
            print(f"\nPrimary Language: {result['primary_language']}")

        if result.get('languages'):
            print("\nDetected Languages:")
            for lang in result['languages']:
                if 'code' in lang:
                    print(f"  • {lang['name']} ({lang['code']}): {lang['confidence']:.1f}% confidence")
                else:
                    print(f"  {lang.get('description', lang)}")

        if result.get('error'):
            print(f"\n⚠️  {result['error']}")

        print("-" * 60)

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cache_stats(args):
    """Show cache statistics.

    Args:
        args: Parsed command-line arguments
    """
    try:
        cache_manager = CacheManager()
        stats = cache_manager.get_stats()

        print("\n📊 Cache Statistics:")
        print("=" * 60)
        print(f"Hits: {stats['hits']}")
        print(f"Misses: {stats['misses']}")
        print(f"Total Requests: {stats['total_requests']}")
        print(f"Hit Rate: {stats['hit_rate_percent']}%")
        print(f"Cache Saves: {stats['cache_saves']}")
        print(f"Cache Size: {stats['cache_size_mb']} MB")

        print("\n💰 Cost Savings (Estimated):")
        print(f"Anthropic: ${stats['cost_savings']['anthropic']:.4f}")
        print(f"OpenAI: ${stats['cost_savings']['openai']:.4f}")
        print(f"Total: ${stats['cost_savings']['total']:.4f}")

        if stats['last_cleanup']:
            print(f"\nLast Cleanup: {stats['last_cleanup']}")

        print("=" * 60)

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cache_cleanup(args):
    """Clean up expired cache entries.

    Args:
        args: Parsed command-line arguments
    """
    try:
        cache_manager = CacheManager()

        keep_hours = getattr(args, 'keep_hours', None)

        print(f"\n🧹 Cleaning up cache...")
        if keep_hours:
            print(f"Keeping entries from last {keep_hours} hours")
        else:
            print("Removing expired entries")

        removed = cache_manager.cleanup(keep_recent_hours=keep_hours)

        print(f"✅ Removed {removed} cache entries")

        # Show updated stats
        stats = cache_manager.get_stats()
        print(f"Cache size now: {stats['cache_size_mb']} MB")

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cache_clear(args):
    """Clear all cache entries.

    Args:
        args: Parsed command-line arguments
    """
    try:
        cache_manager = CacheManager()

        print("\n🗑️  Clearing all cache...")
        cache_manager.clear()

        print("✅ Cache cleared successfully")

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def compare_images(args):
    """Compare two images.

    Args:
        args: Parsed command-line arguments
    """
    try:
        # Initialize components
        print(f"Loading images...")
        image_processor = ImageProcessor()
        image1 = image_processor.load_image(args.image1)
        image2 = image_processor.load_image(args.image2)

        # Initialize vision client if needed
        vision_client = None
        if args.use_ai:
            print(f"Initializing vision client ({args.provider}) for AI comparison...")
            vision_client = VisionClient(
                backend=args.provider,
                model=args.model
            )

        # Initialize comparator
        comparator = ImageComparator(vision_client=vision_client)

        print(f"\n🔍 Comparing images...")
        if args.use_ai:
            print(f"Mode: {args.mode} (with AI analysis)")
        else:
            print("Mode: Structural comparison only")

        result = comparator.compare_images(
            image1=image1,
            image2=image2,
            mode=args.mode,
            temperature=args.temperature,
            max_tokens=args.max_tokens
        )

        # Display results
        print("\n✨ Comparison Results:")
        print("=" * 60)

        # Structural comparison
        print("\n📊 Structural Analysis:")
        print(f"Image 1: {result['structural']['image1']['dimensions']} | "
              f"{result['structural']['image1']['format']} | "
              f"{result['structural']['image1']['mode']}")
        print(f"Image 2: {result['structural']['image2']['dimensions']} | "
              f"{result['structural']['image2']['format']} | "
              f"{result['structural']['image2']['mode']}")

        print(f"\nIdentical: {'✅ Yes' if result['identical'] else '❌ No'}")
        print(f"Same Dimensions: {'✅ Yes' if result['similar_dimensions'] else '❌ No'}")
        print(f"Same Aspect Ratio: {'✅ Yes' if result['structural']['same_aspect_ratio'] else '❌ No'}")

        if not result['identical']:
            dim_diff = result['structural']['dimension_diff']
            print(f"\nDimension Difference:")
            print(f"  Width: {dim_diff['width_diff']}px ({dim_diff['width_ratio']:.2f}x)")
            print(f"  Height: {dim_diff['height_diff']}px ({dim_diff['height_ratio']:.2f}x)")

        # AI comparison
        if result['ai_analysis'] and result['ai_analysis'].get('analysis'):
            print(f"\n🤖 AI Analysis ({result['ai_analysis']['provider']}):")
            print("-" * 60)
            print(result['ai_analysis']['analysis'])
            print("-" * 60)

            if result['ai_analysis'].get('extracted_similarity') is not None:
                print(f"\nAI Similarity Score: {result['ai_analysis']['extracted_similarity']}%")

        print(f"\n📈 Overall Similarity Score: {result['similarity_score']}%")
        print("=" * 60)

        # Save to file if requested
        if args.output_file:
            output_path = Path(args.output_file)
            import json
            with open(output_path, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"\n💾 Results saved to: {output_path}")

        return 0

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def batch_describe(args):
    """Batch describe multiple images.

    Args:
        args: Parsed command-line arguments
    """
    try:
        # Get image paths
        image_paths = []
        if args.images:
            # Individual images specified
            image_paths = args.images
        elif args.directory:
            # Directory specified
            from glob import glob
            pattern = args.pattern or "*.{jpg,jpeg,png,webp,gif,bmp}"
            search_path = Path(args.directory) / pattern
            image_paths = glob(str(search_path), recursive=args.recursive)

        if not image_paths:
            print("❌ No images found")
            return 1

        print(f"Found {len(image_paths)} images")

        # Initialize cache manager if enabled
        cache_manager = None
        if getattr(args, 'enable_cache', True):
            cache_manager = CacheManager()

        # Initialize vision client
        print(f"Initializing vision client ({args.provider})...")
        vision_client = VisionClient(
            backend=args.provider,
            model=args.model,
            cache_manager=cache_manager,
            enable_cache=getattr(args, 'enable_cache', True)
        )

        # Load images
        print("Loading images...")
        image_processor = ImageProcessor()
        images = []
        image_names = []

        for path in image_paths:
            try:
                img = image_processor.load_image(path)
                images.append(img)
                image_names.append(Path(path).name)
            except Exception as e:
                print(f"⚠️  Failed to load {path}: {e}")

        if not images:
            print("❌ No valid images loaded")
            return 1

        # Get prompt
        prompt = get_prompt(
            template_name=getattr(args, 'preset', None),
            custom_prompt=args.prompt
        )

        # Initialize batch processor
        batch_processor = BatchProcessor(
            vision_client=vision_client,
            max_workers=args.workers
        )

        # Progress callback
        def progress(completed, total, result):
            status = "✅" if result['success'] else "❌"
            print(f"{status} [{completed}/{total}] {result['name']}")

        print(f"\n🔍 Processing {len(images)} images...")
        print(f"Workers: {args.workers}")
        print(f"Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"Prompt: {prompt}")
        print()

        results = batch_processor.batch_analyze(
            images=images,
            image_names=image_names,
            prompt=prompt,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            progress_callback=progress
        )

        # Display summary
        print(f"\n✨ Batch Processing Complete:")
        print("=" * 60)
        print(f"Total Images: {results['total_images']}")
        print(f"Successful: {results['successful']}")
        print(f"Failed: {results['failed']}")
        print(f"Total Time: {results['elapsed_time']:.2f}s")
        print(f"Avg Time/Image: {results['avg_time_per_image']:.2f}s")
        print("=" * 60)

        # Export results
        if args.output_json:
            output_path = Path(args.output_json)
            batch_processor.export_to_json(results, output_path)
            print(f"\n💾 JSON results saved to: {output_path}")

        if args.output_csv:
            output_path = Path(args.output_csv)
            batch_processor.export_to_csv(results, output_path, result_type='vision')
            print(f"💾 CSV results saved to: {output_path}")

        if args.output_txt:
            output_path = Path(args.output_txt)
            batch_processor.export_to_txt(results, output_path, result_type='vision')
            print(f"💾 Text results saved to: {output_path}")

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def batch_ocr(args):
    """Batch OCR multiple images.

    Args:
        args: Parsed command-line arguments
    """
    try:
        # Get image paths
        image_paths = []
        if args.images:
            image_paths = args.images
        elif args.directory:
            from glob import glob
            pattern = args.pattern or "*.{jpg,jpeg,png,webp,gif,bmp}"
            search_path = Path(args.directory) / pattern
            image_paths = glob(str(search_path), recursive=args.recursive)

        if not image_paths:
            print("❌ No images found")
            return 1

        print(f"Found {len(image_paths)} images")

        # Initialize vision client for fallback if needed
        vision_client = None
        if args.fallback or args.method == 'vision':
            print(f"Initializing vision client ({args.provider})...")
            vision_client = VisionClient(
                backend=args.provider,
                model=args.model
            )

        # Initialize OCR processor
        ocr_processor = OCRProcessor(
            use_tesseract=(args.method != 'vision'),
            vision_client=vision_client
        )

        # Load images
        print("Loading images...")
        image_processor = ImageProcessor()
        images = []
        image_names = []

        for path in image_paths:
            try:
                img = image_processor.load_image(path)
                images.append(img)
                image_names.append(Path(path).name)
            except Exception as e:
                print(f"⚠️  Failed to load {path}: {e}")

        if not images:
            print("❌ No valid images loaded")
            return 1

        # Initialize batch processor
        batch_processor = BatchProcessor(
            ocr_processor=ocr_processor,
            max_workers=args.workers
        )

        # Progress callback
        def progress(completed, total, result):
            status = "✅" if result['success'] else "❌"
            print(f"{status} [{completed}/{total}] {result['name']}")

        print(f"\n🔍 Processing {len(images)} images...")
        print(f"Workers: {args.workers}")
        print(f"Method: {args.method}")
        print()

        results = batch_processor.batch_ocr(
            images=images,
            image_names=image_names,
            language=args.language,
            method=args.method,
            fallback_to_vision=args.fallback,
            confidence_threshold=args.confidence,
            progress_callback=progress
        )

        # Display summary
        print(f"\n✨ Batch OCR Complete:")
        print("=" * 60)
        print(f"Total Images: {results['total_images']}")
        print(f"Successful: {results['successful']}")
        print(f"Failed: {results['failed']}")
        print(f"Total Time: {results['elapsed_time']:.2f}s")
        print(f"Avg Time/Image: {results['avg_time_per_image']:.2f}s")
        print("=" * 60)

        # Export results
        if args.output_json:
            output_path = Path(args.output_json)
            batch_processor.export_to_json(results, output_path)
            print(f"\n💾 JSON results saved to: {output_path}")

        if args.output_csv:
            output_path = Path(args.output_csv)
            batch_processor.export_to_csv(results, output_path, result_type='ocr')
            print(f"💾 CSV results saved to: {output_path}")

        if args.output_txt:
            output_path = Path(args.output_txt)
            batch_processor.export_to_txt(results, output_path, result_type='ocr')
            print(f"💾 Text results saved to: {output_path}")

        return 0

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

  # Extract text with OCR (Tesseract)
  python analyze.py ocr document.jpg

  # OCR with vision model fallback for better accuracy
  python analyze.py ocr receipt.jpg --fallback --provider anthropic

  # OCR using only vision model (no Tesseract)
  python analyze.py ocr form.png --method vision --provider anthropic

  # Detect language in image text
  python analyze.py detect-language document.jpg

  # Compare two images (structural only)
  python analyze.py compare image1.jpg image2.jpg

  # Compare with AI analysis
  python analyze.py compare before.jpg after.jpg --use-ai --mode detailed

  # Batch describe multiple images
  python analyze.py batch-describe --directory ./photos --preset object --workers 8

  # Batch OCR documents
  python analyze.py batch-ocr --images doc1.jpg doc2.jpg doc3.jpg --output-csv results.csv
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

    # OCR command
    ocr_parser = subparsers.add_parser(
        'ocr',
        help='Extract text from image using OCR'
    )
    ocr_parser.add_argument(
        'image',
        type=str,
        help='Path to image file or URL'
    )
    ocr_parser.add_argument(
        '--method',
        choices=['auto', 'tesseract', 'vision'],
        default='auto',
        help='OCR method (default: auto - Tesseract with vision fallback)'
    )
    ocr_parser.add_argument(
        '--language',
        type=str,
        default='eng',
        help='Language code for OCR (default: eng)'
    )
    ocr_parser.add_argument(
        '--provider',
        choices=['ollama', 'anthropic', 'openai'],
        default='anthropic',
        help='Vision provider for fallback (default: anthropic)'
    )
    ocr_parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Model name (defaults per provider)'
    )
    ocr_parser.add_argument(
        '--fallback',
        action='store_true',
        help='Enable vision model fallback if Tesseract has low confidence'
    )
    ocr_parser.add_argument(
        '--confidence',
        type=float,
        default=60.0,
        help='Minimum confidence threshold for Tesseract (default: 60.0)'
    )
    ocr_parser.add_argument(
        '--output-file',
        type=str,
        default=None,
        help='Save extracted text to file'
    )
    ocr_parser.add_argument(
        '--output-json',
        type=str,
        default=None,
        help='Save full OCR results as JSON'
    )
    ocr_parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed OCR information'
    )

    # Language detection command
    lang_parser = subparsers.add_parser(
        'detect-language',
        help='Detect language in image text'
    )
    lang_parser.add_argument(
        'image',
        type=str,
        help='Path to image file or URL'
    )
    lang_parser.add_argument(
        '--use-vision',
        action='store_true',
        help='Use vision model for language detection'
    )
    lang_parser.add_argument(
        '--provider',
        choices=['ollama', 'anthropic', 'openai'],
        default='anthropic',
        help='Vision provider (default: anthropic)'
    )
    lang_parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Model name (defaults per provider)'
    )

    # Cache stats command
    cache_stats_parser = subparsers.add_parser(
        'cache-stats',
        help='Show cache statistics'
    )

    # Cache cleanup command
    cache_cleanup_parser = subparsers.add_parser(
        'cache-cleanup',
        help='Clean up expired cache entries'
    )
    cache_cleanup_parser.add_argument(
        '--keep-hours',
        type=int,
        default=None,
        help='Keep entries from last N hours (default: remove expired only)'
    )

    # Cache clear command
    cache_clear_parser = subparsers.add_parser(
        'cache-clear',
        help='Clear all cache entries'
    )

    # Compare command
    compare_parser = subparsers.add_parser(
        'compare',
        help='Compare two images'
    )
    compare_parser.add_argument(
        'image1',
        type=str,
        help='Path to first image'
    )
    compare_parser.add_argument(
        'image2',
        type=str,
        help='Path to second image'
    )
    compare_parser.add_argument(
        '--use-ai',
        action='store_true',
        help='Use AI for semantic comparison'
    )
    compare_parser.add_argument(
        '--mode',
        choices=['content', 'visual', 'detailed'],
        default='content',
        help='Comparison mode (default: content)'
    )
    compare_parser.add_argument(
        '--provider',
        choices=['ollama', 'anthropic', 'openai'],
        default='anthropic',
        help='Vision provider for AI comparison (default: anthropic)'
    )
    compare_parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Model name (defaults per provider)'
    )
    compare_parser.add_argument(
        '--temperature',
        type=float,
        default=0.3,
        help='Sampling temperature (default: 0.3 for factual comparison)'
    )
    compare_parser.add_argument(
        '--max-tokens',
        type=int,
        default=1000,
        help='Maximum tokens in response (default: 1000)'
    )
    compare_parser.add_argument(
        '--output-file',
        type=str,
        default=None,
        help='Save comparison results to JSON file'
    )

    # Batch describe command
    batch_describe_parser = subparsers.add_parser(
        'batch-describe',
        help='Batch describe multiple images'
    )
    batch_group = batch_describe_parser.add_mutually_exclusive_group(required=True)
    batch_group.add_argument(
        '--images',
        nargs='+',
        help='List of image paths'
    )
    batch_group.add_argument(
        '--directory',
        type=str,
        help='Directory containing images'
    )
    batch_describe_parser.add_argument(
        '--pattern',
        type=str,
        default=None,
        help='Glob pattern for image files (default: *.{jpg,jpeg,png,webp,gif,bmp})'
    )
    batch_describe_parser.add_argument(
        '--recursive',
        action='store_true',
        help='Search directory recursively'
    )
    batch_describe_parser.add_argument(
        '--prompt',
        type=str,
        default=None,
        help='Custom prompt for all images'
    )
    batch_describe_parser.add_argument(
        '--preset',
        choices=['vehicle', 'document', 'object', 'scene', 'person', 'technical', 'simple'],
        default=None,
        help='Use a preset prompt template'
    )
    batch_describe_parser.add_argument(
        '--provider',
        choices=['ollama', 'anthropic', 'openai'],
        default='anthropic',
        help='Vision provider (default: anthropic)'
    )
    batch_describe_parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Model name (defaults per provider)'
    )
    batch_describe_parser.add_argument(
        '--temperature',
        type=float,
        default=0.7,
        help='Sampling temperature (default: 0.7)'
    )
    batch_describe_parser.add_argument(
        '--max-tokens',
        type=int,
        default=1000,
        help='Maximum tokens per response (default: 1000)'
    )
    batch_describe_parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of concurrent workers (default: 4)'
    )
    batch_describe_parser.add_argument(
        '--output-json',
        type=str,
        default=None,
        help='Save results to JSON file'
    )
    batch_describe_parser.add_argument(
        '--output-csv',
        type=str,
        default=None,
        help='Save results to CSV file'
    )
    batch_describe_parser.add_argument(
        '--output-txt',
        type=str,
        default=None,
        help='Save results to text file'
    )
    batch_describe_parser.add_argument(
        '--no-cache',
        dest='enable_cache',
        action='store_false',
        default=True,
        help='Disable response caching'
    )

    # Batch OCR command
    batch_ocr_parser = subparsers.add_parser(
        'batch-ocr',
        help='Batch OCR multiple images'
    )
    batch_ocr_group = batch_ocr_parser.add_mutually_exclusive_group(required=True)
    batch_ocr_group.add_argument(
        '--images',
        nargs='+',
        help='List of image paths'
    )
    batch_ocr_group.add_argument(
        '--directory',
        type=str,
        help='Directory containing images'
    )
    batch_ocr_parser.add_argument(
        '--pattern',
        type=str,
        default=None,
        help='Glob pattern for image files (default: *.{jpg,jpeg,png,webp,gif,bmp})'
    )
    batch_ocr_parser.add_argument(
        '--recursive',
        action='store_true',
        help='Search directory recursively'
    )
    batch_ocr_parser.add_argument(
        '--method',
        choices=['auto', 'tesseract', 'vision'],
        default='auto',
        help='OCR method (default: auto)'
    )
    batch_ocr_parser.add_argument(
        '--language',
        type=str,
        default='eng',
        help='Language code for OCR (default: eng)'
    )
    batch_ocr_parser.add_argument(
        '--provider',
        choices=['ollama', 'anthropic', 'openai'],
        default='anthropic',
        help='Vision provider for fallback (default: anthropic)'
    )
    batch_ocr_parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Model name (defaults per provider)'
    )
    batch_ocr_parser.add_argument(
        '--fallback',
        action='store_true',
        help='Enable vision model fallback for low confidence'
    )
    batch_ocr_parser.add_argument(
        '--confidence',
        type=float,
        default=60.0,
        help='Minimum confidence threshold (default: 60.0)'
    )
    batch_ocr_parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of concurrent workers (default: 4)'
    )
    batch_ocr_parser.add_argument(
        '--output-json',
        type=str,
        default=None,
        help='Save results to JSON file'
    )
    batch_ocr_parser.add_argument(
        '--output-csv',
        type=str,
        default=None,
        help='Save results to CSV file'
    )
    batch_ocr_parser.add_argument(
        '--output-txt',
        type=str,
        default=None,
        help='Save results to text file'
    )

    # Add cache flag to describe command
    describe_parser.add_argument(
        '--no-cache',
        dest='enable_cache',
        action='store_false',
        default=True,
        help='Disable response caching'
    )

    args = parser.parse_args()

    # Show help if no command provided
    if not args.command:
        parser.print_help()
        return 0

    # Route to appropriate command handler
    if args.command == 'describe':
        return describe_image(args)
    elif args.command == 'ocr':
        return ocr_text(args)
    elif args.command == 'detect-language':
        return detect_language(args)
    elif args.command == 'cache-stats':
        return cache_stats(args)
    elif args.command == 'cache-cleanup':
        return cache_cleanup(args)
    elif args.command == 'cache-clear':
        return cache_clear(args)
    elif args.command == 'compare':
        return compare_images(args)
    elif args.command == 'batch-describe':
        return batch_describe(args)
    elif args.command == 'batch-ocr':
        return batch_ocr(args)

    return 0


if __name__ == '__main__':
    sys.exit(main())
