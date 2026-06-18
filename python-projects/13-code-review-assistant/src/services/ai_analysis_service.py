"""
AI Analysis Service

Integrates LLM capabilities with code analysis to provide:
- Detailed explanations of detected issues
- Suggested fixes with code examples
- Refactoring recommendations
- Confidence scoring for AI-generated content
"""

from typing import Dict, List, Optional, Any
from ..core.llm_client import LLMClient


class AIAnalysisService:
    """Service for AI-enhanced code analysis."""

    def __init__(
        self,
        llm_backend: str = "ollama",
        model: Optional[str] = None,
        max_retries: int = 3
    ):
        """
        Initialize AI analysis service.

        Args:
            llm_backend: LLM backend to use (ollama/anthropic/openai)
            model: Model name (optional, uses backend default)
            max_retries: Maximum retry attempts for LLM calls
        """
        self.llm_client = LLMClient(
            backend=llm_backend,
            model=model,
            max_retries=max_retries
        )

    def enhance_issue_with_ai(
        self,
        issue: Dict[str, Any],
        code_snippet: str,
        language: str = "python"
    ) -> Dict[str, Any]:
        """
        Enhance an issue with AI-generated explanation.

        Args:
            issue: Original issue dict with severity, category, title, description
            code_snippet: Code context for the issue
            language: Programming language

        Returns:
            Enhanced issue dict with ai_explanation field
        """
        try:
            # Generate explanation using template
            explanation = self.llm_client.generate_from_template(
                "explain_issue",
                {
                    "category": issue.get("category", "unknown"),
                    "severity": issue.get("severity", "info"),
                    "title": issue.get("title", "Issue"),
                    "description": issue.get("description", ""),
                    "language": language,
                    "code_snippet": code_snippet
                },
                max_tokens=500,
                temperature=0.3  # Lower temperature for more consistent explanations
            )

            # Add explanation to issue
            enhanced_issue = issue.copy()
            enhanced_issue["ai_explanation"] = explanation.strip()
            enhanced_issue["has_ai_explanation"] = True

            return enhanced_issue

        except Exception as e:
            # If AI enhancement fails, return original issue
            print(f"Failed to generate AI explanation: {e}")
            issue_copy = issue.copy()
            issue_copy["has_ai_explanation"] = False
            issue_copy["ai_error"] = str(e)
            return issue_copy

    def suggest_fix(
        self,
        issue: Dict[str, Any],
        code_snippet: str,
        language: str = "python"
    ) -> Dict[str, Any]:
        """
        Generate fix suggestion for an issue.

        Args:
            issue: Issue dict with title and description
            code_snippet: Original code with the issue
            language: Programming language

        Returns:
            Dict with suggested_fix and confidence_score
        """
        try:
            fix_suggestion = self.llm_client.generate_from_template(
                "suggest_fix",
                {
                    "issue_title": issue.get("title", "Issue"),
                    "issue_description": issue.get("description", ""),
                    "code_snippet": code_snippet,
                    "language": language
                },
                max_tokens=800,
                temperature=0.2  # Very low temperature for code generation
            )

            # Calculate confidence based on severity and complexity
            confidence = self._calculate_fix_confidence(issue, fix_suggestion)

            return {
                "suggested_fix": fix_suggestion.strip(),
                "confidence_score": confidence,
                "can_auto_apply": confidence >= 0.8
            }

        except Exception as e:
            return {
                "suggested_fix": None,
                "confidence_score": 0.0,
                "can_auto_apply": False,
                "error": str(e)
            }

    def suggest_refactoring(
        self,
        code_snippet: str,
        issue_type: str = "general",
        language: str = "python"
    ) -> Dict[str, Any]:
        """
        Generate refactoring suggestions.

        Args:
            code_snippet: Code to refactor
            issue_type: Type of issue triggering refactor (smell/complexity/etc)
            language: Programming language

        Returns:
            Dict with refactoring_suggestion, before_code, after_code, confidence
        """
        try:
            refactoring = self.llm_client.generate_from_template(
                "refactor_code",
                {
                    "code_snippet": code_snippet,
                    "language": language,
                    "issue_type": issue_type
                },
                max_tokens=1000,
                temperature=0.2
            )

            # Parse refactoring into before/after
            parsed = self._parse_refactoring_response(refactoring)

            return {
                "refactoring_suggestion": refactoring.strip(),
                "refactored_code": parsed.get("after_code"),
                "explanation": parsed.get("explanation"),
                "confidence_score": self._calculate_refactoring_confidence(
                    code_snippet,
                    parsed.get("after_code", "")
                )
            }

        except Exception as e:
            return {
                "refactoring_suggestion": None,
                "refactored_code": None,
                "explanation": None,
                "confidence_score": 0.0,
                "error": str(e)
            }

    def enhance_analysis_results(
        self,
        analysis_results: Dict[str, Any],
        code_context: Optional[Dict[str, str]] = None,
        enable_fixes: bool = False
    ) -> Dict[str, Any]:
        """
        Enhance entire analysis results with AI explanations.

        Args:
            analysis_results: Results from diff/code analyzers
            code_context: Dict mapping file paths to code content
            enable_fixes: Whether to generate fix suggestions (slower)

        Returns:
            Enhanced analysis results with AI data
        """
        if code_context is None:
            code_context = {}

        enhanced_results = analysis_results.copy()
        enhanced_results["ai_enhanced"] = True
        enhanced_results["ai_issues_count"] = 0

        # Process each file
        for file_info in enhanced_results.get("files", []):
            file_path = file_info.get("file_path", "")
            file_code = code_context.get(file_path, "")

            # Enhance each issue
            enhanced_issues = []
            for issue in file_info.get("issues", []):
                # Extract code snippet around the issue
                line_number = issue.get("line_number", 0)
                snippet = self._extract_code_snippet(
                    file_code,
                    line_number,
                    context_lines=3
                )

                # Add AI explanation
                enhanced_issue = self.enhance_issue_with_ai(
                    issue,
                    snippet,
                    language="python"
                )

                # Optionally add fix suggestion
                if enable_fixes and enhanced_issue.get("has_ai_explanation"):
                    fix_info = self.suggest_fix(issue, snippet)
                    enhanced_issue["fix_suggestion"] = fix_info

                enhanced_issues.append(enhanced_issue)

                if enhanced_issue.get("has_ai_explanation"):
                    enhanced_results["ai_issues_count"] += 1

            file_info["issues"] = enhanced_issues

        return enhanced_results

    def _calculate_fix_confidence(
        self,
        issue: Dict[str, Any],
        fix_suggestion: str
    ) -> float:
        """
        Calculate confidence score for fix suggestion.

        Higher confidence for:
        - Simple security issues (hardcoded secrets, etc)
        - Style issues
        Lower confidence for:
        - Complex logic issues
        - Architecture problems
        """
        severity = issue.get("severity", "info")
        category = issue.get("category", "unknown")

        base_confidence = 0.7

        # Adjust by severity (critical issues are harder to auto-fix)
        severity_adjustments = {
            "info": 0.2,
            "warning": 0.1,
            "error": 0.0,
            "critical": -0.2
        }
        base_confidence += severity_adjustments.get(severity, 0.0)

        # Adjust by category
        category_adjustments = {
            "style": 0.2,
            "security": 0.1,
            "best-practice": 0.15,
            "complexity": -0.1,
            "smell": 0.05
        }
        base_confidence += category_adjustments.get(category, 0.0)

        # Check fix quality indicators
        if len(fix_suggestion) > 100:  # Detailed explanation
            base_confidence += 0.05
        if "```" in fix_suggestion:  # Contains code blocks
            base_confidence += 0.05

        return max(0.0, min(1.0, base_confidence))

    def _calculate_refactoring_confidence(
        self,
        original_code: str,
        refactored_code: Optional[str]
    ) -> float:
        """Calculate confidence for refactoring suggestion."""
        if not refactored_code:
            return 0.0

        # Base confidence
        confidence = 0.6

        # Length similarity (refactored shouldn't be too different)
        len_ratio = len(refactored_code) / max(len(original_code), 1)
        if 0.5 <= len_ratio <= 1.5:
            confidence += 0.2

        # Has proper code structure
        if "def " in refactored_code or "class " in refactored_code:
            confidence += 0.1

        return min(1.0, confidence)

    def _parse_refactoring_response(self, response: str) -> Dict[str, str]:
        """Parse refactoring response into components."""
        # Simple parsing - look for code blocks
        parts = response.split("```")

        result = {
            "explanation": response,
            "after_code": None
        }

        # Extract last code block as refactored code
        if len(parts) >= 3:
            # Last code block is likely the refactored version
            result["after_code"] = parts[-2].strip()
            if result["after_code"].startswith("python"):
                result["after_code"] = result["after_code"][6:].strip()

        return result

    def _extract_code_snippet(
        self,
        code: str,
        line_number: int,
        context_lines: int = 3
    ) -> str:
        """
        Extract code snippet around a line number.

        Args:
            code: Full file content
            line_number: Target line number (1-indexed)
            context_lines: Lines of context before/after

        Returns:
            Code snippet with context
        """
        if not code:
            return ""

        lines = code.split("\n")
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)

        snippet_lines = lines[start:end]
        return "\n".join(snippet_lines)

    def test_connection(self) -> bool:
        """Test LLM connection."""
        return self.llm_client.test_connection()

    def get_info(self) -> Dict[str, Any]:
        """Get service information."""
        llm_info = self.llm_client.get_info()
        return {
            "service": "AIAnalysisService",
            "llm_backend": llm_info["backend"],
            "llm_model": llm_info["model"],
            "capabilities": [
                "issue_explanation",
                "fix_suggestion",
                "refactoring",
                "confidence_scoring"
            ]
        }
