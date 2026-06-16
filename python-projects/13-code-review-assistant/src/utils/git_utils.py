"""
Git utilities for diff parsing and analysis
"""

from typing import List, Dict, Any, Optional, Tuple
import re
from dataclasses import dataclass, field


@dataclass
class DiffHunk:
    """Represents a single hunk (change block) in a diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str] = field(default_factory=list)

    def get_added_lines(self) -> List[Tuple[int, str]]:
        """Get lines that were added (line_number, content)."""
        added = []
        new_line_num = self.new_start

        for line in self.lines:
            if line.startswith('+') and not line.startswith('+++'):
                added.append((new_line_num, line[1:]))
                new_line_num += 1
            elif not line.startswith('-'):
                new_line_num += 1

        return added

    def get_removed_lines(self) -> List[Tuple[int, str]]:
        """Get lines that were removed (line_number, content)."""
        removed = []
        old_line_num = self.old_start

        for line in self.lines:
            if line.startswith('-') and not line.startswith('---'):
                removed.append((old_line_num, line[1:]))
                old_line_num += 1
            elif not line.startswith('+'):
                old_line_num += 1

        return removed

    def get_modified_line_numbers(self) -> List[int]:
        """Get line numbers that were modified (in new file)."""
        modified = []
        new_line_num = self.new_start

        for line in self.lines:
            if line.startswith('+') and not line.startswith('+++'):
                modified.append(new_line_num)
                new_line_num += 1
            elif not line.startswith('-'):
                new_line_num += 1

        return modified


@dataclass
class DiffFile:
    """Represents a single file in a diff."""
    old_path: Optional[str]
    new_path: Optional[str]
    is_new_file: bool = False
    is_deleted_file: bool = False
    is_renamed: bool = False
    hunks: List[DiffHunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        """Get the current path of the file."""
        return self.new_path or self.old_path or ""

    def get_all_modified_lines(self) -> List[int]:
        """Get all line numbers that were modified across all hunks."""
        modified = []
        for hunk in self.hunks:
            modified.extend(hunk.get_modified_line_numbers())
        return sorted(set(modified))

    def is_line_modified(self, line_number: int) -> bool:
        """Check if a specific line was modified."""
        return line_number in self.get_all_modified_lines()

    def get_added_lines_count(self) -> int:
        """Get total count of added lines."""
        count = 0
        for hunk in self.hunks:
            count += len(hunk.get_added_lines())
        return count

    def get_removed_lines_count(self) -> int:
        """Get total count of removed lines."""
        count = 0
        for hunk in self.hunks:
            count += len(hunk.get_removed_lines())
        return count


class DiffParser:
    """Parser for Git unified diffs."""

    # Regex patterns for diff parsing
    FILE_HEADER_PATTERN = re.compile(r'^diff --git a/(.*?) b/(.*?)$')
    OLD_FILE_PATTERN = re.compile(r'^--- a/(.*?)$|^--- /dev/null$')
    NEW_FILE_PATTERN = re.compile(r'^\+\+\+ b/(.*?)$|^\+\+\+ /dev/null$')
    HUNK_HEADER_PATTERN = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
    NEW_FILE_MODE_PATTERN = re.compile(r'^new file mode')
    DELETED_FILE_MODE_PATTERN = re.compile(r'^deleted file mode')
    RENAME_FROM_PATTERN = re.compile(r'^rename from (.*?)$')
    RENAME_TO_PATTERN = re.compile(r'^rename to (.*?)$')

    @classmethod
    def parse_diff(cls, diff_text: str) -> List[DiffFile]:
        """
        Parse a unified diff into structured data.

        Args:
            diff_text: Git diff output (unified format)

        Returns:
            List of DiffFile objects
        """
        if not diff_text or not diff_text.strip():
            return []

        lines = diff_text.split('\n')
        files = []
        current_file = None
        current_hunk = None

        i = 0
        while i < len(lines):
            line = lines[i]

            # Start of new file
            if cls.FILE_HEADER_PATTERN.match(line):
                # Save current hunk to current file before moving to next file
                if current_hunk and current_file:
                    current_file.hunks.append(current_hunk)
                # Save current file to files list
                if current_file:
                    files.append(current_file)

                match = cls.FILE_HEADER_PATTERN.match(line)
                current_file = DiffFile(
                    old_path=match.group(1),
                    new_path=match.group(2)
                )
                current_hunk = None

            # New file mode
            elif cls.NEW_FILE_MODE_PATTERN.match(line):
                if current_file:
                    current_file.is_new_file = True

            # Deleted file mode
            elif cls.DELETED_FILE_MODE_PATTERN.match(line):
                if current_file:
                    current_file.is_deleted_file = True

            # Rename detection
            elif cls.RENAME_FROM_PATTERN.match(line):
                if current_file:
                    match = cls.RENAME_FROM_PATTERN.match(line)
                    current_file.old_path = match.group(1)
                    current_file.is_renamed = True

            elif cls.RENAME_TO_PATTERN.match(line):
                if current_file:
                    match = cls.RENAME_TO_PATTERN.match(line)
                    current_file.new_path = match.group(1)
                    current_file.is_renamed = True

            # Old file path
            elif cls.OLD_FILE_PATTERN.match(line):
                if current_file:
                    match = cls.OLD_FILE_PATTERN.match(line)
                    if '/dev/null' not in line:
                        # Extract path from "--- a/path"
                        current_file.old_path = line[6:]  # Skip "--- a/"

            # New file path
            elif cls.NEW_FILE_PATTERN.match(line):
                if current_file:
                    match = cls.NEW_FILE_PATTERN.match(line)
                    if '/dev/null' not in line:
                        # Extract path from "+++ b/path"
                        current_file.new_path = line[6:]  # Skip "+++ b/"

            # Hunk header
            elif cls.HUNK_HEADER_PATTERN.match(line):
                if current_hunk and current_file:
                    current_file.hunks.append(current_hunk)

                match = cls.HUNK_HEADER_PATTERN.match(line)
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1

                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count
                )

            # Hunk content
            elif current_hunk and (line.startswith('+') or line.startswith('-') or line.startswith(' ')):
                current_hunk.lines.append(line)

            i += 1

        # Add last hunk and file
        if current_hunk and current_file:
            current_file.hunks.append(current_hunk)
        if current_file:
            files.append(current_file)

        return files

    @classmethod
    def get_changed_files(cls, diff_text: str) -> List[str]:
        """
        Get list of changed file paths from a diff.

        Args:
            diff_text: Git diff output

        Returns:
            List of file paths
        """
        files = cls.parse_diff(diff_text)
        return [f.path for f in files if f.path]

    @classmethod
    def get_file_stats(cls, diff_text: str) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for each changed file.

        Args:
            diff_text: Git diff output

        Returns:
            Dictionary mapping file paths to stats:
            {
                'path/to/file.py': {
                    'added': 10,
                    'removed': 5,
                    'is_new': False,
                    'is_deleted': False,
                    'is_renamed': False
                }
            }
        """
        files = cls.parse_diff(diff_text)
        stats = {}

        for file in files:
            if file.path:
                stats[file.path] = {
                    'added': file.get_added_lines_count(),
                    'removed': file.get_removed_lines_count(),
                    'is_new': file.is_new_file,
                    'is_deleted': file.is_deleted_file,
                    'is_renamed': file.is_renamed,
                    'old_path': file.old_path,
                    'new_path': file.new_path
                }

        return stats

    @classmethod
    def filter_by_extension(cls, diff_text: str, extensions: List[str]) -> List[DiffFile]:
        """
        Filter diff files by file extension.

        Args:
            diff_text: Git diff output
            extensions: List of extensions to include (e.g., ['.py', '.js'])

        Returns:
            List of DiffFile objects matching the extensions
        """
        files = cls.parse_diff(diff_text)
        return [
            f for f in files
            if f.path and any(f.path.endswith(ext) for ext in extensions)
        ]


def analyze_diff_complexity(diff_text: str) -> Dict[str, Any]:
    """
    Analyze the complexity of changes in a diff.

    Args:
        diff_text: Git diff output

    Returns:
        Dictionary with complexity metrics:
        {
            'total_files': int,
            'total_added': int,
            'total_removed': int,
            'total_modified': int,
            'largest_file_changes': str,
            'complexity_score': float  # 0-100
        }
    """
    files = DiffParser.parse_diff(diff_text)

    if not files:
        return {
            'total_files': 0,
            'total_added': 0,
            'total_removed': 0,
            'total_modified': 0,
            'largest_file_changes': None,
            'complexity_score': 0.0
        }

    total_added = sum(f.get_added_lines_count() for f in files)
    total_removed = sum(f.get_removed_lines_count() for f in files)
    total_modified = total_added + total_removed

    # Find file with most changes
    largest_file = max(files, key=lambda f: f.get_added_lines_count() + f.get_removed_lines_count())

    # Calculate complexity score (0-100)
    # Based on: number of files, total changes, and concentration
    file_count_score = min(len(files) * 5, 30)  # Max 30 points for file count
    change_size_score = min(total_modified / 10, 50)  # Max 50 points for change size

    # Concentration: if changes are spread across many files, add points
    avg_changes_per_file = total_modified / len(files) if files else 0
    concentration_score = min(20, 20 * (1 - (avg_changes_per_file / total_modified if total_modified else 0)))

    complexity_score = min(100, file_count_score + change_size_score + concentration_score)

    return {
        'total_files': len(files),
        'total_added': total_added,
        'total_removed': total_removed,
        'total_modified': total_modified,
        'largest_file_changes': largest_file.path,
        'complexity_score': round(complexity_score, 2)
    }
