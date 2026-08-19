"""Service for orchestrating code analysis"""
from typing import List, Dict, Any, Optional
from pathlib import Path
from src.parsers.parser_registry import get_registry as get_parser_registry
from src.analyzers import get_registry
from src.analyzers.base_analyzer import CodeIssue


class CodeAnalyzerService:
    """Orchestrates parser and analyzers to analyze code files.

    Used to hardcode a Python-only parser regardless of the file's real
    language - analyzing a JavaScript/Java/Go/Rust file meant parsing it
    as Python, which fails immediately with a syntax error, silently
    caught and reported as "0 issues found" rather than an error. Now
    detects the language and uses the matching parser (ParserRegistry)
    and analyzer set (AnalyzerRegistry.LANGUAGE_ANALYZER_IDS) for it."""

    def __init__(self):
        """Initialize service with parser and analyzer registries"""
        self.parser_registry = get_parser_registry()
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
        analyzer_ids: Optional[List[str]] = None,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze source code in any supported language (Python, JavaScript/
        TypeScript, Java - see AnalyzerRegistry.LANGUAGE_ANALYZER_IDS for
        what's currently backed by a real analyzer).

        Args:
            source_code: Source code to analyze
            file_path: Path or identifier for the code - also used to
                detect the language by extension when `language` isn't
                given explicitly
            analyzer_ids: Optional list of specific analyzer IDs to run -
                overrides language-based selection entirely
            language: Optional explicit language ('python', 'javascript',
                'java', ...). If omitted, detected from file_path's
                extension, falling back to content-based detection.

        Returns:
            Dictionary with analysis results
        """
        try:
            if not language:
                language = self.parser_registry.detect_language(file_path, content=source_code)

            if not language:
                return {
                    'success': False,
                    'error': f'Could not detect a supported language for {file_path}',
                    'file_path': file_path
                }

            # Parse the code with the language-appropriate parser
            parsed = self.parser_registry.parse_code(source_code, language, file_path)

            # Run analysis with the language-appropriate analyzers
            issues = self.registry.analyze(parsed, source_code, analyzer_ids, language=language)

            # Calculate health score
            health_score = self.registry.calculate_health_score(issues)

            # Generate report
            report = self._generate_report(
                file_path=file_path,
                issues=issues,
                health_score=health_score,
                source_code=source_code,
                language=language
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
        Analyze multiple files (any supported language, auto-detected
        per-file from its extension).

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
                language = self.parser_registry.detect_language(file_path, content=source_code)
                if not language:
                    results.append({
                        'success': False,
                        'error': f'Could not detect a supported language for {file_path}',
                        'file_path': file_path
                    })
                    continue

                parsed = self.parser_registry.parse_code(source_code, language, file_path)

                # Get CodeIssue objects for aggregation
                issues = self.registry.analyze(parsed, source_code, analyzer_ids, language=language)
                all_issues.extend(issues)

                # Generate report
                health_score = self.registry.calculate_health_score(issues)
                report = self._generate_report(file_path, issues, health_score, source_code, language=language)

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
        source_code: str,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate analysis report.

        Args:
            file_path: File path
            issues: List of detected issues
            health_score: Health score data
            source_code: Original source code
            language: Detected/specified language, if known

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
            'language': language,
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
