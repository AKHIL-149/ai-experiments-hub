"""Parser registry for managing language-specific parsers"""
from typing import Dict, Optional, List
from .base_parser import BaseParser, ParseError
from .python_parser import PythonParser
from .javascript_parser import JavaScriptParser
from .java_parser import JavaParser
from .go_parser import GoParser
from .rust_parser import RustParser
from .models import ParsedModule


class ParserRegistry:
    """
    Registry for managing and accessing language-specific parsers.

    Automatically registers available parsers and provides methods
    to get the appropriate parser for a given file.
    """

    def __init__(self):
        """Initialize parser registry"""
        self._parsers: Dict[str, BaseParser] = {}
        self._extension_map: Dict[str, str] = {}
        self._register_default_parsers()

    def _register_default_parsers(self):
        """Register all available parsers"""
        self.register_parser('python', PythonParser())
        self.register_parser('javascript', JavaScriptParser())
        self.register_parser('java', JavaParser())
        self.register_parser('go', GoParser())
        self.register_parser('rust', RustParser())

    def register_parser(self, language: str, parser: BaseParser):
        """
        Register a parser for a specific language.

        Args:
            language: Language identifier (e.g., 'python', 'javascript')
            parser: Parser instance implementing BaseParser
        """
        self._parsers[language] = parser

        for ext in parser.supported_extensions:
            self._extension_map[ext] = language

    def get_parser(self, language: str) -> Optional[BaseParser]:
        """
        Get parser for a specific language.

        Args:
            language: Language identifier

        Returns:
            Parser instance or None if not found
        """
        return self._parsers.get(language)

    def get_parser_for_file(self, file_path: str) -> Optional[BaseParser]:
        """
        Get appropriate parser for a file based on extension.

        Args:
            file_path: Path to the file

        Returns:
            Parser instance or None if no parser supports this file
        """
        for parser in self._parsers.values():
            if parser.can_parse(file_path):
                return parser
        return None

    def detect_language(self, file_path: str) -> Optional[str]:
        """
        Detect programming language from file extension.

        Args:
            file_path: Path to the file

        Returns:
            Language identifier or None if not supported
        """
        ext = self._get_extension(file_path)
        return self._extension_map.get(ext)

    def parse_file(self, file_path: str) -> ParsedModule:
        """
        Parse a file using the appropriate parser.

        Args:
            file_path: Path to the file to parse

        Returns:
            ParsedModule containing extracted code structure

        Raises:
            ParseError: If no parser found or parsing fails
        """
        parser = self.get_parser_for_file(file_path)
        if not parser:
            raise ParseError(
                f"No parser available for file: {file_path}",
                file_path=file_path
            )

        return parser.parse_file(file_path)

    def parse_code(self, code: str, language: str, file_path: str = "<string>") -> ParsedModule:
        """
        Parse code string using specified language parser.

        Args:
            code: Source code string
            language: Language identifier
            file_path: Optional file path for reference

        Returns:
            ParsedModule containing extracted code structure

        Raises:
            ParseError: If no parser found or parsing fails
        """
        parser = self.get_parser(language)
        if not parser:
            raise ParseError(f"No parser available for language: {language}")

        return parser.parse_code(code, file_path)

    def get_supported_languages(self) -> List[str]:
        """
        Get list of supported languages.

        Returns:
            List of language identifiers
        """
        return list(self._parsers.keys())

    def get_supported_extensions(self) -> List[str]:
        """
        Get list of all supported file extensions.

        Returns:
            List of file extensions
        """
        return list(self._extension_map.keys())

    def is_supported(self, file_path: str) -> bool:
        """
        Check if a file is supported by any parser.

        Args:
            file_path: Path to check

        Returns:
            True if file can be parsed
        """
        return self.get_parser_for_file(file_path) is not None

    @staticmethod
    def _get_extension(file_path: str) -> str:
        """Extract file extension from path"""
        if '.' in file_path:
            return '.' + file_path.rsplit('.', 1)[1].lower()
        return ''


# Global singleton instance
_registry = ParserRegistry()


def get_registry() -> ParserRegistry:
    """
    Get the global parser registry instance.

    Returns:
        Global ParserRegistry instance
    """
    return _registry
