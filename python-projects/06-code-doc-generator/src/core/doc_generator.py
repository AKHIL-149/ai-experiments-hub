"""Main documentation generator orchestrator"""
from pathlib import Path
from typing import List, Optional, Dict, Union

from ..parsers.parser_registry import ParserRegistry
from ..parsers.models import ParsedModule
from .ai_explainer import AIExplainer
from . import settings
from .llm_client import LLMClient, default_provider
from .cache_manager import CacheManager
from ..formatters import (
    MarkdownFormatter,
    HTMLFormatter,
    JSONFormatter,
    DocstringFormatter
)
from ..utils.file_utils import FileDiscovery, validate_file_readable


class AIUnavailableError(RuntimeError):
    """The AI part of a job that cannot be done without it did not work (message says why)."""


class DocGenerator:
    """
    Main orchestrator for code documentation generation.

    Coordinates parsing, AI enhancement, and output formatting
    to generate comprehensive documentation from source code.
    """

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        use_ai: bool = True,
        enable_cache: Optional[bool] = None,
        cache_dir: Optional[str] = None
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
        if enable_cache is None:
            enable_cache = settings.cache_enabled()
        self.use_ai = use_ai
        # Things that went wrong without stopping the run (a file that would not parse, AI that
        # went away); callers show them to the user. Reset by each generate_docs / enhance_code.
        self.warnings: List[str] = []
        self.parser_registry = ParserRegistry()
        self.file_discovery = FileDiscovery()

        # Initialize AI components if enabled
        self.ai_explainer: Optional[AIExplainer] = None
        if use_ai:
            try:
                llm_client = LLMClient(backend=llm_provider or default_provider(), model=model)
                cache_manager = CacheManager(cache_dir=cache_dir) if enable_cache else None
                self.ai_explainer = AIExplainer(llm_client, cache_manager, enable_cache)
            except Exception as e:
                self.warnings.append(f"AI features unavailable: {e}")
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
        self._reset_warnings()

        # Set default output directory
        if output_dir is None:
            output_dir = settings.default_output_dir()

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
                self.warnings.append(f"Skipped {Path(file_path).name}: {self._reason(e)}")
                continue

        if not parsed_modules:
            raise ValueError("No files could be parsed. " + " ".join(self.warnings))

        # Enhance with AI if enabled
        if self.use_ai and self.ai_explainer:
            parsed_modules = self._enhance_modules(parsed_modules)
            self._collect_ai_warnings()

        # Generate output in requested formats
        output_files = []
        format_errors = []

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
                format_errors.append(f"Could not write {fmt} output: {self._reason(e)}")

        self.warnings.extend(format_errors)
        if not output_files:
            raise RuntimeError(" ".join(format_errors) or "No output was produced")
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
            AIUnavailableError: If the model could not explain anything (nothing is written)
        """
        if not validate_file_readable(input_path):
            raise FileNotFoundError(f"File not found or not readable: {input_path}")

        if not self.use_ai or not self.ai_explainer:
            raise ValueError("AI features must be enabled to enhance code")
        self._reset_warnings()

        # Parse file
        parsed = self._parse_file(input_path)

        # Enhance with AI
        parsed = self._enhance_module(parsed)
        self._collect_ai_warnings()
        if not self.ai_explainer.answers and self.warnings:
            raise AIUnavailableError("No AI explanations could be generated. " + " ".join(self.warnings))

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
            'total_lines': 0,
            'failed_files': []
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
                    analysis['failed_files'].append({'path': file_path, 'error': self._reason(e)})

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
            module.ai_summary = self.ai_explainer.generate_module_summary(module) or None

            # Function explanations
            for func in module.functions:
                func.ai_explanation = self.ai_explainer.explain_function(
                    func,
                    context=Path(module.file_path).stem
                ) or None

                # Parameter descriptions
                if func.parameters:
                    func.parameters = self.ai_explainer.enhance_parameter_descriptions(
                        func.parameters,
                        function_context=func.name,
                        func_info=func
                    )

            # Class explanations
            for cls in module.classes:
                cls.ai_explanation = self.ai_explainer.explain_class(
                    cls,
                    context=Path(module.file_path).stem
                ) or None

                # Method explanations (every method, not just the first few)
                for method in cls.methods:
                    method.ai_explanation = self.ai_explainer.explain_function(
                        method,
                        context=f"{cls.name}.{method.name}"
                    ) or None

        except Exception as e:
            self.warnings.append(f"AI enhancement stopped early for {Path(module.file_path).name}: {self._reason(e)}")

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
        """Parse and validate output format(s): names are case-insensitive, 'all' means markdown+html+json"""
        requested = [output_format] if isinstance(output_format, str) else list(output_format)
        formats: List[str] = []
        for name in requested:
            name = str(name).strip().lower()
            if name == 'all':
                names = ['markdown', 'html', 'json']
            elif name in self.formatters:
                names = [name]
            else:
                raise ValueError(
                    f"Unsupported format: '{name}'. Choose from: {', '.join(self.formatters)}, all"
                )
            formats.extend(n for n in names if n not in formats)
        if not formats:
            raise ValueError("No output format given")
        return formats

    def _reset_warnings(self) -> None:
        """Start a run with only the warnings that belong to it (AI-setup warnings stay)"""
        self.warnings = [w for w in self.warnings if w.startswith("AI features unavailable")]
        if self.ai_explainer:
            self.ai_explainer.reset()

    def _collect_ai_warnings(self) -> None:
        if self.ai_explainer:
            for w in self.ai_explainer.warnings:
                if w not in self.warnings:
                    self.warnings.append(w)

    @staticmethod
    def _reason(error: Exception) -> str:
        """One line describing an error (parser errors can span several)"""
        return " ".join(str(error).split()) or type(error).__name__

    def get_available_parsers(self) -> List[str]:
        """Get list of available language parsers"""
        return self.parser_registry.list_available_parsers()

    def get_supported_formats(self) -> List[str]:
        """Get list of supported output formats"""
        return list(self.formatters.keys())
