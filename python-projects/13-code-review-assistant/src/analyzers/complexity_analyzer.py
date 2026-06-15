"""Complexity analyzer for detecting code complexity issues"""
import ast
from typing import List
from radon.complexity import cc_visit
from radon.metrics import mi_visit
from .base_analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity


class ComplexityAnalyzer(BaseAnalyzer):
    """Detects code complexity issues using cyclomatic complexity, maintainability index, and cognitive complexity"""

    # Default thresholds
    DEFAULT_CC_WARNING = 10
    DEFAULT_CC_ERROR = 15
    DEFAULT_MI_WARNING = 20  # Below 20 is hard to maintain
    DEFAULT_MI_ERROR = 10    # Below 10 is extremely hard to maintain
    DEFAULT_COGNITIVE_WARNING = 15
    DEFAULT_COGNITIVE_ERROR = 25

    def __init__(self, config=None):
        """Initialize complexity analyzer with configurable thresholds"""
        super().__init__(config)

        # Try to load from environment config first, then fall back to passed config, then defaults
        try:
            from ..core.config import get_config
            env_config = get_config().get_complexity_config()
        except ImportError:
            env_config = {}

        self.cc_warning_threshold = self.config.get('cc_warning',
                                                     env_config.get('cc_warning', self.DEFAULT_CC_WARNING))
        self.cc_error_threshold = self.config.get('cc_error',
                                                   env_config.get('cc_error', self.DEFAULT_CC_ERROR))
        self.mi_warning_threshold = self.config.get('mi_warning',
                                                     env_config.get('mi_warning', self.DEFAULT_MI_WARNING))
        self.mi_error_threshold = self.config.get('mi_error',
                                                   env_config.get('mi_error', self.DEFAULT_MI_ERROR))
        self.cognitive_warning_threshold = self.config.get('cognitive_warning',
                                                            env_config.get('cognitive_warning',
                                                                          self.DEFAULT_COGNITIVE_WARNING))
        self.cognitive_error_threshold = self.config.get('cognitive_error',
                                                          env_config.get('cognitive_error',
                                                                        self.DEFAULT_COGNITIVE_ERROR))

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
        issues.extend(self._check_cognitive_complexity(tree, source_code, parsed_module.file_path))

        # Apply configuration (filter disabled rules, apply severity overrides)
        return self.apply_configuration(issues)

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

    def _check_cognitive_complexity(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Check cognitive complexity for each function"""
        issues = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cognitive_score = self._calculate_cognitive_complexity(node)

                # Determine severity based on cognitive complexity
                if cognitive_score >= self.cognitive_error_threshold:
                    severity = IssueSeverity.ERROR
                elif cognitive_score >= self.cognitive_warning_threshold:
                    severity = IssueSeverity.WARNING
                else:
                    # Skip if below warning threshold
                    continue

                snippet = self.extract_code_snippet(source_code, node.lineno)

                # Identify what makes it complex
                complexity_reasons = self._identify_complexity_reasons(node)

                issues.append(self.create_issue(
                    rule_id='COMPLEX003',
                    severity=severity,
                    title=f'High cognitive complexity: {node.name}',
                    description=f'The function "{node.name}" has a cognitive complexity of {cognitive_score}, '
                               f'which {"exceeds" if severity == IssueSeverity.ERROR else "is above"} the recommended threshold. '
                               f'Cognitive complexity measures how difficult code is to understand. '
                               f'High cognitive complexity indicates deeply nested structures, complex conditionals, '
                               f'or confusing control flow that makes code hard to read and maintain. {complexity_reasons}',
                    file_path=file_path,
                    line_number=node.lineno,
                    code_snippet=snippet,
                    suggestion=f'Simplify by: reducing nesting depth (use early returns), '
                              f'breaking complex conditionals into separate functions, '
                              f'extracting nested loops into helper methods, '
                              f'replacing complex boolean logic with descriptive variable names, '
                              f'or using polymorphism instead of conditional chains.',
                    confidence=0.9,
                    cognitive_complexity=cognitive_score,
                    warning_threshold=self.cognitive_warning_threshold,
                    error_threshold=self.cognitive_error_threshold
                ))

        return issues

    def _calculate_cognitive_complexity(self, node: ast.FunctionDef, nesting_level: int = 0) -> int:
        """
        Calculate cognitive complexity for a function.

        Cognitive complexity increments for:
        - Control flow structures (if, for, while, etc.) - base +1 plus nesting level
        - Break and continue statements - +1
        - Binary logical operators - +1 for each after the first in a sequence
        - Except clauses - +1 plus nesting level
        """
        complexity = 0

        for child in ast.walk(node):
            # Skip the function node itself
            if child is node:
                continue

            # Control flow structures: +1 + nesting increment
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With)):
                complexity += 1 + nesting_level

            # Except clauses: +1 + nesting increment
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1 + nesting_level

            # Break and continue: +1
            elif isinstance(child, (ast.Break, ast.Continue)):
                complexity += 1

            # Binary boolean operators (and, or): +1 for each in sequence
            elif isinstance(child, ast.BoolOp):
                # Count the number of operators (values - 1)
                complexity += len(child.values) - 1

        # Recursively calculate for nested structures with increased nesting level
        complexity += self._calculate_nested_complexity(node, nesting_level)

        return complexity

    def _calculate_nested_complexity(self, node: ast.AST, current_nesting: int) -> int:
        """Calculate complexity contribution from nested structures"""
        complexity = 0

        for child in ast.iter_child_nodes(node):
            # Increase nesting level for control structures
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                # Recursively calculate for nested content
                for nested in ast.iter_child_nodes(child):
                    if isinstance(nested, (ast.If, ast.For, ast.While, ast.With)):
                        complexity += 1 + (current_nesting + 1)
                    # Recurse deeper
                    complexity += self._calculate_nested_complexity(nested, current_nesting + 1)
            else:
                complexity += self._calculate_nested_complexity(child, current_nesting)

        return complexity

    def _identify_complexity_reasons(self, node: ast.FunctionDef) -> str:
        """Identify what contributes to cognitive complexity"""
        reasons = []

        # Count different types of complexity contributors
        if_count = sum(1 for _ in ast.walk(node) if isinstance(_, ast.If))
        loop_count = sum(1 for _ in ast.walk(node) if isinstance(_, (ast.For, ast.While)))
        try_count = sum(1 for _ in ast.walk(node) if isinstance(_, ast.Try))
        bool_op_count = sum(1 for _ in ast.walk(node) if isinstance(_, ast.BoolOp))
        max_nesting = self._calculate_max_nesting_depth(node)

        if if_count > 3:
            reasons.append(f'{if_count} conditional statements')
        if loop_count > 2:
            reasons.append(f'{loop_count} loops')
        if try_count > 1:
            reasons.append(f'{try_count} exception handlers')
        if bool_op_count > 2:
            reasons.append(f'{bool_op_count} boolean operations')
        if max_nesting > 3:
            reasons.append(f'maximum nesting depth of {max_nesting}')

        if reasons:
            return f'Contributors: {", ".join(reasons)}.'
        return ''

    def _calculate_max_nesting_depth(self, func_node: ast.FunctionDef) -> int:
        """Calculate maximum nesting depth in a function"""
        def get_depth(node, current_depth=0):
            """Recursively calculate nesting depth"""
            max_depth = current_depth

            for child in ast.iter_child_nodes(node):
                # Count nesting for control flow structures
                if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                    child_depth = get_depth(child, current_depth + 1)
                    max_depth = max(max_depth, child_depth)
                else:
                    child_depth = get_depth(child, current_depth)
                    max_depth = max(max_depth, child_depth)

            return max_depth

        return get_depth(func_node, 0)

    def get_rule_ids(self) -> List[str]:
        """Get all rule IDs this analyzer can detect"""
        return ['COMPLEX001', 'COMPLEX002', 'COMPLEX003']
