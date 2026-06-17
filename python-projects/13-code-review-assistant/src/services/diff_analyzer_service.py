"""
Service for analyzing code changes in diffs
"""

from typing import List, Dict, Any, Tuple, Optional
from src.utils.git_utils import DiffParser, DiffFile, DiffHunk
from src.services.code_analyzer_service import CodeAnalyzerService


class DiffAnalyzerService:
    """Service for analyzing code changes in diffs."""

    def __init__(self):
        """Initialize diff analyzer service."""
        self.code_analyzer = CodeAnalyzerService()

    def analyze_diff(
        self,
        diff_text: str,
        file_filter: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Analyze a Git diff for code quality issues.

        Args:
            diff_text: Unified diff text
            file_filter: Optional file extension filter (e.g., '.py')

        Returns:
            Tuple of (success, analysis_results, error_message)
        """
        try:
            # Parse diff
            diff_files = DiffParser.parse_diff(diff_text)

            if not diff_files:
                return True, {
                    'total_files': 0,
                    'analyzed_files': 0,
                    'total_issues': 0,
                    'files': []
                }, None

            # Filter files if needed
            if file_filter:
                diff_files = [
                    f for f in diff_files
                    if f.path and f.path.endswith(file_filter)
                ]

            # Analyze each file
            file_results = []
            total_issues = 0

            for diff_file in diff_files:
                if diff_file.is_deleted_file:
                    continue  # Skip deleted files

                # Analyze the changed code
                success, result, error = self._analyze_diff_file(diff_file)

                if success and result:
                    file_results.append(result)
                    total_issues += result.get('issues_count', 0)

            return True, {
                'total_files': len(diff_files),
                'analyzed_files': len(file_results),
                'total_issues': total_issues,
                'files': file_results
            }, None

        except Exception as e:
            return False, None, f"Failed to analyze diff: {str(e)}"

    def _analyze_diff_file(
        self,
        diff_file: DiffFile
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Analyze a single file from a diff.

        Args:
            diff_file: Parsed diff file

        Returns:
            Tuple of (success, file_result, error_message)
        """
        try:
            # Extract added/modified lines
            changed_lines = []
            line_numbers = []

            for hunk in diff_file.hunks:
                added = hunk.get_added_lines()
                for line_num, line_content in added:
                    changed_lines.append(line_content)
                    line_numbers.append(line_num)

            if not changed_lines:
                return True, {
                    'file_path': diff_file.path,
                    'issues_count': 0,
                    'issues': [],
                    'changed_lines': 0
                }, None

            # Reconstruct code snippet for analysis
            # For better context, we analyze the full hunks
            code_snippet = self._reconstruct_code_from_hunks(diff_file.hunks)

            # Analyze the code
            result = self.code_analyzer.analyze_code(
                source_code=code_snippet,
                file_path=diff_file.path
            )

            if not result['success']:
                return False, None, result.get('error', 'Analysis failed')

            # Filter issues to only those on added/modified lines
            filtered_issues = self._filter_issues_by_lines(
                result['report']['issues'],
                line_numbers
            )

            return True, {
                'file_path': diff_file.path,
                'issues_count': len(filtered_issues),
                'issues': filtered_issues,
                'changed_lines': len(changed_lines),
                'additions': diff_file.additions,
                'deletions': diff_file.deletions
            }, None

        except Exception as e:
            return False, None, f"Failed to analyze file {diff_file.path}: {str(e)}"

    def _reconstruct_code_from_hunks(self, hunks: List[DiffHunk]) -> str:
        """
        Reconstruct code from diff hunks for analysis.

        Args:
            hunks: List of diff hunks

        Returns:
            Reconstructed code string
        """
        code_lines = []

        for hunk in hunks:
            for line in hunk.lines:
                # Include context and added lines, skip removed lines
                if not line.startswith('-'):
                    # Remove diff markers
                    if line.startswith('+'):
                        code_lines.append(line[1:])
                    elif line.startswith(' '):
                        code_lines.append(line[1:])
                    else:
                        code_lines.append(line)

        return '\n'.join(code_lines)

    def _filter_issues_by_lines(
        self,
        issues: List[Dict[str, Any]],
        changed_line_numbers: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Filter issues to only those on changed lines.

        Args:
            issues: List of all issues found
            changed_line_numbers: Line numbers that were changed

        Returns:
            Filtered list of issues
        """
        filtered = []

        for issue in issues:
            line_number = issue.get('line_number')

            if line_number is None:
                # If no line number, include the issue (file-level)
                filtered.append(issue)
            elif line_number in changed_line_numbers:
                # Issue is on a changed line
                filtered.append(issue)
            else:
                # Check if issue is within a few lines of changes (context)
                # This catches issues that span multiple lines
                for changed_line in changed_line_numbers:
                    if abs(line_number - changed_line) <= 2:
                        filtered.append(issue)
                        break

        return filtered

    def analyze_pr_diff(
        self,
        diff_text: str,
        language: str = 'python'
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Analyze a pull request diff.

        Args:
            diff_text: Unified diff text from PR
            language: Programming language (default: python)

        Returns:
            Tuple of (success, analysis_results, error_message)
        """
        # Map language to file extension
        extension_map = {
            'python': '.py',
            'javascript': '.js',
            'typescript': '.ts',
            'java': '.java',
            'go': '.go',
            'rust': '.rs'
        }

        file_filter = extension_map.get(language.lower())

        return self.analyze_diff(diff_text, file_filter=file_filter)

    def get_changed_files(
        self,
        diff_text: str,
        file_filter: Optional[str] = None
    ) -> Tuple[bool, List[str], Optional[str]]:
        """
        Get list of changed files from diff.

        Args:
            diff_text: Unified diff text
            file_filter: Optional file extension filter

        Returns:
            Tuple of (success, file_paths, error_message)
        """
        try:
            diff_files = DiffParser.parse_diff(diff_text)

            file_paths = [
                f.path for f in diff_files
                if f.path and not f.is_deleted_file
            ]

            if file_filter:
                file_paths = [
                    p for p in file_paths
                    if p.endswith(file_filter)
                ]

            return True, file_paths, None

        except Exception as e:
            return False, [], f"Failed to get changed files: {str(e)}"

    def get_diff_stats(self, diff_text: str) -> Dict[str, Any]:
        """
        Get statistics about a diff.

        Args:
            diff_text: Unified diff text

        Returns:
            Dictionary with diff statistics
        """
        try:
            diff_files = DiffParser.parse_diff(diff_text)

            total_additions = sum(f.additions for f in diff_files)
            total_deletions = sum(f.deletions for f in diff_files)

            return {
                'files_changed': len(diff_files),
                'additions': total_additions,
                'deletions': total_deletions,
                'files': [
                    {
                        'path': f.path,
                        'additions': f.additions,
                        'deletions': f.deletions,
                        'is_new': f.is_new_file,
                        'is_deleted': f.is_deleted_file,
                        'is_renamed': f.is_renamed_file
                    }
                    for f in diff_files
                ]
            }

        except Exception as e:
            return {
                'error': str(e),
                'files_changed': 0,
                'additions': 0,
                'deletions': 0,
                'files': []
            }
