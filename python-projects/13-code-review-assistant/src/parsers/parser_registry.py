"""Parser registry for managing language-specific parsers"""
from typing import Dict, Optional, List, Tuple
import re
from pathlib import Path
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

    Features:
    - Extension-based detection
    - Content-based detection (imports, keywords)
    - Shebang detection for scripts
    - Statistics and reporting
    """

    # Language detection patterns based on file content
    CONTENT_PATTERNS = {
        'python': [
            r'^import\s+\w+',
            r'^from\s+\w+\s+import',
            r'^\s*def\s+\w+\s*\(',
            r'^\s*class\s+\w+',
            r'if\s+__name__\s*==\s*["\']__main__["\']',
        ],
        'javascript': [
            r'^import\s+.*\s+from\s+["\']',
            r'^export\s+(default|const|function|class)',
            r'^\s*function\s+\w+\s*\(',
            r'^\s*const\s+\w+\s*=',
            r'require\s*\(["\']',
            r'=>\s*{',
        ],
        'java': [
            r'^package\s+[\w.]+;',
            r'^import\s+[\w.]+;',
            r'^\s*public\s+(class|interface|enum)',
            r'^\s*private\s+(static\s+)?final',
            r'System\.out\.print',
        ],
        'go': [
            r'^package\s+\w+',
            r'^import\s+\(',
            r'^func\s+\w+\s*\(',
            r'^\s*type\s+\w+\s+(struct|interface)',
            r'fmt\.Print',
        ],
        'rust': [
            r'^use\s+[\w:]+;',
            r'^fn\s+\w+\s*\(',
            r'^\s*(pub\s+)?struct\s+\w+',
            r'impl\s+\w+',
            r'println!\s*\(',
        ],
    }

    # Shebang patterns for script detection
    SHEBANG_PATTERNS = {
        'python': [r'#!/usr/bin/env python', r'#!/usr/bin/python'],
        'javascript': [r'#!/usr/bin/env node', r'#!/usr/bin/node'],
        'bash': [r'#!/bin/bash', r'#!/usr/bin/env bash', r'#!/bin/sh'],
    }

    def __init__(self):
        """Initialize parser registry"""
        self._parsers: Dict[str, BaseParser] = {}
        self._extension_map: Dict[str, str] = {}
        self._parse_stats: Dict[str, int] = {}  # Track parse counts per language
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

    def detect_language(self, file_path: str, content: Optional[str] = None) -> Optional[str]:
        """
        Detect programming language from file extension and optionally content.

        Args:
            file_path: Path to the file
            content: Optional file content for content-based detection

        Returns:
            Language identifier or None if not supported
        """
        # Try extension-based detection first
        ext = self._get_extension(file_path)
        lang = self._extension_map.get(ext)

        # If no extension match or content provided, try content-based detection
        if not lang and content:
            lang = self.detect_language_from_content(content)

        return lang

    def detect_language_from_content(self, content: str) -> Optional[str]:
        """
        Detect programming language from file content.

        Uses pattern matching on imports, keywords, and syntax patterns.

        Args:
            content: Source code content

        Returns:
            Language identifier or None if cannot determine
        """
        # Check shebang first (first line)
        lines = content.split('\n')
        if lines and lines[0].startswith('#!'):
            shebang_lang = self._detect_from_shebang(lines[0])
            if shebang_lang:
                return shebang_lang

        # Score each language based on pattern matches
        scores: Dict[str, int] = {}

        for language, patterns in self.CONTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, content, re.MULTILINE):
                    score += 1
            if score > 0:
                scores[language] = score

        # Return language with highest score
        if scores:
            return max(scores, key=scores.get)

        return None

    def _detect_from_shebang(self, shebang_line: str) -> Optional[str]:
        """
        Detect language from shebang line.

        Args:
            shebang_line: First line of file (shebang)

        Returns:
            Language identifier or None
        """
        for language, patterns in self.SHEBANG_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, shebang_line):
                    return language
        return None

    def parse_file(self, file_path: str, auto_detect: bool = True) -> ParsedModule:
        """
        Parse a file using the appropriate parser.

        Args:
            file_path: Path to the file to parse
            auto_detect: Use content-based detection if extension detection fails

        Returns:
            ParsedModule containing extracted code structure

        Raises:
            ParseError: If no parser found or parsing fails
        """
        parser = self.get_parser_for_file(file_path)

        # If no parser found by extension and auto_detect enabled, try content-based
        if not parser and auto_detect:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                language = self.detect_language_from_content(content)
                if language:
                    parser = self.get_parser(language)
            except Exception:
                pass  # Fall through to error below

        if not parser:
            raise ParseError(
                f"No parser available for file: {file_path}",
                file_path=file_path
            )

        # Track statistics
        language = self._get_language_for_parser(parser)
        if language:
            self._parse_stats[language] = self._parse_stats.get(language, 0) + 1

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

        # Track statistics
        self._parse_stats[language] = self._parse_stats.get(language, 0) + 1

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

    def get_parser_info(self) -> Dict[str, Dict[str, any]]:
        """
        Get detailed information about all registered parsers.

        Returns:
            Dictionary mapping language to parser info
        """
        info = {}
        for language, parser in self._parsers.items():
            info[language] = {
                'language': language,
                'extensions': parser.supported_extensions,
                'parser_class': parser.__class__.__name__,
                'parse_count': self._parse_stats.get(language, 0)
            }
        return info

    def get_statistics(self) -> Dict[str, int]:
        """
        Get parsing statistics.

        Returns:
            Dictionary mapping language to parse count
        """
        return dict(self._parse_stats)

    def get_language_stats(self) -> Tuple[int, int, Dict[str, int]]:
        """
        Get comprehensive language statistics.

        Returns:
            Tuple of (total_languages, total_extensions, parse_counts)
        """
        return (
            len(self._parsers),
            len(self._extension_map),
            dict(self._parse_stats)
        )

    def reset_statistics(self):
        """Reset all parsing statistics."""
        self._parse_stats.clear()

    def _get_language_for_parser(self, parser: BaseParser) -> Optional[str]:
        """
        Get language identifier for a parser instance.

        Args:
            parser: Parser instance

        Returns:
            Language identifier or None
        """
        for language, registered_parser in self._parsers.items():
            if registered_parser is parser:
                return language
        return None

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
