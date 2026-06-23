"""
AI Refactoring Service
Advanced AI-powered refactoring, code generation, and technical debt estimation
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from src.core.llm_client import LLMClient
from src.core.database import DatabaseManager, Issue, Refactoring


class RefactoringType(Enum):
    """Types of refactoring operations"""
    EXTRACT_METHOD = "extract_method"
    RENAME = "rename"
    SIMPLIFY = "simplify"
    OPTIMIZE = "optimize"
    SECURITY_FIX = "security_fix"
    STYLE_FIX = "style_fix"
    COMPLEXITY_REDUCTION = "complexity_reduction"


@dataclass
class RefactoringChain:
    """A sequence of refactoring steps"""
    steps: List[Dict[str, Any]]
    original_code: str
    final_code: str
    confidence: float
    explanation: str
    estimated_time: str


class AIRefactoringService:
    """Advanced AI-powered refactoring service"""

    def __init__(self):
        self.llm = LLMClient()
        self.db_manager = DatabaseManager()

    def generate_multi_step_refactoring(
        self,
        code: str,
        language: str,
        issues: List[Dict[str, Any]],
        max_steps: int = 5
    ) -> RefactoringChain:
        """
        Generate a multi-step refactoring chain to fix all issues

        Args:
            code: Original code
            language: Programming language
            issues: List of issues to fix
            max_steps: Maximum number of refactoring steps

        Returns:
            RefactoringChain object with sequential steps
        """
        # Prioritize issues by severity
        sorted_issues = sorted(
            issues,
            key=lambda x: self._get_severity_priority(x.get('severity', 'info')),
            reverse=True
        )

        # Group related issues
        issue_groups = self._group_related_issues(sorted_issues)

        # Generate refactoring plan
        prompt = f"""You are an expert code refactoring assistant. Analyze this {language} code and the identified issues.
Generate a step-by-step refactoring plan to fix all issues.

Code:
```{language}
{code}
```

Issues to fix:
{json.dumps([{{
    'severity': i.get('severity'),
    'category': i.get('category'),
    'title': i.get('title'),
    'line': i.get('line_number')
}} for i in sorted_issues[:10]], indent=2)}

Generate a refactoring plan with up to {max_steps} steps. For each step:
1. Describe what to change and why
2. Show the code after this step
3. Explain which issues are addressed

Format response as JSON:
{{
    "steps": [
        {{
            "step_number": 1,
            "type": "extract_method|rename|simplify|optimize|security_fix|style_fix",
            "description": "...",
            "code_after": "...",
            "issues_addressed": ["issue title 1", ...],
            "confidence": 0.95
        }}
    ],
    "overall_confidence": 0.9,
    "estimated_time": "15 minutes",
    "explanation": "Overall plan summary"
}}"""

        response = self.llm.complete(prompt, max_tokens=4000)

        try:
            # Parse JSON response
            result = json.loads(response)

            steps = result.get('steps', [])
            final_code = steps[-1].get('code_after', code) if steps else code

            return RefactoringChain(
                steps=steps,
                original_code=code,
                final_code=final_code,
                confidence=result.get('overall_confidence', 0.8),
                explanation=result.get('explanation', ''),
                estimated_time=result.get('estimated_time', 'Unknown')
            )

        except json.JSONDecodeError:
            # Fallback: simple single-step refactoring
            return self._generate_simple_refactoring(code, language, issues)

    def _generate_simple_refactoring(
        self,
        code: str,
        language: str,
        issues: List[Dict[str, Any]]
    ) -> RefactoringChain:
        """Generate a simple single-step refactoring"""
        prompt = f"""Fix the following issues in this {language} code:

Code:
```{language}
{code}
```

Issues:
{', '.join([i.get('title', '') for i in issues[:5]])}

Provide the refactored code:"""

        refactored_code = self.llm.complete(prompt, max_tokens=2000)

        # Clean code blocks
        refactored_code = re.sub(r'```[a-z]*\n?', '', refactored_code).strip()

        return RefactoringChain(
            steps=[{
                'step_number': 1,
                'type': 'simplify',
                'description': 'Fix identified issues',
                'code_after': refactored_code,
                'issues_addressed': [i.get('title') for i in issues],
                'confidence': 0.7
            }],
            original_code=code,
            final_code=refactored_code,
            confidence=0.7,
            explanation='Single-step refactoring to address all issues',
            estimated_time='10 minutes'
        )

    def apply_automated_fix(
        self,
        issue_id: str,
        generate_test: bool = True
    ) -> Dict[str, Any]:
        """
        Automatically apply a fix for an issue

        Args:
            issue_id: Issue ID to fix
            generate_test: Whether to generate a test for the fix

        Returns:
            Dictionary with fix details and optional test
        """
        with self.db_manager.get_session() as db:
            issue = db.query(Issue).filter(Issue.id == issue_id).first()

            if not issue:
                return {
                    'success': False,
                    'error': 'Issue not found'
                }

            # Generate fix
            prompt = f"""You are a code fixing assistant. Fix this issue:

Issue: {issue.title}
Description: {issue.description}
Severity: {issue.severity}
Category: {issue.category}

Code:
```
{issue.code_snippet}
```

Provide:
1. The fixed code
2. Explanation of the fix
{"3. A test case to verify the fix" if generate_test else ""}

Format as JSON:
{{
    "fixed_code": "...",
    "explanation": "...",
    {"test_code": "..."," if generate_test else ""}
    "confidence": 0.95
}}"""

            response = self.llm.complete(prompt, max_tokens=2000)

            try:
                result = json.loads(response)

                # Create refactoring record
                refactoring = Refactoring(
                    issue_id=issue_id,
                    refactoring_type='automated_fix',
                    original_code=issue.code_snippet,
                    refactored_code=result.get('fixed_code', ''),
                    explanation=result.get('explanation', ''),
                    confidence=result.get('confidence', 0.8),
                    status='pending'
                )

                db.add(refactoring)
                db.commit()
                db.refresh(refactoring)

                return {
                    'success': True,
                    'refactoring_id': refactoring.id,
                    'fixed_code': result.get('fixed_code'),
                    'explanation': result.get('explanation'),
                    'test_code': result.get('test_code') if generate_test else None,
                    'confidence': result.get('confidence')
                }

            except json.JSONDecodeError:
                return {
                    'success': False,
                    'error': 'Failed to parse AI response'
                }

    def estimate_technical_debt(
        self,
        code_files: List[Dict[str, Any]],
        issues: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Estimate technical debt for a codebase

        Args:
            code_files: List of code file metadata
            issues: List of all issues

        Returns:
            Technical debt estimation
        """
        # Calculate metrics
        total_files = len(code_files)
        total_issues = len(issues)
        total_loc = sum(f.get('lines_of_code', 0) for f in code_files)

        # Count by severity
        severity_counts = {
            'critical': sum(1 for i in issues if i.get('severity') == 'critical'),
            'error': sum(1 for i in issues if i.get('severity') == 'error'),
            'warning': sum(1 for i in issues if i.get('severity') == 'warning'),
            'info': sum(1 for i in issues if i.get('severity') == 'info')
        }

        # Estimate time to fix (hours)
        time_estimates = {
            'critical': 4,  # 4 hours each
            'error': 2,     # 2 hours each
            'warning': 1,   # 1 hour each
            'info': 0.5     # 30 minutes each
        }

        total_hours = sum(
            severity_counts[severity] * time_estimates[severity]
            for severity in severity_counts
        )

        # Calculate debt ratio (issues per 1000 LOC)
        debt_ratio = (total_issues / total_loc * 1000) if total_loc > 0 else 0

        # Categorize debt level
        if debt_ratio < 5:
            debt_level = 'low'
            debt_color = 'green'
        elif debt_ratio < 15:
            debt_level = 'medium'
            debt_color = 'yellow'
        elif debt_ratio < 30:
            debt_level = 'high'
            debt_color = 'orange'
        else:
            debt_level = 'critical'
            debt_color = 'red'

        # Calculate cost estimate (assuming $100/hour)
        hourly_rate = 100
        total_cost = total_hours * hourly_rate

        # Generate recommendations
        recommendations = []

        if severity_counts['critical'] > 0:
            recommendations.append({
                'priority': 'high',
                'title': f"Fix {severity_counts['critical']} critical issues",
                'description': 'Critical issues pose immediate risks and should be addressed first',
                'estimated_time': f"{severity_counts['critical'] * time_estimates['critical']} hours"
            })

        if severity_counts['error'] > 10:
            recommendations.append({
                'priority': 'medium',
                'title': 'Address high error count',
                'description': f'{severity_counts["error"]} errors found. Consider dedicating sprint time to reduce this',
                'estimated_time': f"{severity_counts['error'] * time_estimates['error']} hours"
            })

        if debt_ratio > 20:
            recommendations.append({
                'priority': 'medium',
                'title': 'Reduce technical debt ratio',
                'description': f'Debt ratio of {debt_ratio:.1f} issues/KLOC is high. Target: <10',
                'estimated_time': 'Ongoing effort'
            })

        return {
            'total_files': total_files,
            'total_loc': total_loc,
            'total_issues': total_issues,
            'severity_counts': severity_counts,
            'debt_ratio': round(debt_ratio, 2),
            'debt_level': debt_level,
            'debt_color': debt_color,
            'estimated_hours': round(total_hours, 1),
            'estimated_cost': round(total_cost, 2),
            'estimated_days': round(total_hours / 8, 1),
            'recommendations': recommendations,
            'priority_breakdown': {
                'high': severity_counts['critical'] + severity_counts['error'],
                'medium': severity_counts['warning'],
                'low': severity_counts['info']
            }
        }

    def ai_pair_programming(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        language: str = 'python'
    ) -> Dict[str, Any]:
        """
        AI pair programming mode - interactive code assistance

        Args:
            prompt: User's request or question
            context: Optional context (current file, issues, etc.)
            language: Programming language

        Returns:
            AI response with code suggestions
        """
        context_str = ""
        if context:
            if context.get('current_file'):
                context_str += f"\nCurrent file:\n```{language}\n{context['current_file']}\n```\n"

            if context.get('issues'):
                context_str += f"\nKnown issues:\n{json.dumps(context['issues'], indent=2)}\n"

            if context.get('recent_changes'):
                context_str += f"\nRecent changes:\n{context['recent_changes']}\n"

        ai_prompt = f"""You are an AI pair programming assistant. Help the developer with their request.

{context_str}

Developer request: {prompt}

Provide:
1. Code suggestion or solution
2. Explanation
3. Potential issues to watch out for
4. Alternative approaches (if applicable)

Format as JSON:
{{
    "code": "...",
    "explanation": "...",
    "warnings": ["..."],
    "alternatives": ["..."],
    "confidence": 0.95
}}"""

        response = self.llm.complete(ai_prompt, max_tokens=2000)

        try:
            result = json.loads(response)
            return {
                'success': True,
                **result
            }
        except json.JSONDecodeError:
            # Return raw response if JSON parsing fails
            return {
                'success': False,
                'raw_response': response
            }

    def predict_code_smells(
        self,
        code: str,
        language: str
    ) -> List[Dict[str, Any]]:
        """
        Predict potential code smells using AI

        Args:
            code: Code to analyze
            language: Programming language

        Returns:
            List of predicted code smells
        """
        prompt = f"""Analyze this {language} code for potential code smells and maintainability issues.

Code:
```{language}
{code}
```

Identify:
1. Code smells (long methods, god classes, duplicate code, etc.)
2. Maintainability concerns
3. Future refactoring opportunities
4. Architectural issues

Format as JSON array:
[
    {{
        "smell_type": "long_method",
        "location": "line 10-50",
        "description": "...",
        "severity": "warning",
        "confidence": 0.9,
        "refactoring_suggestion": "..."
    }}
]"""

        response = self.llm.complete(prompt, max_tokens=2000)

        try:
            smells = json.loads(response)
            return smells if isinstance(smells, list) else []
        except json.JSONDecodeError:
            return []

    def _get_severity_priority(self, severity: str) -> int:
        """Get numeric priority for severity"""
        priorities = {
            'critical': 4,
            'error': 3,
            'warning': 2,
            'info': 1
        }
        return priorities.get(severity, 0)

    def _group_related_issues(self, issues: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Group related issues together"""
        # Simple grouping by category
        groups = {}
        for issue in issues:
            category = issue.get('category', 'other')
            if category not in groups:
                groups[category] = []
            groups[category].append(issue)

        return list(groups.values())


# Global instance
ai_refactoring_service = AIRefactoringService()
