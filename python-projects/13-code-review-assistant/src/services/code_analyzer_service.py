"""Service for orchestrating code analysis"""
from typing import List, Dict, Any, Optional
from pathlib import Path
from src.parsers.python_parser import PythonParser
from src.analyzers import get_registry
from src.analyzers.base_analyzer import CodeIssue


class CodeAnalyzerService:
    """Orchestrates parser and analyzers to analyze code files"""

    def __init__(self):
        """Initialize service with parser and analyzer registry"""
        self.parser = PythonParser()
        self.registry = get_registry()

    def analyze_file(
        self,
        file_path: str,
        analyzer_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze a single Python file.

        Args:
            file_path: Path to Python file to analyze
            analyzer_ids: Optional list of specific analyzer IDs to run

        Returns:
            Dictionary with analysis results
        """
        # Read the file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to read file: {str(e)}',
                'file_path': file_path
            }

        return self.analyze_code(source_code, file_path, analyzer_ids)

    def analyze_code(
        self,
        source_code: str,
        file_path: str = '<string>',
        analyzer_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze Python source code.

        Args:
            source_code: Python source code to analyze
            file_path: Path or identifier for the code
            analyzer_ids: Optional list of specific analyzer IDs to run

        Returns:
            Dictionary with analysis results
        """
        try:
            # Parse the code
            parsed = self.parser.parse_code(source_code)
            parsed.file_path = file_path

            # Run analysis
            issues = self.registry.analyze(parsed, source_code, analyzer_ids)

            # Calculate health score
            health_score = self.registry.calculate_health_score(issues)

            # Generate report
            report = self._generate_report(
                file_path=file_path,
                issues=issues,
                health_score=health_score,
                source_code=source_code
            )

            return {
                'success': True,
                'file_path': file_path,
                'report': report
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Analysis failed: {str(e)}',
                'file_path': file_path
            }

    def analyze_multiple_files(
        self,
        file_paths: List[str],
        analyzer_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze multiple Python files.

        Args:
            file_paths: List of file paths to analyze
            analyzer_ids: Optional list of specific analyzer IDs to run

        Returns:
            Dictionary with aggregated results
        """
        results = []
        all_issues = []

        for file_path in file_paths:
            # Read file
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source_code = f.read()
            except Exception as e:
                results.append({
                    'success': False,
                    'error': f'Failed to read file: {str(e)}',
                    'file_path': file_path
                })
                continue

            # Parse and analyze
            try:
                parsed = self.parser.parse_code(source_code)
                parsed.file_path = file_path

                # Get CodeIssue objects for aggregation
                issues = self.registry.analyze(parsed, source_code, analyzer_ids)
                all_issues.extend(issues)

                # Generate report
                health_score = self.registry.calculate_health_score(issues)
                report = self._generate_report(file_path, issues, health_score, source_code)

                results.append({
                    'success': True,
                    'file_path': file_path,
                    'report': report
                })

            except Exception as e:
                results.append({
                    'success': False,
                    'error': f'Analysis failed: {str(e)}',
                    'file_path': file_path
                })

        # Calculate overall health score
        overall_health = self.registry.calculate_health_score(all_issues)

        return {
            'success': True,
            'files_analyzed': len(file_paths),
            'files_with_issues': sum(1 for r in results if r.get('success') and r['report']['total_issues'] > 0),
            'total_issues': len(all_issues),
            'overall_health': overall_health,
            'files': results
        }

    def _generate_report(
        self,
        file_path: str,
        issues: List[CodeIssue],
        health_score: Dict[str, Any],
        source_code: str
    ) -> Dict[str, Any]:
        """
        Generate analysis report.

        Args:
            file_path: File path
            issues: List of detected issues
            health_score: Health score data
            source_code: Original source code

        Returns:
            Report dictionary
        """
        # Group issues by category and severity
        by_category = {}
        by_severity = {}
        by_rule = {}

        for issue in issues:
            # By category
            cat = issue.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(issue.to_dict())

            # By severity
            sev = issue.severity.value
            if sev not in by_severity:
                by_severity[sev] = []
            by_severity[sev].append(issue.to_dict())

            # By rule
            rule = issue.rule_id
            if rule not in by_rule:
                by_rule[rule] = []
            by_rule[rule].append(issue.to_dict())

        # Get source stats
        lines = source_code.split('\n')
        stats = {
            'total_lines': len(lines),
            'blank_lines': sum(1 for line in lines if not line.strip()),
            'comment_lines': sum(1 for line in lines if line.strip().startswith('#')),
        }
        stats['code_lines'] = stats['total_lines'] - stats['blank_lines'] - stats['comment_lines']

        return {
            'file_path': file_path,
            'total_issues': len(issues),
            'issues': [issue.to_dict() for issue in issues],
            'by_category': by_category,
            'by_severity': by_severity,
            'by_rule': by_rule,
            'health_score': health_score,
            'stats': stats,
            'summary': self._generate_summary(issues, health_score)
        }

    def _generate_summary(
        self,
        issues: List[CodeIssue],
        health_score: Dict[str, Any]
    ) -> str:
        """Generate human-readable summary"""
        if not issues:
            return "No issues found. Code looks good!"

        total = len(issues)
        critical = sum(1 for i in issues if i.severity.value == 'critical')
        errors = sum(1 for i in issues if i.severity.value == 'error')
        warnings = sum(1 for i in issues if i.severity.value == 'warning')

        parts = [f"Found {total} issue{'s' if total != 1 else ''}."]

        if critical > 0:
            parts.append(f"{critical} critical")
        if errors > 0:
            parts.append(f"{errors} error{'s' if errors != 1 else ''}")
        if warnings > 0:
            parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")

        severity_summary = ", ".join(parts[1:]) if len(parts) > 1 else ""
        if severity_summary:
            parts[0] += f" ({severity_summary})"

        parts.append(f"Health score: {health_score['overall_score']}/100 ({health_score['grade']})")

        return " ".join(parts)
