"""Parser registry for auto-discovery and selection of parsers"""
from typing import List, Optional
from .base_parser import BaseParser, ParseError


class ParserRegistry:
    """
    Registry for managing multiple language parsers.

    Auto-discovers available parsers and selects the appropriate one
    based on file extension.
    """

    def __init__(self):
        self.parsers: List[BaseParser] = self._discover_parsers()

    def _discover_parsers(self) -> List[BaseParser]:
        """Auto-discover all available parser implementations"""
        parsers = []

        # Import and instantiate Python parser (always available)
        try:
            from .python_parser import PythonParser
            parsers.append(PythonParser())
        except Exception:
            pass  # Skip if unavailable

        # JavaScript parser (requires Node.js)
        try:
            from .javascript_parser import JavaScriptParser
            parsers.append(JavaScriptParser())
        except Exception:
            pass  # Skip if Node.js not available

        # Java parser (requires javalang)
        try:
            from .java_parser import JavaParser
            parsers.append(JavaParser())
        except Exception:
            pass  # Skip if javalang not installed

        return parsers

    def get_parser(self, file_path: str) -> BaseParser:
        """
        Get appropriate parser for a file.

        Args:
            file_path: Path to the file

        Returns:
            Parser instance that can handle the file

        Raises:
            ValueError: If no parser found for the file extension
        """
        for parser in self.parsers:
            if parser.can_parse(file_path):
                return parser

        # Extract extension for error message
        ext = file_path.split('.')[-1] if '.' in file_path else 'unknown'
        supported_exts = []
        for parser in self.parsers:
            supported_exts.extend(parser.supported_extensions)

        raise ValueError(
            f"No parser found for file '{file_path}' (extension: .{ext}). "
            f"Supported extensions: {', '.join(supported_exts)}"
        )

    def get_supported_extensions(self) -> List[str]:
        """
        Get all supported file extensions.

        Returns:
            List of all file extensions supported by registered parsers
        """
        extensions = []
        for parser in self.parsers:
            extensions.extend(parser.supported_extensions)
        return list(set(extensions))  # Remove duplicates

    def get_parser_for_language(self, language: str) -> Optional[BaseParser]:
        """
        Get parser for a specific language.

        Args:
            language: Language name (e.g., 'python', 'javascript', 'java')

        Returns:
            Parser instance or None if not found
        """
        language = language.lower()

        for parser in self.parsers:
            parser_name = parser.__class__.__name__.lower()
            if language in parser_name:
                return parser

        return None

    def list_available_parsers(self) -> List[str]:
        """
        List all available parser types.

        Returns:
            List of parser class names
        """
        return [parser.__class__.__name__ for parser in self.parsers]
