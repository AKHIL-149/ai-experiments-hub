"""Main documentation generator orchestrator"""
from pathlib import Path
from typing import List, Optional, Dict, Union

from ..parsers.parser_registry import ParserRegistry
from ..parsers.models import ParsedModule
from .ai_explainer import AIExplainer
from .llm_client import LLMClient
from .cache_manager import CacheManager
from ..formatters import (
    MarkdownFormatter,
    HTMLFormatter,
    JSONFormatter,
    DocstringFormatter
)
from ..utils.file_utils import FileDiscovery, validate_file_readable


class DocGenerator:
    """
    Main orchestrator for code documentation generation.

    Coordinates parsing, AI enhancement, and output formatting
    to generate comprehensive documentation from source code.
    """

    def __init__(
        self,
        llm_provider: str = "ollama",
        model: Optional[str] = None,
        use_ai: bool = True,
        enable_cache: bool = True,
        cache_dir: str = "./data/cache"
    ):
        """
        Initialize documentation generator.

        Args:
            llm_provider: LLM backend ('ollama', 'anthropic', 'openai')
            model: Model name (uses provider default if None)
            use_ai: Whether to use AI enhancements
            enable_cache: Whether to enable caching
            cache_dir: Directory for cache storage
        """
        self.use_ai = use_ai
        self.parser_registry = ParserRegistry()
        self.file_discovery = FileDiscovery()

        # Initialize AI components if enabled
        self.ai_explainer: Optional[AIExplainer] = None
        if use_ai:
            try:
                llm_client = LLMClient(backend=llm_provider, model=model)
                cache_manager = CacheManager(cache_dir=cache_dir) if enable_cache else None
                self.ai_explainer = AIExplainer(llm_client, cache_manager, enable_cache)
            except Exception as e:
                print(f"Warning: AI features unavailable: {e}")
                self.use_ai = False

        # Initialize formatters
        self.formatters = {
            'markdown': MarkdownFormatter(include_toc=True),
            'html': HTMLFormatter(theme='light', include_search=True),
            'json': JSONFormatter(pretty=True, include_metadata=True),
            'docstring': DocstringFormatter(style='auto', create_backup=True)
        }

    def generate_docs(
        self,
        input_path: str,
        output_format: Union[str, List[str]] = 'markdown',
        output_dir: Optional[str] = None,
        recursive: bool = True
    ) -> List[str]:
        """
        Generate documentation for code files.

        Args:
            input_path: File or directory to document
            output_format: Output format(s) - single string or list
                          Options: 'markdown', 'html', 'json', or 'all'
            output_dir: Output directory (defaults to './data/output')
            recursive: Whether to recursively process directories

        Returns:
            List of generated output file paths

        Raises:
            FileNotFoundError: If input_path doesn't exist
            ValueError: If unsupported format specified
        """
        # Normalize format(s)
        formats = self._parse_formats(output_format)

        # Set default output directory
        if output_dir is None:
            output_dir = './data/output'

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Discover files
        files = self.file_discovery.discover_files(input_path, recursive=recursive)

        if not files:
            raise ValueError(f"No supported source files found in: {input_path}")

        # Parse all files
        parsed_modules = []
        for file_path in files:
            try:
                parsed = self._parse_file(file_path)
                parsed_modules.append(parsed)
            except Exception as e:
                print(f"Warning: Failed to parse {file_path}: {e}")
                continue

        if not parsed_modules:
            raise ValueError("No files were successfully parsed")

        # Enhance with AI if enabled
        if self.use_ai and self.ai_explainer:
            parsed_modules = self._enhance_modules(parsed_modules)

        # Generate output in requested formats
        output_files = []

        for fmt in formats:
            try:
                generated = self._generate_output(
                    parsed_modules,
                    fmt,
                    output_path,
                    input_path
                )
                output_files.extend(generated)
            except Exception as e:
                print(f"Warning: Failed to generate {fmt} output: {e}")

        return output_files

    def enhance_code(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        style: str = 'auto'
    ) -> str:
        """
        Enhance source code with AI-generated docstrings.

        Args:
            input_path: Source file to enhance
            output_path: Output file path (defaults to input_path + '_documented')
            style: Docstring style ('auto', 'google', 'numpy', 'jsdoc', 'javadoc')

        Returns:
            Path to enhanced output file

        Raises:
            FileNotFoundError: If input file doesn't exist
            ValueError: If AI features not available
        """
        if not validate_file_readable(input_path):
            raise FileNotFoundError(f"File not found or not readable: {input_path}")

        if not self.use_ai or not self.ai_explainer:
            raise ValueError("AI features must be enabled to enhance code")

        # Parse file
        parsed = self._parse_file(input_path)

        # Enhance with AI
        parsed = self._enhance_module(parsed)

        # Generate output path
        if output_path is None:
            input_file = Path(input_path)
            output_path = str(input_file.parent / f"{input_file.stem}_documented{input_file.suffix}")

        # Use docstring formatter
        formatter = DocstringFormatter(style=style, create_backup=True)
        result = formatter.format(parsed, output_path)

        return result

    def analyze_structure(self, input_path: str, show_details: bool = False) -> Dict:
        """
        Analyze code structure without generating documentation.

        Args:
            input_path: File or directory to analyze
            show_details: Whether to include detailed analysis

        Returns:
            Dictionary with structure analysis

        Raises:
            FileNotFoundError: If input_path doesn't exist
        """
        # Discover files
        files = self.file_discovery.discover_files(input_path, recursive=True)

        if not files:
            raise ValueError(f"No supported source files found in: {input_path}")

        # Group by language
        by_language = self.file_discovery.group_by_language(files)

        # Parse and analyze
        analysis = {
            'total_files': len(files),
            'languages': {},
            'total_functions': 0,
            'total_classes': 0,
            'total_lines': 0
        }

        for language, lang_files in by_language.items():
            lang_stats = {
                'file_count': len(lang_files),
                'functions': 0,
                'classes': 0,
                'files': []
            }

            for file_path in lang_files:
                try:
                    parsed = self._parse_file(file_path)

                    file_info = {
                        'path': file_path,
                        'functions': len(parsed.functions),
                        'classes': len(parsed.classes)
                    }

                    if show_details:
                        file_info['function_names'] = [f.name for f in parsed.functions]
                        file_info['class_names'] = [c.name for c in parsed.classes]

                    lang_stats['functions'] += len(parsed.functions)
                    lang_stats['classes'] += len(parsed.classes)
                    lang_stats['files'].append(file_info)

                except Exception as e:
                    print(f"Warning: Failed to analyze {file_path}: {e}")

            analysis['languages'][language] = lang_stats
            analysis['total_functions'] += lang_stats['functions']
            analysis['total_classes'] += lang_stats['classes']

        return analysis

    def _parse_file(self, file_path: str) -> ParsedModule:
        """Parse a single file"""
        parser = self.parser_registry.get_parser(file_path)
        return parser.parse_file(file_path)

    def _enhance_module(self, module: ParsedModule) -> ParsedModule:
        """Enhance single module with AI"""
        if not self.ai_explainer:
            return module

        try:
            # Module summary
            module.ai_summary = self.ai_explainer.generate_module_summary(module)

            # Function explanations
            for func in module.functions:
                func.ai_explanation = self.ai_explainer.explain_function(
                    func,
                    context=Path(module.file_path).stem
                )

                # Parameter descriptions
                if func.parameters:
                    func.parameters = self.ai_explainer.enhance_parameter_descriptions(
                        func.parameters,
                        function_context=func.name
                    )

            # Class explanations
            for cls in module.classes:
                cls.ai_explanation = self.ai_explainer.explain_class(
                    cls,
                    context=Path(module.file_path).stem
                )

                # Method explanations (first 3 methods)
                for method in cls.methods[:3]:
                    method.ai_explanation = self.ai_explainer.explain_function(
                        method,
                        context=f"{cls.name}.{method.name}"
                    )

        except Exception as e:
            print(f"Warning: AI enhancement failed for {module.file_path}: {e}")

        return module

    def _enhance_modules(self, modules: List[ParsedModule]) -> List[ParsedModule]:
        """Enhance multiple modules with AI"""
        enhanced = []
        for module in modules:
            enhanced.append(self._enhance_module(module))
        return enhanced

    def _generate_output(
        self,
        modules: List[ParsedModule],
        format_name: str,
        output_dir: Path,
        input_path: str
    ) -> List[str]:
        """Generate output in specified format"""
        formatter = self.formatters.get(format_name)

        if not formatter:
            raise ValueError(f"Unsupported format: {format_name}")

        # Determine output filename
        input_name = Path(input_path).stem
        if Path(input_path).is_dir():
            base_name = Path(input_path).name
        else:
            base_name = input_name

        output_files = []

        # Docstring format handles single files only
        if format_name == 'docstring':
            for module in modules:
                output_path = output_dir / f"{Path(module.file_path).stem}_documented{Path(module.file_path).suffix}"
                result = formatter.format(module, str(output_path))
                output_files.append(result)

        # Other formats support batch processing
        else:
            extensions = {
                'markdown': '.md',
                'html': '.html',
                'json': '.json'
            }

            ext = extensions.get(format_name, '.txt')

            # Single file or batch?
            if len(modules) == 1:
                output_path = output_dir / f"{base_name}_docs{ext}"
                result = formatter.format(modules[0], str(output_path))
                output_files.append(result)
            else:
                output_path = output_dir / f"{base_name}_docs{ext}"
                result = formatter.format_batch(modules, str(output_path))
                output_files.append(result)

        return output_files

    def _parse_formats(self, output_format: Union[str, List[str]]) -> List[str]:
        """Parse and validate output format(s)"""
        if isinstance(output_format, str):
            if output_format == 'all':
                return ['markdown', 'html', 'json']
            return [output_format]

        return output_format

    def get_available_parsers(self) -> List[str]:
        """Get list of available language parsers"""
        return self.parser_registry.list_available_parsers()

    def get_supported_formats(self) -> List[str]:
        """Get list of supported output formats"""
        return list(self.formatters.keys())
