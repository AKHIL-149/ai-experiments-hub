#!/usr/bin/env python3
"""
Code Documentation Generator CLI

Main command-line interface for generating documentation from source code.
"""
import argparse
import sys
from pathlib import Path
from typing import List, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.core.doc_generator import DocGenerator
from src.utils.file_utils import FileDiscovery, get_file_stats, format_file_size

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


class CLI:
    """Command-line interface for documentation generator"""

    def __init__(self):
        """Initialize CLI"""
        self.parser = self._create_parser()

    def _create_parser(self) -> argparse.ArgumentParser:
        """Create argument parser with all commands"""
        parser = argparse.ArgumentParser(
            prog='doc-gen',
            description='AI-powered code documentation generator',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Generate Markdown docs for a file
  %(prog)s generate mycode.py

  # Generate multiple formats for a directory
  %(prog)s generate src/ --format markdown,html,json --output docs/

  # Generate with specific LLM provider
  %(prog)s generate src/ --provider anthropic --model claude-3-5-sonnet

  # Disable AI enhancements
  %(prog)s generate src/ --no-ai

  # Analyze code structure
  %(prog)s analyze src/

  # Enhance code with docstrings
  %(prog)s enhance mycode.py --output mycode_documented.py
            """
        )

        parser.add_argument(
            '--version',
            action='version',
            version='%(prog)s 0.7.2'
        )

        # Create subparsers for commands
        subparsers = parser.add_subparsers(dest='command', help='Available commands')

        # Generate command
        self._add_generate_command(subparsers)

        # Enhance command (placeholder for 0.6.5.3)
        self._add_enhance_command(subparsers)

        # Analyze command (placeholder for 0.6.5.3)
        self._add_analyze_command(subparsers)

        # Serve command (placeholder for 0.6.5.4)
        self._add_serve_command(subparsers)

        return parser

    def _add_generate_command(self, subparsers):
        """Add generate command"""
        gen_parser = subparsers.add_parser(
            'generate',
            help='Generate documentation from source code',
            description='Parse source code and generate comprehensive documentation'
        )

        gen_parser.add_argument(
            'input',
            help='File or directory to document'
        )

        gen_parser.add_argument(
            '--format', '-f',
            default='markdown',
            help='Output format(s): markdown, html, json, docstring, all (default: markdown). '
                 'Comma-separated for multiple formats'
        )

        gen_parser.add_argument(
            '--output', '-o',
            help='Output directory (default: ./data/output)'
        )

        gen_parser.add_argument(
            '--recursive', '-r',
            action='store_true',
            default=True,
            help='Recursively process directories (default: True)'
        )

        gen_parser.add_argument(
            '--no-recursive',
            action='store_false',
            dest='recursive',
            help='Do not process directories recursively'
        )

        gen_parser.add_argument(
            '--provider',
            choices=['ollama', 'anthropic', 'openai'],
            default='ollama',
            help='LLM provider (default: ollama)'
        )

        gen_parser.add_argument(
            '--model',
            help='LLM model to use (uses provider default if not specified)'
        )

        gen_parser.add_argument(
            '--no-ai',
            action='store_true',
            help='Disable AI enhancements (faster, template-based docs only)'
        )

        gen_parser.add_argument(
            '--no-cache',
            action='store_true',
            help='Disable caching (forces fresh generation)'
        )

        gen_parser.add_argument(
            '--cache-dir',
            default='./data/cache',
            help='Cache directory (default: ./data/cache)'
        )

        gen_parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Verbose output'
        )

    def _add_enhance_command(self, subparsers):
        """Add enhance command (placeholder for 0.6.5.3)"""
        enh_parser = subparsers.add_parser(
            'enhance',
            help='Add AI-generated docstrings to source code',
            description='Enhance source code with AI-generated documentation'
        )

        enh_parser.add_argument(
            'input',
            help='Source file to enhance'
        )

        enh_parser.add_argument(
            '--output', '-o',
            help='Output file path (default: <input>_documented)'
        )

        enh_parser.add_argument(
            '--style',
            choices=['auto', 'google', 'numpy', 'jsdoc', 'javadoc'],
            default='auto',
            help='Docstring style (default: auto-detect)'
        )

        enh_parser.add_argument(
            '--provider',
            choices=['ollama', 'anthropic', 'openai'],
            default='ollama',
            help='LLM provider (default: ollama)'
        )

        enh_parser.add_argument(
            '--model',
            help='LLM model to use'
        )

    def _add_analyze_command(self, subparsers):
        """Add analyze command (placeholder for 0.6.5.3)"""
        ana_parser = subparsers.add_parser(
            'analyze',
            help='Analyze code structure without generating docs',
            description='Analyze and display code structure statistics'
        )

        ana_parser.add_argument(
            'input',
            help='File or directory to analyze'
        )

        ana_parser.add_argument(
            '--details',
            action='store_true',
            help='Show detailed analysis'
        )

    def _add_serve_command(self, subparsers):
        """Add serve command (placeholder for 0.6.5.4)"""
        srv_parser = subparsers.add_parser(
            'serve',
            help='Start web UI server',
            description='Start web interface for documentation generation'
        )

        srv_parser.add_argument(
            '--host',
            default='127.0.0.1',
            help='Host to bind (default: 127.0.0.1)'
        )

        srv_parser.add_argument(
            '--port', '-p',
            type=int,
            default=8000,
            help='Port to bind (default: 8000)'
        )

    def run(self, args=None):
        """Run CLI with arguments"""
        parsed_args = self.parser.parse_args(args)

        if not parsed_args.command:
            self.parser.print_help()
            return 1

        # Route to command handlers
        if parsed_args.command == 'generate':
            return self.handle_generate(parsed_args)
        elif parsed_args.command == 'enhance':
            return self.handle_enhance(parsed_args)
        elif parsed_args.command == 'analyze':
            return self.handle_analyze(parsed_args)
        elif parsed_args.command == 'serve':
            return self.handle_serve(parsed_args)

        return 0

    def handle_generate(self, args) -> int:
        """Handle generate command"""
        try:
            print(f"🚀 Code Documentation Generator v0.6.5\n")

            # Validate input
            input_path = Path(args.input)
            if not input_path.exists():
                print(f"❌ Error: Input path not found: {args.input}")
                return 1

            # Parse formats
            formats = self._parse_formats(args.format)

            # Display configuration
            print("📋 Configuration:")
            print(f"   Input:     {args.input}")
            print(f"   Format(s): {', '.join(formats)}")
            print(f"   Output:    {args.output or './data/output'}")
            print(f"   AI:        {'Enabled' if not args.no_ai else 'Disabled'}")
            if not args.no_ai:
                print(f"   Provider:  {args.provider}")
                if args.model:
                    print(f"   Model:     {args.model}")
            print(f"   Cache:     {'Enabled' if not args.no_cache else 'Disabled'}")
            print()

            # Discover files
            print("🔍 Discovering files...")
            discovery = FileDiscovery()
            files = discovery.discover_files(
                args.input,
                recursive=args.recursive
            )

            if not files:
                print(f"❌ No supported source files found in: {args.input}")
                return 1

            # Show file statistics
            by_language = discovery.group_by_language(files)
            print(f"✓ Found {len(files)} file(s):")
            for lang, lang_files in by_language.items():
                print(f"   • {lang}: {len(lang_files)} file(s)")

            if args.verbose:
                stats = get_file_stats(files)
                print(f"\n📊 Statistics:")
                print(f"   Total size:  {stats['total_size_formatted']}")
                print(f"   Total lines: {stats['total_lines']:,}")
                print(f"   Avg lines:   {stats['avg_lines']:,}")

            print()

            # Initialize generator
            print("⚙️  Initializing generator...")
            generator = DocGenerator(
                llm_provider=args.provider,
                model=args.model,
                use_ai=not args.no_ai,
                enable_cache=not args.no_cache,
                cache_dir=args.cache_dir
            )
            print("✓ Generator ready")
            print()

            # Generate documentation with progress
            print(f"📝 Generating documentation...")

            if TQDM_AVAILABLE:
                # Use progress bar
                with tqdm(total=len(formats), desc="Formats", unit="format") as pbar:
                    output_files = generator.generate_docs(
                        input_path=args.input,
                        output_format=formats,
                        output_dir=args.output,
                        recursive=args.recursive
                    )
                    pbar.update(len(formats))
            else:
                # No progress bar
                output_files = generator.generate_docs(
                    input_path=args.input,
                    output_format=formats,
                    output_dir=args.output,
                    recursive=args.recursive
                )

            # Display results
            print()
            print("✅ Documentation generated successfully!\n")
            print("📁 Output files:")
            for file_path in output_files:
                file_size = Path(file_path).stat().st_size
                print(f"   • {Path(file_path).name} ({format_file_size(file_size)})")

            print()
            print(f"💾 Location: {Path(output_files[0]).parent}")

            # Show hints for HTML output
            if 'html' in formats:
                html_file = next((f for f in output_files if f.endswith('.html')), None)
                if html_file:
                    print(f"\n💡 Tip: Open in browser: file://{Path(html_file).absolute()}")

            return 0

        except KeyboardInterrupt:
            print("\n\n⚠️  Generation cancelled by user")
            return 1
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            return 1

    def handle_enhance(self, args) -> int:
        """Handle enhance command"""
        try:
            print(f"🚀 Code Enhancement v0.6.5\n")

            # Validate input
            input_path = Path(args.input)
            if not input_path.exists():
                print(f"❌ Error: Input file not found: {args.input}")
                return 1

            if not input_path.is_file():
                print(f"❌ Error: Input must be a file, not a directory: {args.input}")
                return 1

            # Display configuration
            print("📋 Configuration:")
            print(f"   Input:    {args.input}")
            print(f"   Output:   {args.output or '<input>_documented'}")
            print(f"   Style:    {args.style}")
            print(f"   Provider: {args.provider}")
            if args.model:
                print(f"   Model:    {args.model}")
            print()

            # Initialize generator with AI
            print("⚙️  Initializing AI enhancer...")
            generator = DocGenerator(
                llm_provider=args.provider,
                model=args.model,
                use_ai=True,  # Must have AI for enhancement
                enable_cache=True
            )

            if not generator.use_ai:
                print("❌ Error: AI features are required for code enhancement")
                print("   Please ensure LLM provider is available and configured")
                return 1

            print("✓ AI enhancer ready")
            print()

            # Enhance code
            print(f"✨ Enhancing code with AI-generated docstrings...")

            output_path = generator.enhance_code(
                input_path=args.input,
                output_path=args.output,
                style=args.style
            )

            # Display results
            print()
            print("✅ Code enhanced successfully!\n")

            # Show file info
            input_size = input_path.stat().st_size
            output_size = Path(output_path).stat().st_size
            size_increase = output_size - input_size

            print("📁 Files:")
            print(f"   • Input:  {input_path.name} ({format_file_size(input_size)})")
            print(f"   • Output: {Path(output_path).name} ({format_file_size(output_size)})")
            print(f"   • Added:  {format_file_size(size_increase)} of documentation")

            print()
            print(f"💾 Location: {Path(output_path).parent}")

            # Show backup info
            backup_file = Path(str(input_path) + '.backup')
            if backup_file.exists():
                print(f"📦 Backup:   {backup_file.name}")

            return 0

        except KeyboardInterrupt:
            print("\n\n⚠️  Enhancement cancelled by user")
            return 1
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            return 1

    def handle_analyze(self, args) -> int:
        """Handle analyze command"""
        try:
            print(f"🔍 Code Structure Analyzer v0.6.5\n")

            # Validate input
            input_path = Path(args.input)
            if not input_path.exists():
                print(f"❌ Error: Input path not found: {args.input}")
                return 1

            print(f"📂 Analyzing: {args.input}\n")

            # Initialize generator (no AI needed for analysis)
            generator = DocGenerator(use_ai=False)

            # Analyze structure
            analysis = generator.analyze_structure(
                args.input,
                show_details=args.details
            )

            # Display summary
            print("📊 Summary:")
            print(f"   Total files:     {analysis['total_files']}")
            print(f"   Total functions: {analysis['total_functions']}")
            print(f"   Total classes:   {analysis['total_classes']}")
            print()

            # Display by language
            if analysis['languages']:
                print("📝 By Language:")
                for lang, stats in analysis['languages'].items():
                    print(f"\n   {lang.upper()}:")
                    print(f"      Files:     {stats['file_count']}")
                    print(f"      Functions: {stats['functions']}")
                    print(f"      Classes:   {stats['classes']}")

                    # Show detailed breakdown if requested
                    if args.details and stats['files']:
                        print(f"\n      Files:")
                        for file_info in stats['files']:
                            rel_path = self._get_display_path(file_info['path'], args.input)
                            print(f"         • {rel_path}")
                            print(f"           Functions: {file_info['functions']}, Classes: {file_info['classes']}")

                            if 'function_names' in file_info and file_info['function_names']:
                                print(f"           Functions: {', '.join(file_info['function_names'][:5])}")
                                if len(file_info['function_names']) > 5:
                                    print(f"              ... and {len(file_info['function_names']) - 5} more")

                            if 'class_names' in file_info and file_info['class_names']:
                                print(f"           Classes: {', '.join(file_info['class_names'][:5])}")
                                if len(file_info['class_names']) > 5:
                                    print(f"              ... and {len(file_info['class_names']) - 5} more")
            else:
                print("⚠️  No supported source files found")

            print()
            print("✅ Analysis complete!")

            return 0

        except KeyboardInterrupt:
            print("\n\n⚠️  Analysis cancelled by user")
            return 1
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            return 1

    def _get_display_path(self, file_path: str, base_path: str) -> str:
        """Get relative path for display"""
        try:
            return str(Path(file_path).relative_to(Path(base_path).parent))
        except ValueError:
            return str(Path(file_path).name)

    def handle_serve(self, args) -> int:
        """Handle serve command - Start FastAPI web server"""
        try:
            # Check if web dependencies are available
            try:
                from src.web import start_server
            except ImportError as e:
                print(f"❌ Error: Web interface dependencies not installed\n")
                print("Install with one of the following:")
                print("   pip install 'fastapi>=0.109.0' 'uvicorn>=0.27.0' 'jinja2>=3.1.0'")
                print("   pip install -e '.[web]'")
                print("   pip install -e '.[all]'\n")
                print(f"Details: {str(e)}")
                return 1

            print(f"🚀 Code Documentation Generator v0.7.2\n")
            print(f"Starting web server...")
            print(f"   Host: {args.host}")
            print(f"   Port: {args.port}\n")

            # Start the web server
            return start_server(
                host=args.host,
                port=args.port,
                reload=False,
                log_level="info"
            )

        except KeyboardInterrupt:
            print("\n\n⚠️  Server stopped by user")
            return 0
        except Exception as e:
            print(f"\n❌ Error starting server: {str(e)}")
            return 1

    def _parse_formats(self, format_str: str) -> List[str]:
        """Parse format string into list of formats"""
        if format_str == 'all':
            return ['markdown', 'html', 'json']

        # Split by comma and clean
        formats = [f.strip() for f in format_str.split(',')]

        # Validate
        valid_formats = {'markdown', 'html', 'json', 'docstring'}
        for fmt in formats:
            if fmt not in valid_formats:
                raise ValueError(f"Invalid format: {fmt}. Valid options: {', '.join(valid_formats)}")

        return formats


def main():
    """Main entry point"""
    cli = CLI()
    return cli.run()


if __name__ == '__main__':
    sys.exit(main())
