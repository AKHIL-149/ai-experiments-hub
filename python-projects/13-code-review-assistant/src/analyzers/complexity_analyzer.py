"""Complexity analyzer for detecting code complexity issues"""
import ast
from typing import List
from radon.complexity import cc_visit
from radon.metrics import mi_visit
from .base_analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity


class ComplexityAnalyzer(BaseAnalyzer):
    """Detects code complexity issues using cyclomatic complexity and maintainability index"""

    # Default thresholds
    DEFAULT_CC_WARNING = 10
    DEFAULT_CC_ERROR = 15
    DEFAULT_MI_WARNING = 20  # Below 20 is hard to maintain
    DEFAULT_MI_ERROR = 10    # Below 10 is extremely hard to maintain

    def __init__(self, config=None):
        """Initialize complexity analyzer with configurable thresholds"""
        super().__init__(config)
        self.cc_warning_threshold = self.config.get('cc_warning', self.DEFAULT_CC_WARNING)
        self.cc_error_threshold = self.config.get('cc_error', self.DEFAULT_CC_ERROR)
        self.mi_warning_threshold = self.config.get('mi_warning', self.DEFAULT_MI_WARNING)
        self.mi_error_threshold = self.config.get('mi_error', self.DEFAULT_MI_ERROR)

    @property
    def analyzer_id(self) -> str:
        return 'complexity'

    @property
    def category(self) -> IssueCategory:
        return IssueCategory.COMPLEXITY

    def analyze(self, parsed_module, source_code: str) -> List[CodeIssue]:
        """Run all complexity checks"""
        issues = []

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return issues

        issues.extend(self._check_cyclomatic_complexity(source_code, parsed_module.file_path))
        issues.extend(self._check_maintainability_index(source_code, parsed_module.file_path))

        return issues

    def _check_cyclomatic_complexity(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Check cyclomatic complexity using radon"""
        issues = []

        try:
            # Use radon to calculate complexity
            complexity_results = cc_visit(source_code)

            for result in complexity_results:
                # Determine severity based on complexity
                if result.complexity >= self.cc_error_threshold:
                    severity = IssueSeverity.ERROR
                elif result.complexity >= self.cc_warning_threshold:
                    severity = IssueSeverity.WARNING
                else:
                    # Skip if below warning threshold
                    continue

                snippet = self.extract_code_snippet(source_code, result.lineno)

                issues.append(self.create_issue(
                    rule_id='COMPLEX001',
                    severity=severity,
                    title=f'High cyclomatic complexity: {result.name}',
                    description=f'The function "{result.name}" has a cyclomatic complexity of {result.complexity}, '
                               f'which {"exceeds" if severity == IssueSeverity.ERROR else "is above"} the recommended threshold. '
                               f'High complexity indicates too many decision points, making code harder to test and maintain. '
                               f'Each additional branch increases the number of paths through the code.',
                    file_path=file_path,
                    line_number=result.lineno,
                    code_snippet=snippet,
                    suggestion=f'Refactor to reduce complexity: break down into smaller functions, '
                              f'use early returns for guard clauses, replace complex conditionals with lookup tables or polymorphism, '
                              f'or extract decision logic into separate functions.',
                    confidence=1.0,
                    complexity=result.complexity,
                    warning_threshold=self.cc_warning_threshold,
                    error_threshold=self.cc_error_threshold
                ))

        except Exception as e:
            # Radon might fail on certain code patterns
            pass

        return issues

    def _check_maintainability_index(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Check maintainability index using radon"""
        issues = []

        try:
            # Use radon to calculate maintainability index
            mi_results = mi_visit(source_code, multi=True)

            for result in mi_results:
                mi_score = result.mi

                # Determine severity based on MI score
                # MI ranges from 0-100, higher is better
                if mi_score < self.mi_error_threshold:
                    severity = IssueSeverity.ERROR
                elif mi_score < self.mi_warning_threshold:
                    severity = IssueSeverity.WARNING
                else:
                    # Skip if above warning threshold
                    continue

                snippet = self.extract_code_snippet(source_code, result.lineno)

                issues.append(self.create_issue(
                    rule_id='COMPLEX002',
                    severity=severity,
                    title=f'Low maintainability index: {result.name}',
                    description=f'The module/function "{result.name}" has a maintainability index of {mi_score:.1f}, '
                               f'indicating {"very poor" if severity == IssueSeverity.ERROR else "poor"} maintainability. '
                               f'The maintainability index combines complexity, volume, and lack of comments. '
                               f'Scores below 20 indicate code that is hard to maintain.',
                    file_path=file_path,
                    line_number=result.lineno,
                    code_snippet=snippet,
                    suggestion=f'Improve maintainability by: reducing complexity, breaking down large functions, '
                              f'adding meaningful comments and documentation, removing duplicate code, '
                              f'and simplifying logic.',
                    confidence=0.9,
                    maintainability_index=mi_score,
                    warning_threshold=self.mi_warning_threshold,
                    error_threshold=self.mi_error_threshold
                ))

        except Exception as e:
            # Radon might fail on certain code patterns
            pass

        return issues

    def get_rule_ids(self) -> List[str]:
        """Get all rule IDs this analyzer can detect"""
        return ['COMPLEX001', 'COMPLEX002']
