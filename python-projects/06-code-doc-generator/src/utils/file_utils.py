"""File utility functions for code discovery and validation"""
from pathlib import Path
from typing import List, Set, Optional, Dict
import os


class FileDiscovery:
    """
    Handles file discovery and filtering for code analysis.

    Provides utilities to recursively find source code files,
    filter by extension, and validate file accessibility.
    """

    # Default extensions for supported languages
    SUPPORTED_EXTENSIONS = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.java': 'java'
    }

    # Directories to skip during recursive search
    DEFAULT_IGNORE = {
        '__pycache__',
        'node_modules',
        '.git',
        '.svn',
        '.hg',
        'venv',
        'env',
        '.venv',
        'dist',
        'build',
        'target',
        '.idea',
        '.vscode',
        'coverage',
        '.pytest_cache',
        '.mypy_cache'
    }

    def __init__(self, ignore_dirs: Optional[Set[str]] = None):
        """
        Initialize file discovery.

        Args:
            ignore_dirs: Additional directories to ignore (merged with defaults)
        """
        self.ignore_dirs = self.DEFAULT_IGNORE.copy()
        if ignore_dirs:
            self.ignore_dirs.update(ignore_dirs)

    def discover_files(
        self,
        path: str,
        extensions: Optional[List[str]] = None,
        recursive: bool = True
    ) -> List[str]:
        """
        Discover source code files in a path.

        Args:
            path: File or directory path to search
            extensions: List of file extensions to include (e.g., ['.py', '.js'])
                       If None, uses all supported extensions
            recursive: Whether to search subdirectories

        Returns:
            List of absolute file paths

        Raises:
            FileNotFoundError: If path doesn't exist
            ValueError: If path is neither file nor directory
        """
        target_path = Path(path).resolve()

        if not target_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        # Single file
        if target_path.is_file():
            if self._should_include_file(target_path, extensions):
                return [str(target_path)]
            return []

        # Directory
        if target_path.is_dir():
            return self._discover_in_directory(target_path, extensions, recursive)

        raise ValueError(f"Path is neither file nor directory: {path}")

    def _discover_in_directory(
        self,
        directory: Path,
        extensions: Optional[List[str]],
        recursive: bool
    ) -> List[str]:
        """Discover files within a directory"""
        files = []

        try:
            for entry in directory.iterdir():
                # Skip ignored directories
                if entry.is_dir():
                    if entry.name in self.ignore_dirs:
                        continue
                    if recursive:
                        files.extend(
                            self._discover_in_directory(entry, extensions, recursive)
                        )

                # Check files
                elif entry.is_file():
                    if self._should_include_file(entry, extensions):
                        files.append(str(entry))

        except PermissionError:
            # Skip directories we can't read
            pass

        return sorted(files)

    def _should_include_file(
        self,
        file_path: Path,
        extensions: Optional[List[str]]
    ) -> bool:
        """Check if file should be included based on extension"""
        file_ext = file_path.suffix.lower()

        # If no extensions specified, use all supported
        if extensions is None:
            return file_ext in self.SUPPORTED_EXTENSIONS

        # Check against specified extensions
        return file_ext in extensions

    def get_language(self, file_path: str) -> Optional[str]:
        """
        Detect language from file extension.

        Args:
            file_path: Path to source file

        Returns:
            Language name or None if unsupported
        """
        ext = Path(file_path).suffix.lower()
        return self.SUPPORTED_EXTENSIONS.get(ext)

    def group_by_language(self, file_paths: List[str]) -> Dict[str, List[str]]:
        """
        Group files by programming language.

        Args:
            file_paths: List of file paths

        Returns:
            Dictionary mapping language to list of files
        """
        groups: Dict[str, List[str]] = {}

        for file_path in file_paths:
            language = self.get_language(file_path)
            if language:
                if language not in groups:
                    groups[language] = []
                groups[language].append(file_path)

        return groups


def validate_file_readable(file_path: str) -> bool:
    """
    Check if file exists and is readable.

    Args:
        file_path: Path to file

    Returns:
        True if file is readable, False otherwise
    """
    try:
        path = Path(file_path)
        return path.exists() and path.is_file() and os.access(path, os.R_OK)
    except Exception:
        return False


def validate_directory_writable(directory: str) -> bool:
    """
    Check if directory exists and is writable.

    Args:
        directory: Path to directory

    Returns:
        True if directory is writable, False otherwise
    """
    try:
        path = Path(directory)
        if not path.exists():
            return False
        return path.is_dir() and os.access(path, os.W_OK)
    except Exception:
        return False


def ensure_directory(directory: str) -> Path:
    """
    Ensure directory exists, creating it if necessary.

    Args:
        directory: Path to directory

    Returns:
        Path object for the directory

    Raises:
        OSError: If directory cannot be created
    """
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_relative_path(file_path: str, base_path: str) -> str:
    """
    Get relative path from base to file.

    Args:
        file_path: Target file path
        base_path: Base directory path

    Returns:
        Relative path string
    """
    try:
        return str(Path(file_path).relative_to(base_path))
    except ValueError:
        # If not relative, return absolute path
        return str(Path(file_path).resolve())


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def get_file_stats(file_paths: List[str]) -> Dict[str, any]:
    """
    Get statistics about a list of files.

    Args:
        file_paths: List of file paths

    Returns:
        Dictionary with file statistics
    """
    total_size = 0
    total_lines = 0

    for file_path in file_paths:
        try:
            path = Path(file_path)
            total_size += path.stat().st_size

            # Count lines
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                total_lines += sum(1 for _ in f)
        except Exception:
            continue

    return {
        'total_files': len(file_paths),
        'total_size': total_size,
        'total_size_formatted': format_file_size(total_size),
        'total_lines': total_lines,
        'avg_size': total_size // len(file_paths) if file_paths else 0,
        'avg_lines': total_lines // len(file_paths) if file_paths else 0
    }
