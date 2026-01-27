#!/usr/bin/env python3
"""
Meeting Summarizer CLI - Phase 1: Core Foundation

Transcribe meeting audio files with intelligent caching.

Usage:
    python summarize.py transcribe meeting.mp3
    python summarize.py transcribe --chunked long_meeting.mp3
    python summarize.py cache-stats
"""

import argparse
import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import logging
from colorama import Fore, Style, init as colorama_init

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.audio_processor import AudioProcessor
from core.transcription_service import TranscriptionService
from core.cache_manager import CacheManager
from core.llm_client import LLMClient
from core.meeting_analyzer import MeetingAnalyzer

# Initialize colorama
colorama_init(autoreset=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from .env file"""
    load_dotenv()

    config = {
        # Transcription
        'transcription_backend': os.getenv('TRANSCRIPTION_BACKEND', 'openai'),
        'openai_api_key': os.getenv('OPENAI_API_KEY'),
        'whisper_model': os.getenv('WHISPER_MODEL', 'whisper-1'),
        'whisper_cpp_path': os.getenv('WHISPER_CPP_PATH'),
        'whisper_model_path': os.getenv('WHISPER_CPP_MODEL'),

        # Audio Processing
        'max_audio_size_mb': int(os.getenv('MAX_AUDIO_SIZE_MB', 500)),
        'chunk_duration_minutes': int(os.getenv('CHUNK_DURATION_MINUTES', 10)),
        'overlap_seconds': int(os.getenv('OVERLAP_SECONDS', 5)),

        # Caching
        'cache_dir': os.getenv('CACHE_DIR', './data/cache'),
        'transcription_ttl_days': int(os.getenv('TRANSCRIPTION_CACHE_TTL_DAYS', 30)),
        'summary_ttl_days': int(os.getenv('SUMMARY_CACHE_TTL_DAYS', 7)),
        'enable_cache': os.getenv('ENABLE_CACHE', 'true').lower() == 'true',

        # Output
        'output_dir': os.getenv('OUTPUT_DIR', './data/output'),
        'default_output_format': os.getenv('DEFAULT_OUTPUT_FORMAT', 'markdown')
    }

    return config


def print_banner():
    """Print CLI banner"""
    print(f"\n{Fore.CYAN}╔════════════════════════════════════════╗")
    print(f"{Fore.CYAN}║   Meeting Summarizer - Phase 1        ║")
    print(f"{Fore.CYAN}║   Audio Transcription with Caching    ║")
    print(f"{Fore.CYAN}╚════════════════════════════════════════╝{Style.RESET_ALL}\n")


def print_success(message):
    """Print success message"""
    print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")


def print_error(message):
    """Print error message"""
    print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")


def print_info(message):
    """Print info message"""
    print(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")


def print_warning(message):
    """Print warning message"""
    print(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")


def cmd_transcribe(args, config):
    """Transcribe audio file"""
    print_banner()

    audio_path = args.audio_file

    if not Path(audio_path).exists():
        print_error(f"Audio file not found: {audio_path}")
        return 1

    try:
        # Initialize components
        print_info("Initializing services...")

        audio_processor = AudioProcessor(max_size_mb=config['max_audio_size_mb'])

        cache_manager = None
        if config['enable_cache']:
            cache_manager = CacheManager(
                cache_dir=config['cache_dir'],
                transcription_ttl_days=config['transcription_ttl_days'],
                summary_ttl_days=config['summary_ttl_days']
            )

        transcription_service = TranscriptionService(
            backend=config['transcription_backend'],
            api_key=config['openai_api_key'],
            model=config['whisper_model'],
            cache_manager=cache_manager,
            audio_processor=audio_processor,
            whisper_cpp_path=config['whisper_cpp_path'],
            whisper_model_path=config['whisper_model_path']
        )

        # Validate audio file
        print_info(f"Validating audio file: {audio_path}")
        validation = audio_processor.validate_audio(audio_path)

        if not validation['valid']:
            print_error("Audio validation failed:")
            for error in validation['errors']:
                print(f"  - {error}")
            return 1

        if validation['warnings']:
            for warning in validation['warnings']:
                print_warning(warning)

        # Show file info
        metadata = audio_processor.get_metadata(audio_path)
        print_info(f"Duration: {metadata['duration_seconds']:.1f}s ({metadata['duration_seconds']/60:.1f} min)")
        print_info(f"Format: {metadata['format']}")
        print_info(f"Size: {metadata['file_size_mb']:.2f} MB")

        # Estimate cost
        if config['transcription_backend'] == 'openai':
            cost_estimate = transcription_service.estimate_cost(audio_path)
            print_info(f"Estimated cost: ${cost_estimate['estimated_cost_usd']:.4f}")

        # Transcribe
        print_info("Starting transcription...")

        if args.chunked or metadata['duration_seconds'] > 600:  # >10 minutes
            if metadata['duration_seconds'] > 600 and not args.chunked:
                print_warning("Audio is longer than 10 minutes, using chunked transcription")

            result = transcription_service.transcribe_chunked(
                audio_path,
                chunk_duration_minutes=config['chunk_duration_minutes'],
                overlap_seconds=config['overlap_seconds'],
                language=args.language
            )

            if 'chunks_processed' in result:
                print_info(f"Processed {result['chunks_processed']} chunks")
        else:
            result = transcription_service.transcribe(
                audio_path,
                language=args.language
            )

        # Display results
        print()
        print(f"{Fore.CYAN}{'='*60}")
        print(f"Transcription Result")
        print(f"{'='*60}{Style.RESET_ALL}")
        print()

        if result.get('cached'):
            print_success("Used cached transcription")

        print(f"{Fore.YELLOW}Language:{Style.RESET_ALL} {result['language']}")
        print(f"{Fore.YELLOW}Backend:{Style.RESET_ALL} {result['backend']}")
        print(f"{Fore.YELLOW}Duration:{Style.RESET_ALL} {result['duration']:.1f}s")
        print()
        print(f"{Fore.YELLOW}Transcript:{Style.RESET_ALL}")
        print(result['text'])
        print()

        # Save output
        output_dir = Path(config['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{Path(audio_path).stem}_transcript.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Transcript: {Path(audio_path).name}\n")
            f.write(f"Duration: {result['duration']:.1f}s\n")
            f.write(f"Language: {result['language']}\n")
            f.write(f"Backend: {result['backend']}\n")
            f.write(f"\n{'='*60}\n\n")
            f.write(result['text'])

        print_success(f"Transcript saved to: {output_file}")

        # Save JSON if requested
        if args.json:
            json_file = output_dir / f"{Path(audio_path).stem}_transcript.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print_success(f"JSON saved to: {json_file}")

        return 0

    except Exception as e:
        print_error(f"Transcription failed: {str(e)}")
        logger.exception("Transcription error")
        return 1


def cmd_cache_stats(args, config):
    """Display cache statistics"""
    print_banner()

    if not config['enable_cache']:
        print_warning("Caching is disabled in configuration")
        return 0

    try:
        cache_manager = CacheManager(
            cache_dir=config['cache_dir'],
            transcription_ttl_days=config['transcription_ttl_days'],
            summary_ttl_days=config['summary_ttl_days']
        )

        stats = cache_manager.get_stats()

        print(f"{Fore.CYAN}{'='*60}")
        print(f"Cache Statistics")
        print(f"{'='*60}{Style.RESET_ALL}\n")

        # Transcription cache
        trans_stats = stats['transcription']
        print(f"{Fore.YELLOW}Transcription Cache:{Style.RESET_ALL}")
        print(f"  Hits: {trans_stats['hits']}")
        print(f"  Misses: {trans_stats['misses']}")
        print(f"  Hit Rate: {trans_stats['hit_rate_percent']:.2f}%")
        print(f"  Total Requests: {trans_stats['total_requests']}")
        print()

        # Summary cache
        sum_stats = stats['summary']
        print(f"{Fore.YELLOW}Summary Cache:{Style.RESET_ALL}")
        print(f"  Hits: {sum_stats['hits']}")
        print(f"  Misses: {sum_stats['misses']}")
        print(f"  Hit Rate: {sum_stats['hit_rate_percent']:.2f}%")
        print(f"  Total Requests: {sum_stats['total_requests']}")
        print()

        # Cost savings
        print(f"{Fore.GREEN}Estimated Cost Saved: ${stats['estimated_cost_saved_usd']:.2f}{Style.RESET_ALL}")
        print()

        # Cache sizes
        print(f"{Fore.YELLOW}Cache Directory:{Style.RESET_ALL} {stats['cache_dir']}")
        print(f"  Transcriptions: {stats['cache_sizes']['transcriptions']['num_files']} files, "
              f"{stats['cache_sizes']['transcriptions']['total_size_mb']:.2f} MB")
        print(f"  Summaries: {stats['cache_sizes']['summaries']['num_files']} files, "
              f"{stats['cache_sizes']['summaries']['total_size_mb']:.2f} MB")
        print()

        # Cleanup option
        if args.cleanup:
            print_info("Running cache cleanup...")
            cleanup_stats = cache_manager.cleanup_expired()
            print_success(f"Removed {cleanup_stats['total_removed']} expired entries")
            print(f"  Transcriptions: {cleanup_stats['removed_transcriptions']}")
            print(f"  Summaries: {cleanup_stats['removed_summaries']}")

        return 0

    except Exception as e:
        print_error(f"Failed to get cache stats: {str(e)}")
        logger.exception("Cache stats error")
        return 1


def cmd_validate(args, config):
    """Validate audio file without transcribing"""
    audio_path = args.audio_file

    if not Path(audio_path).exists():
        print_error(f"Audio file not found: {audio_path}")
        return 1

    try:
        audio_processor = AudioProcessor(max_size_mb=config['max_audio_size_mb'])

        print_info(f"Validating: {audio_path}")

        validation = audio_processor.validate_audio(audio_path)

        if validation['valid']:
            print_success("Audio file is valid")
        else:
            print_error("Audio file validation failed")

        # Display details
        print(f"\n{Fore.YELLOW}File Details:{Style.RESET_ALL}")
        print(f"  Format: {validation['format']}")
        print(f"  Size: {validation['file_size_mb']:.2f} MB")

        if validation['errors']:
            print(f"\n{Fore.RED}Errors:{Style.RESET_ALL}")
            for error in validation['errors']:
                print(f"  - {error}")

        if validation['warnings']:
            print(f"\n{Fore.YELLOW}Warnings:{Style.RESET_ALL}")
            for warning in validation['warnings']:
                print(f"  - {warning}")

        # Get metadata if valid
        if validation['valid']:
            metadata = audio_processor.get_metadata(audio_path)
            print(f"\n{Fore.YELLOW}Audio Metadata:{Style.RESET_ALL}")
            print(f"  Duration: {metadata['duration_seconds']:.1f}s ({metadata['duration_seconds']/60:.1f} min)")
            print(f"  Sample Rate: {metadata['sample_rate']} Hz")
            print(f"  Channels: {metadata['channels']}")
            print(f"  Bitrate: {metadata['bitrate']}")

        return 0 if validation['valid'] else 1

    except Exception as e:
        print_error(f"Validation failed: {str(e)}")
        logger.exception("Validation error")
        return 1


def cmd_analyze(args, config):
    """Analyze meeting: transcribe + summarize + extract actions"""
    print_banner()

    audio_path = args.audio_file

    if not Path(audio_path).exists():
        print_error(f"Audio file not found: {audio_path}")
        return 1

    try:
        # Initialize components
        print_info("Initializing analysis pipeline...")

        audio_processor = AudioProcessor(max_size_mb=config['max_audio_size_mb'])

        cache_manager = None
        if config['enable_cache']:
            cache_manager = CacheManager(
                cache_dir=config['cache_dir'],
                transcription_ttl_days=config['transcription_ttl_days'],
                summary_ttl_days=config['summary_ttl_days']
            )

        transcription_service = TranscriptionService(
            backend=config['transcription_backend'],
            api_key=config['openai_api_key'],
            model=config['whisper_model'],
            cache_manager=cache_manager,
            audio_processor=audio_processor,
            whisper_cpp_path=config['whisper_cpp_path'],
            whisper_model_path=config['whisper_model_path']
        )

        # Initialize LLM client
        llm_provider = os.getenv('LLM_PROVIDER', 'openai')
        llm_model = os.getenv('LLM_MODEL')

        if llm_provider == 'openai':
            api_key = config['openai_api_key']
        elif llm_provider == 'anthropic':
            api_key = os.getenv('ANTHROPIC_API_KEY')
        else:
            api_key = None

        llm_client = LLMClient(
            backend=llm_provider,
            model=llm_model,
            api_key=api_key
        )

        # Initialize meeting analyzer
        meeting_analyzer = MeetingAnalyzer(
            transcription_service=transcription_service,
            llm_client=llm_client,
            cache_manager=cache_manager,
            audio_processor=audio_processor
        )

        # Validate audio
        print_info(f"Validating audio file: {audio_path}")
        validation = audio_processor.validate_audio(audio_path)

        if not validation['valid']:
            print_error("Audio validation failed:")
            for error in validation['errors']:
                print(f"  - {error}")
            return 1

        # Show file info
        metadata = audio_processor.get_metadata(audio_path)
        print_info(f"Duration: {metadata['duration_seconds']:.1f}s ({metadata['duration_seconds']/60:.1f} min)")
        print_info(f"Format: {metadata['format']}")

        # Run analysis
        print_info("Starting full meeting analysis...")
        print()

        result = meeting_analyzer.analyze_meeting(
            audio_path,
            summary_level=args.level,
            extract_actions=not args.no_actions,
            extract_topics=not args.no_topics,
            language=args.language
        )

        # Display results
        print(f"{Fore.CYAN}{'='*60}")
        print(f"Analysis Complete")
        print(f"{'='*60}{Style.RESET_ALL}")
        print()

        print(f"{Fore.YELLOW}Summary:{Style.RESET_ALL}")
        print(result['summary']['text'])
        print()

        if result.get('topics'):
            print(f"{Fore.YELLOW}Key Topics:{Style.RESET_ALL}")
            for i, topic in enumerate(result['topics'], 1):
                print(f"  {i}. {topic}")
            print()

        if result.get('actions'):
            actions = result['actions']
            print(f"{Fore.YELLOW}Action Items: {actions['total_actions']}{Style.RESET_ALL}")
            for action in actions['action_items'][:5]:  # Show first 5
                print(f"  • {action['description']}")
                print(f"    Assignee: {action.get('assignee', 'Unassigned')}")
            if actions['total_actions'] > 5:
                print(f"  ... and {actions['total_actions'] - 5} more")
            print()

        # Statistics
        stats = result['statistics']
        print(f"{Fore.GREEN}Statistics:{Style.RESET_ALL}")
        print(f"  Processing Time: {stats['processing_time_seconds']:.1f}s")
        print(f"  Total Cost: ${stats['total_cost_usd']:.4f}")
        print(f"  Cache Hits: {stats['cache_hits']}")
        print()

        # Save report
        output_dir = Path(config['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)

        output_format = args.format or config['default_output_format']
        output_file = output_dir / f"{Path(audio_path).stem}_analysis.{output_format}"

        print_info(f"Generating {output_format} report...")
        report = meeting_analyzer.generate_report(
            result,
            format=output_format,
            output_path=str(output_file)
        )

        print_success(f"Report saved to: {output_file}")

        return 0

    except Exception as e:
        print_error(f"Analysis failed: {str(e)}")
        logger.exception("Analysis error")
        return 1


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Meeting Summarizer - Audio transcription with AI-powered summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Transcribe command
    transcribe_parser = subparsers.add_parser(
        'transcribe',
        help='Transcribe audio file'
    )
    transcribe_parser.add_argument(
        'audio_file',
        help='Path to audio file (mp3, wav, webm, m4a, ogg, flac)'
    )
    transcribe_parser.add_argument(
        '--language',
        help='Language code (e.g., en, es, fr)',
        default=None
    )
    transcribe_parser.add_argument(
        '--chunked',
        action='store_true',
        help='Force chunked transcription (useful for very long audio)'
    )
    transcribe_parser.add_argument(
        '--json',
        action='store_true',
        help='Also save output as JSON'
    )

    # Cache stats command
    cache_parser = subparsers.add_parser(
        'cache-stats',
        help='Show cache statistics'
    )
    cache_parser.add_argument(
        '--cleanup',
        action='store_true',
        help='Clean up expired cache entries'
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate audio file without transcribing'
    )
    validate_parser.add_argument(
        'audio_file',
        help='Path to audio file'
    )

    # Analyze command (Phase 2)
    analyze_parser = subparsers.add_parser(
        'analyze',
        help='Full meeting analysis: transcribe + summarize + extract actions'
    )
    analyze_parser.add_argument(
        'audio_file',
        help='Path to audio file'
    )
    analyze_parser.add_argument(
        '--level',
        choices=['brief', 'standard', 'detailed'],
        default='standard',
        help='Summary detail level'
    )
    analyze_parser.add_argument(
        '--language',
        help='Language code (e.g., en, es, fr)',
        default=None
    )
    analyze_parser.add_argument(
        '--format',
        choices=['markdown', 'json', 'html', 'txt'],
        help='Output format (default: from config)'
    )
    analyze_parser.add_argument(
        '--no-actions',
        action='store_true',
        help='Skip action item extraction'
    )
    analyze_parser.add_argument(
        '--no-topics',
        action='store_true',
        help='Skip topic extraction'
    )

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Load configuration
    config = load_config()

    # Execute command
    if args.command == 'transcribe':
        return cmd_transcribe(args, config)
    elif args.command == 'cache-stats':
        return cmd_cache_stats(args, config)
    elif args.command == 'validate':
        return cmd_validate(args, config)
    elif args.command == 'analyze':
        return cmd_analyze(args, config)
    else:
        print_error(f"Unknown command: {args.command}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
