#!/usr/bin/env python3
"""
AI Code Review Assistant - Command Line Interface

A CLI tool for running code analysis locally or in CI/CD pipelines.
Supports multiple output formats, severity thresholds, and quality gates.
"""

import argparse
import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parsers import get_registry
from src.analyzers.security_analyzer import SecurityAnalyzer
from src.analyzers.smell_analyzer import SmellAnalyzer
from src.analyzers.complexity_analyzer import ComplexityAnalyzer


class CodeReviewCLI:
    """Command-line interface for code review"""

    def __init__(self):
        self.registry = get_registry()
        self.analyzers = {
            'security': SecurityAnalyzer(),
            'smell': SmellAnalyzer(),
            'complexity': ComplexityAnalyzer()
        }
        self.results = []
        self.summary = {
            'total_files': 0,
            'total_issues': 0,
            'by_severity': {'critical': 0, 'error': 0, 'warning': 0, 'info': 0},
            'by_category': {}
        }

    def analyze_path(
        self,
        path: str,
        language: Optional[str] = None,
        categories: Optional[List[str]] = None,
        severity_threshold: str = 'info',
        exclude_patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze code at given path

        Args:
            path: Directory or file path to analyze
            language: Filter by language (python, javascript, java, go, rust)
            categories: Filter by categories (security, smell, complexity)
            severity_threshold: Minimum severity to report
            exclude_patterns: Patterns to exclude (glob)

        Returns:
            Analysis results dictionary
        """
        path_obj = Path(path)

        if path_obj.is_file():
            files = [path_obj]
        else:
            files = self._discover_files(path_obj, language, exclude_patterns)

        print(f"📁 Analyzing {len(files)} files...")

        for file_path in files:
            self._analyze_file(file_path, categories, severity_threshold)

        return {
            'summary': self.summary,
            'results': self.results,
            'analyzed_at': datetime.now().isoformat(),
            'path': str(path),
            'threshold': severity_threshold
        }

    def _discover_files(
        self,
        path: Path,
        language: Optional[str] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> List[Path]:
        """Discover code files in directory"""
        extensions = {
            'python': ['.py', '.pyw'],
            'javascript': ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'],
            'java': ['.java'],
            'go': ['.go'],
            'rust': ['.rs']
        }

        if language:
            allowed_exts = extensions.get(language, [])
        else:
            allowed_exts = [ext for exts in extensions.values() for ext in exts]

        files = []
        exclude_patterns = exclude_patterns or ['node_modules', '.git', '__pycache__', 'venv', '.venv']

        for file_path in path.rglob('*'):
            if file_path.is_file() and file_path.suffix in allowed_exts:
                # Check exclude patterns
                if any(pattern in str(file_path) for pattern in exclude_patterns):
                    continue
                files.append(file_path)

        return files

    def _analyze_file(
        self,
        file_path: Path,
        categories: Optional[List[str]] = None,
        severity_threshold: str = 'info'
    ):
        """Analyze a single file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            # Detect language
            detected_lang = self.registry.detect_language(str(file_path))
            if not detected_lang:
                detected_lang = self.registry.detect_language_from_content(code)

            if not detected_lang:
                return

            # Parse file
            parsed = self.registry.parse_file(str(file_path))
            if not parsed:
                return

            self.summary['total_files'] += 1

            # Run analyzers
            issues = []
            for category, analyzer in self.analyzers.items():
                if categories and category not in categories:
                    continue

                try:
                    analyzer_issues = analyzer.analyze(code, file_path=str(file_path))
                    issues.extend(analyzer_issues)
                except Exception as e:
                    print(f"⚠️  Error analyzing {file_path}: {e}")

            # Filter by severity
            severity_order = {'info': 0, 'warning': 1, 'error': 2, 'critical': 3}
            threshold_level = severity_order.get(severity_threshold, 0)

            filtered_issues = [
                issue for issue in issues
                if severity_order.get(issue.get('severity', 'info'), 0) >= threshold_level
            ]

            # Update summary
            for issue in filtered_issues:
                severity = issue.get('severity', 'info')
                category = issue.get('category', 'other')

                self.summary['by_severity'][severity] = self.summary['by_severity'].get(severity, 0) + 1
                self.summary['by_category'][category] = self.summary['by_category'].get(category, 0) + 1
                self.summary['total_issues'] += 1

            if filtered_issues:
                self.results.append({
                    'file': str(file_path),
                    'language': detected_lang,
                    'issues': filtered_issues,
                    'issue_count': len(filtered_issues)
                })

                # Print file summary
                critical = sum(1 for i in filtered_issues if i.get('severity') == 'critical')
                errors = sum(1 for i in filtered_issues if i.get('severity') == 'error')
                warnings = sum(1 for i in filtered_issues if i.get('severity') == 'warning')

                status = "❌" if critical > 0 or errors > 0 else "⚠️ " if warnings > 0 else "✅"
                print(f"{status} {file_path.name}: {len(filtered_issues)} issues "
                      f"(🔴 {critical} critical, ⛔ {errors} errors, ⚠️  {warnings} warnings)")

        except Exception as e:
            print(f"⚠️  Error processing {file_path}: {e}")

    def generate_report(
        self,
        format: str = 'text',
        output_file: Optional[str] = None
    ) -> str:
        """Generate analysis report in various formats"""
        if format == 'json':
            report = json.dumps({
                'summary': self.summary,
                'results': self.results
            }, indent=2)

        elif format == 'markdown':
            report = self._generate_markdown_report()

        elif format == 'html':
            report = self._generate_html_report()

        else:  # text
            report = self._generate_text_report()

        if output_file:
            Path(output_file).write_text(report, encoding='utf-8')
            print(f"📄 Report saved to {output_file}")

        return report

    def _generate_text_report(self) -> str:
        """Generate plain text report"""
        lines = []
        lines.append("=" * 80)
        lines.append("AI CODE REVIEW REPORT")
        lines.append("=" * 80)
        lines.append("")

        # Summary
        lines.append(f"Files Analyzed: {self.summary['total_files']}")
        lines.append(f"Total Issues: {self.summary['total_issues']}")
        lines.append("")

        # Severity breakdown
        lines.append("Issues by Severity:")
        for severity, count in self.summary['by_severity'].items():
            if count > 0:
                lines.append(f"  {severity.upper():10} {count}")
        lines.append("")

        # Category breakdown
        if self.summary['by_category']:
            lines.append("Issues by Category:")
            for category, count in sorted(self.summary['by_category'].items()):
                lines.append(f"  {category:15} {count}")
            lines.append("")

        # Files with issues
        if self.results:
            lines.append("Files with Issues:")
            lines.append("-" * 80)
            for result in self.results:
                lines.append(f"\n{result['file']} ({result['language']})")
                lines.append(f"  {result['issue_count']} issues found")

                for issue in result['issues'][:5]:  # Show first 5 issues
                    lines.append(f"  [{issue['severity'].upper()}] Line {issue.get('line_number', '?')}: {issue['title']}")

                if result['issue_count'] > 5:
                    lines.append(f"  ... and {result['issue_count'] - 5} more issues")

        return "\n".join(lines)

    def _generate_markdown_report(self) -> str:
        """Generate markdown report"""
        lines = []
        lines.append("# 🔍 AI Code Review Report")
        lines.append("")

        # Summary stats
        lines.append("## 📊 Summary")
        lines.append("")
        lines.append(f"- **Files Analyzed:** {self.summary['total_files']}")
        lines.append(f"- **Total Issues:** {self.summary['total_issues']}")
        lines.append("")

        # Severity table
        lines.append("### Issues by Severity")
        lines.append("")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        for severity in ['critical', 'error', 'warning', 'info']:
            count = self.summary['by_severity'].get(severity, 0)
            emoji = {'critical': '🔴', 'error': '⛔', 'warning': '⚠️', 'info': 'ℹ️'}
            lines.append(f"| {emoji[severity]} {severity.upper()} | {count} |")
        lines.append("")

        # Issues by category
        if self.summary['by_category']:
            lines.append("### Issues by Category")
            lines.append("")
            lines.append("| Category | Count |")
            lines.append("|----------|-------|")
            for category, count in sorted(self.summary['by_category'].items()):
                lines.append(f"| {category} | {count} |")
            lines.append("")

        # Detailed issues
        if self.results:
            lines.append("## 📝 Detailed Results")
            lines.append("")

            for result in self.results[:10]:  # Top 10 files
                lines.append(f"### `{result['file']}`")
                lines.append("")
                lines.append(f"**Language:** {result['language']} | **Issues:** {result['issue_count']}")
                lines.append("")

                for issue in result['issues'][:3]:  # Top 3 issues per file
                    severity_emoji = {'critical': '🔴', 'error': '⛔', 'warning': '⚠️', 'info': 'ℹ️'}
                    emoji = severity_emoji.get(issue['severity'], 'ℹ️')
                    lines.append(f"- {emoji} **Line {issue.get('line_number', '?')}:** {issue['title']}")
                    if issue.get('description'):
                        lines.append(f"  - {issue['description']}")

                lines.append("")

        return "\n".join(lines)

    def _generate_html_report(self) -> str:
        """Generate HTML report"""
        # Simple HTML report
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Code Review Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .summary {{ background: #f5f5f5; padding: 20px; border-radius: 8px; }}
        .issue {{ margin: 10px 0; padding: 10px; border-left: 4px solid #ccc; }}
        .critical {{ border-left-color: #dc3545; }}
        .error {{ border-left-color: #fd7e14; }}
        .warning {{ border-left-color: #ffc107; }}
        .info {{ border-left-color: #17a2b8; }}
    </style>
</head>
<body>
    <h1>🔍 AI Code Review Report</h1>
    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Files Analyzed:</strong> {self.summary['total_files']}</p>
        <p><strong>Total Issues:</strong> {self.summary['total_issues']}</p>
    </div>
    <h2>Issues by Severity</h2>
    <ul>
        {"".join(f"<li>{sev.upper()}: {count}</li>" for sev, count in self.summary['by_severity'].items() if count > 0)}
    </ul>
</body>
</html>"""
        return html

    def check_quality_gate(
        self,
        max_critical: int = 0,
        max_error: int = 5,
        max_warning: int = 20,
        max_total: int = 50
    ) -> bool:
        """
        Check if code passes quality gate

        Returns:
            True if passed, False if failed
        """
        critical = self.summary['by_severity'].get('critical', 0)
        error = self.summary['by_severity'].get('error', 0)
        warning = self.summary['by_severity'].get('warning', 0)
        total = self.summary['total_issues']

        passed = True
        if critical > max_critical:
            print(f"❌ Quality gate failed: {critical} critical issues (max: {max_critical})")
            passed = False

        if error > max_error:
            print(f"❌ Quality gate failed: {error} errors (max: {max_error})")
            passed = False

        if warning > max_warning:
            print(f"❌ Quality gate failed: {warning} warnings (max: {max_warning})")
            passed = False

        if total > max_total:
            print(f"❌ Quality gate failed: {total} total issues (max: {max_total})")
            passed = False

        if passed:
            print("✅ Quality gate passed!")

        return passed


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='AI Code Review Assistant - CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze code')
    analyze_parser.add_argument('--path', default='.', help='Path to analyze')
    analyze_parser.add_argument('--language', choices=['python', 'javascript', 'java', 'go', 'rust'],
                                help='Filter by language')
    analyze_parser.add_argument('--categories', nargs='+',
                                choices=['security', 'smell', 'complexity'],
                                help='Categories to analyze')
    analyze_parser.add_argument('--severity-threshold',
                                choices=['info', 'warning', 'error', 'critical'],
                                default='info',
                                help='Minimum severity to report')
    analyze_parser.add_argument('--output-format', choices=['text', 'json', 'markdown', 'html'],
                                default='text', help='Output format')
    analyze_parser.add_argument('--output-file', help='Output file path')
    analyze_parser.add_argument('--exit-on-threshold', action='store_true',
                                help='Exit with error code if issues found')
    analyze_parser.add_argument('--max-issues', type=int, default=50,
                                help='Maximum issues before failing')

    # Report command
    report_parser = subparsers.add_parser('report', help='Generate report from results')
    report_parser.add_argument('--input', required=True, help='Input JSON results file')
    report_parser.add_argument('--format', choices=['text', 'json', 'markdown', 'html'],
                              default='markdown', help='Report format')
    report_parser.add_argument('--output', help='Output file')

    # Quality gate command
    gate_parser = subparsers.add_parser('quality-gate', help='Check quality gate')
    gate_parser.add_argument('--results', required=True, help='Results JSON file')
    gate_parser.add_argument('--max-critical', type=int, default=0)
    gate_parser.add_argument('--max-error', type=int, default=5)
    gate_parser.add_argument('--max-warning', type=int, default=20)
    gate_parser.add_argument('--max-total', type=int, default=50)

    # Badge command
    badge_parser = subparsers.add_parser('badge', help='Generate quality badge')
    badge_parser.add_argument('--results', required=True, help='Results JSON file')
    badge_parser.add_argument('--output-file', default='badge.svg', help='Output SVG file')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    cli = CodeReviewCLI()

    # Analyze command
    if args.command == 'analyze':
        results = cli.analyze_path(
            path=args.path,
            language=args.language,
            categories=args.categories,
            severity_threshold=args.severity_threshold
        )

        # Generate report
        report = cli.generate_report(
            format=args.output_format,
            output_file=args.output_file
        )

        if args.output_format == 'text':
            print(report)

        # Check if should exit on threshold
        if args.exit_on_threshold:
            total_issues = cli.summary['total_issues']
            critical = cli.summary['by_severity'].get('critical', 0)
            errors = cli.summary['by_severity'].get('error', 0)

            if critical > 0 or errors > 0 or total_issues > args.max_issues:
                print(f"\n❌ Analysis failed: {critical} critical, {errors} errors, {total_issues} total issues")
                return 1

        print("\n✅ Analysis complete!")
        return 0

    # Report command
    elif args.command == 'report':
        with open(args.input, 'r') as f:
            data = json.load(f)

        cli.summary = data.get('summary', {})
        cli.results = data.get('results', [])

        report = cli.generate_report(format=args.format, output_file=args.output)

        if not args.output:
            print(report)

        return 0

    # Quality gate command
    elif args.command == 'quality-gate':
        with open(args.results, 'r') as f:
            data = json.load(f)

        cli.summary = data.get('summary', {})

        passed = cli.check_quality_gate(
            max_critical=args.max_critical,
            max_error=args.max_error,
            max_warning=args.max_warning,
            max_total=args.max_total
        )

        return 0 if passed else 1

    # Badge command
    elif args.command == 'badge':
        with open(args.results, 'r') as f:
            data = json.load(f)

        total_issues = data.get('summary', {}).get('total_issues', 0)
        critical = data.get('summary', {}).get('by_severity', {}).get('critical', 0)

        # Determine color and label
        if critical > 0:
            color = 'red'
            label = 'failing'
        elif total_issues > 20:
            color = 'orange'
            label = 'poor'
        elif total_issues > 5:
            color = 'yellow'
            label = 'fair'
        else:
            color = 'brightgreen'
            label = 'passing'

        # Simple SVG badge
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="20">
    <linearGradient id="b" x2="0" y2="100%">
        <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
        <stop offset="1" stop-opacity=".1"/>
    </linearGradient>
    <rect rx="3" width="120" height="20" fill="#555"/>
    <rect rx="3" x="65" width="55" height="20" fill="{color}"/>
    <path fill="{color}" d="M65 0h4v20h-4z"/>
    <rect rx="3" width="120" height="20" fill="url(#b)"/>
    <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
        <text x="33" y="15" fill="#010101" fill-opacity=".3">quality</text>
        <text x="33" y="14">quality</text>
        <text x="91.5" y="15" fill="#010101" fill-opacity=".3">{label}</text>
        <text x="91.5" y="14">{label}</text>
    </g>
</svg>'''

        Path(args.output_file).write_text(svg)
        print(f"✅ Badge generated: {args.output_file}")

        return 0


if __name__ == '__main__':
    sys.exit(main())
