"""Abstract base class for code parsers"""
import io
import tokenize
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List
from .models import ParsedModule


class BaseParser(ABC):
    """
    Abstract base class for language-specific parsers.

    Each parser implementation should handle parsing for specific file types
    and convert code into a standardized ParsedModule structure.
    """

    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """
        Return file extensions this parser handles.

        Returns:
            List of file extensions (e.g., ['.py', '.pyw'])
        """
        pass

    @abstractmethod
    def parse_file(self, file_path: str) -> ParsedModule:
        """
        Parse a file and return structured data.

        Args:
            file_path: Path to the file to parse

        Returns:
            ParsedModule containing extracted code structure

        Raises:
            FileNotFoundError: If file doesn't exist
            ParseError: If parsing fails
        """
        pass

    @abstractmethod
    def parse_code(self, code: str, file_path: str = "<string>") -> ParsedModule:
        """
        Parse code string and return structured data.

        Args:
            code: Source code as string
            file_path: Optional path for reference (defaults to "<string>")

        Returns:
            ParsedModule containing extracted code structure

        Raises:
            ParseError: If parsing fails
        """
        pass

    def can_parse(self, file_path: str) -> bool:
        """
        Check if this parser can handle the given file.

        Args:
            file_path: Path to check

        Returns:
            True if this parser supports the file extension
        """
        # extensions are matched ignoring case (Foo.PY is Python), like file discovery does
        name = file_path.lower()
        return any(name.endswith(ext.lower()) for ext in self.supported_extensions)


class ParseError(Exception):
    """Exception raised when parsing fails"""

    def __init__(self, message: str, file_path: str = None, line_number: int = None):
        self.message = message
        self.file_path = file_path
        self.line_number = line_number

        error_msg = f"Parse error: {message}"
        if file_path:
            error_msg += f" in {file_path}"
        if line_number:
            error_msg += f" at line {line_number}"

        super().__init__(error_msg)


def decode_source(data: bytes) -> str:
    """Turn the bytes of a source file into text, whatever its encoding.

    Honours a UTF-8 byte-order mark and a ``# -*- coding: ... -*-`` declaration, and falls back to
    Windows-1252 and then Latin-1 instead of failing on a file that is not UTF-8. Bytes with nulls
    are not source code and are refused.

    Raises:
        ParseError: the data looks binary
    """
    if b"\x00" in data:
        raise ParseError("File looks like a binary file (it contains null bytes)", file_path=None)

    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    except (SyntaxError, LookupError):
        encoding = "utf-8"

    for candidate in (encoding, "cp1252", "latin-1"):
        try:
            return data.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1")  # cannot fail: kept for clarity


def read_source_text(file_path: str) -> str:
    """Read a source file as text (see decode_source).

    Raises:
        FileNotFoundError, OSError: the file cannot be read
        ParseError: the file looks binary
    """
    return decode_source(Path(file_path).read_bytes())
