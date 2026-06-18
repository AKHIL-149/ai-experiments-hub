"""
Enhanced Analyzer

Integrates AI capabilities with traditional code analysis to provide:
- AI explanations for detected issues
- Fix suggestions for common problems
- Refactoring recommendations
- Enriched analysis results
"""

from typing import Dict, Any, Optional, List
from .code_analyzer_service import CodeAnalyzerService
from .ai_analysis_service import AIAnalysisService


class EnhancedAnalyzer:
    """Enhanced analyzer with AI capabilities."""

    def __init__(
        self,
        enable_ai: bool = True,
        llm_backend: str = "ollama",
        model: Optional[str] = None
    ):
        """
        Initialize enhanced analyzer.

        Args:
            enable_ai: Whether to enable AI enhancements
            llm_backend: LLM backend to use (ollama/anthropic/openai)
            model: Optional model name
        """
        self.code_analyzer = CodeAnalyzerService()
        self.enable_ai = enable_ai

        if enable_ai:
            self.ai_service = AIAnalysisService(
                llm_backend=llm_backend,
                model=model
            )
        else:
            self.ai_service = None

    def analyze_code(
        self,
        code: str,
        file_path: str,
        language: str = "python",
        enable_fixes: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze code with AI enhancement.

        Args:
            code: Source code to analyze
            file_path: File path for context
            language: Programming language
            enable_fixes: Whether to generate fix suggestions

        Returns:
            Enhanced analysis results with AI explanations
        """
        # Run traditional analysis
        results = self.code_analyzer.analyze_code(code, language)

        # Enhance with AI if enabled
        if self.enable_ai and self.ai_service:
            results = self._enhance_results(
                results,
                code,
                file_path,
                language,
                enable_fixes
            )

        return results

    def analyze_file(
        self,
        file_path: str,
        enable_fixes: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze file with AI enhancement.

        Args:
            file_path: Path to file
            enable_fixes: Whether to generate fix suggestions

        Returns:
            Enhanced analysis results
        """
        # Run traditional analysis
        results = self.code_analyzer.analyze_file(file_path)

        # Get code content for AI enhancement
        if self.enable_ai and self.ai_service and results.get('issues'):
            try:
                with open(file_path, 'r') as f:
                    code = f.read()

                results = self._enhance_results(
                    results,
                    code,
                    file_path,
                    results.get('language', 'python'),
                    enable_fixes
                )
            except Exception as e:
                results['ai_enhancement_error'] = str(e)

        return results

    def _enhance_results(
        self,
        results: Dict[str, Any],
        code: str,
        file_path: str,
        language: str,
        enable_fixes: bool
    ) -> Dict[str, Any]:
        """
        Enhance analysis results with AI.

        Args:
            results: Original analysis results
            code: Source code
            file_path: File path
            language: Programming language
            enable_fixes: Whether to generate fixes

        Returns:
            Enhanced results
        """
        enhanced_results = results.copy()
        enhanced_results['ai_enhanced'] = True
        enhanced_results['ai_issues_enhanced'] = 0

        # Enhance each issue
        enhanced_issues = []
        for issue in results.get('issues', []):
            # Extract code snippet
            line_number = issue.get('line_number', 0)
            snippet = self._extract_snippet(code, line_number)

            # Add AI explanation
            enhanced_issue = self.ai_service.enhance_issue_with_ai(
                issue,
                snippet,
                language
            )

            # Optionally add fix suggestion
            if enable_fixes and enhanced_issue.get('has_ai_explanation'):
                fix_info = self.ai_service.suggest_fix(
                    issue,
                    snippet,
                    language
                )
                enhanced_issue['fix_suggestion'] = fix_info

            enhanced_issues.append(enhanced_issue)

            if enhanced_issue.get('has_ai_explanation'):
                enhanced_results['ai_issues_enhanced'] += 1

        enhanced_results['issues'] = enhanced_issues
        return enhanced_results

    def _extract_snippet(
        self,
        code: str,
        line_number: int,
        context_lines: int = 3
    ) -> str:
        """Extract code snippet with context."""
        if not code:
            return ""

        lines = code.split('\n')
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)

        return '\n'.join(lines[start:end])

    def analyze_multiple_files(
        self,
        file_paths: List[str],
        enable_fixes: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze multiple files with AI enhancement.

        Args:
            file_paths: List of file paths
            enable_fixes: Whether to generate fix suggestions

        Returns:
            Combined analysis results
        """
        all_results = {
            'total_files': len(file_paths),
            'analyzed_files': 0,
            'total_issues': 0,
            'ai_enhanced': self.enable_ai,
            'files': []
        }

        for file_path in file_paths:
            try:
                file_results = self.analyze_file(file_path, enable_fixes)

                all_results['files'].append({
                    'file_path': file_path,
                    'issues_count': len(file_results.get('issues', [])),
                    'issues': file_results.get('issues', []),
                    'language': file_results.get('language'),
                    'ai_issues_enhanced': file_results.get('ai_issues_enhanced', 0)
                })

                all_results['analyzed_files'] += 1
                all_results['total_issues'] += len(file_results.get('issues', []))

            except Exception as e:
                all_results['files'].append({
                    'file_path': file_path,
                    'error': str(e)
                })

        return all_results

    def get_severity_summary(
        self,
        analysis_results: Dict[str, Any]
    ) -> Dict[str, int]:
        """
        Get summary of issues by severity.

        Args:
            analysis_results: Analysis results

        Returns:
            Dict with counts by severity
        """
        summary = {
            'critical': 0,
            'error': 0,
            'warning': 0,
            'info': 0
        }

        # Count from direct issues
        for issue in analysis_results.get('issues', []):
            severity = issue.get('severity', 'info')
            if severity in summary:
                summary[severity] += 1

        # Count from file-level issues
        for file_info in analysis_results.get('files', []):
            for issue in file_info.get('issues', []):
                severity = issue.get('severity', 'info')
                if severity in summary:
                    summary[severity] += 1

        return summary

    def get_category_summary(
        self,
        analysis_results: Dict[str, Any]
    ) -> Dict[str, int]:
        """
        Get summary of issues by category.

        Args:
            analysis_results: Analysis results

        Returns:
            Dict with counts by category
        """
        summary = {}

        # Count from direct issues
        for issue in analysis_results.get('issues', []):
            category = issue.get('category', 'unknown')
            summary[category] = summary.get(category, 0) + 1

        # Count from file-level issues
        for file_info in analysis_results.get('files', []):
            for issue in file_info.get('issues', []):
                category = issue.get('category', 'unknown')
                summary[category] = summary.get(category, 0) + 1

        return summary

    def test_ai_connection(self) -> bool:
        """Test AI service connection."""
        if not self.ai_service:
            return False
        return self.ai_service.test_connection()

    def get_info(self) -> Dict[str, Any]:
        """Get analyzer information."""
        info = {
            'enhanced_analyzer': True,
            'ai_enabled': self.enable_ai,
            'code_analyzer': 'CodeAnalyzerService'
        }

        if self.ai_service:
            ai_info = self.ai_service.get_info()
            info['ai_service'] = ai_info

        return info
