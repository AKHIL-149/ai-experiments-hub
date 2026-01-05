"""Abstract base class for documentation formatters"""
from abc import ABC, abstractmethod
from typing import List, Optional
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from parsers.models import ParsedModule


class BaseFormatter(ABC):
    """
    Abstract base class for all documentation formatters.

    Formatters convert ParsedModule data into specific output formats
    (Markdown, HTML, JSON, etc.).
    """

    @abstractmethod
    def format(self, parsed_module: ParsedModule, output_path: str) -> str:
        """
        Generate documentation and save to file.

        Args:
            parsed_module: Parsed module data with optional AI enhancements
            output_path: Path where the output file should be saved

        Returns:
            Path to the generated output file

        Raises:
            ValueError: If output_path is invalid
            IOError: If file cannot be written
        """
        pass

    @abstractmethod
    def format_batch(self, parsed_modules: List[ParsedModule], output_path: str) -> str:
        """
        Generate combined documentation for multiple modules.

        Args:
            parsed_modules: List of parsed module data
            output_path: Path where the combined output should be saved

        Returns:
            Path to the generated output file

        Raises:
            ValueError: If output_path is invalid or modules list is empty
            IOError: If file cannot be written
        """
        pass

    @abstractmethod
    def supports_batch(self) -> bool:
        """
        Check if formatter supports batch processing.

        Returns:
            True if formatter can combine multiple modules into single output
        """
        pass

    def _ensure_output_dir(self, output_path: str) -> None:
        """
        Ensure output directory exists.

        Args:
            output_path: Path to output file
        """
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

    def _safe_write(self, output_path: str, content: str) -> str:
        """
        Safely write content to file.

        Args:
            output_path: Path to output file
            content: Content to write

        Returns:
            Absolute path to written file

        Raises:
            IOError: If write fails
        """
        try:
            self._ensure_output_dir(output_path)
            output_file = Path(output_path)
            output_file.write_text(content, encoding='utf-8')
            return str(output_file.absolute())
        except Exception as e:
            raise IOError(f"Failed to write output file: {e}")


class FormatterError(Exception):
    """Exception raised for formatter-specific errors"""
    pass
