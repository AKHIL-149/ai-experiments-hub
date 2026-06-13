"""Code smell analyzer for detecting code quality issues"""
import ast
from typing import List
from .base_analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity


class SmellAnalyzer(BaseAnalyzer):
    """Detects code smells and maintainability issues"""

    # Default thresholds
    DEFAULT_MAX_METHOD_LINES = 50
    DEFAULT_MAX_PARAMETERS = 5
    DEFAULT_MAX_NESTING_DEPTH = 4
    DEFAULT_MAX_CLASS_METHODS = 20

    def __init__(self, config=None):
        """Initialize smell analyzer with configurable thresholds"""
        super().__init__(config)
        self.max_method_lines = self.config.get('max_method_lines', self.DEFAULT_MAX_METHOD_LINES)
        self.max_parameters = self.config.get('max_parameters', self.DEFAULT_MAX_PARAMETERS)
        self.max_nesting_depth = self.config.get('max_nesting_depth', self.DEFAULT_MAX_NESTING_DEPTH)
        self.max_class_methods = self.config.get('max_class_methods', self.DEFAULT_MAX_CLASS_METHODS)

    @property
    def analyzer_id(self) -> str:
        return 'smell'

    @property
    def category(self) -> IssueCategory:
        return IssueCategory.SMELL

    def analyze(self, parsed_module, source_code: str) -> List[CodeIssue]:
        """Run all code smell checks"""
        issues = []

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return issues

        issues.extend(self._check_long_methods(tree, source_code, parsed_module.file_path))

        return issues

    def _check_long_methods(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect methods/functions that are too long"""
        issues = []
        lines = source_code.split('\n')

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Calculate actual lines of code (excluding blank lines and comments)
                loc = self._count_lines_of_code(node, lines)
                
                if loc > self.max_method_lines:
                    snippet = self.extract_code_snippet(source_code, node.lineno)
                    
                    # Determine if it's a method or function
                    is_method = self._is_method(node, tree)
                    entity_type = "method" if is_method else "function"
                    
                    issues.append(self.create_issue(
                        rule_id='SMELL001',
                        severity=IssueSeverity.WARNING,
                        title=f'Long {entity_type}: {node.name}',
                        description=f'The {entity_type} "{node.name}" has {loc} lines of code, '
                                   f'exceeding the recommended maximum of {self.max_method_lines} lines. '
                                   f'Long {entity_type}s are harder to understand, test, and maintain. '
                                   f'Consider breaking it down into smaller, focused {entity_type}s.',
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=snippet,
                        suggestion=f'Refactor this {entity_type} by extracting logical blocks into separate '
                                  f'{entity_type}s. Look for repeated code, distinct responsibilities, '
                                  f'or sections that can be named and extracted.',
                        confidence=1.0,
                        lines_of_code=loc,
                        threshold=self.max_method_lines
                    ))

        return issues

    def _count_lines_of_code(self, node: ast.FunctionDef, lines: List[str]) -> int:
        """
        Count actual lines of code in a function, excluding:
        - Blank lines
        - Comment-only lines
        - Docstrings
        """
        if not hasattr(node, 'end_lineno') or node.end_lineno is None:
            # Fallback for older Python versions
            return 0

        start_line = node.lineno - 1  # Convert to 0-indexed
        end_line = node.end_lineno - 1

        loc = 0
        in_docstring = False
        docstring_processed = False

        for i in range(start_line, min(end_line + 1, len(lines))):
            line = lines[i].strip()

            # Skip the function definition line
            if i == start_line:
                continue

            # Skip blank lines
            if not line:
                continue

            # Skip comment lines
            if line.startswith('#'):
                continue

            # Handle docstrings (first string literal in function body)
            if not docstring_processed and (line.startswith('"""') or line.startswith("'''")):
                if line.count('"""') >= 2 or line.count("'''") >= 2:
                    # Single-line docstring
                    docstring_processed = True
                    continue
                else:
                    # Multi-line docstring start
                    in_docstring = True
                    continue

            if in_docstring:
                if '"""' in line or "'''" in line:
                    in_docstring = False
                    docstring_processed = True
                continue

            # Count this as a line of code
            loc += 1

        return loc

    def _is_method(self, func_node: ast.FunctionDef, tree: ast.AST) -> bool:
        """Check if a function is a method (defined inside a class)"""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if item is func_node:
                        return True
        return False

    def get_rule_ids(self) -> List[str]:
        """Get all rule IDs this analyzer can detect"""
        return ['SMELL001', 'SMELL002', 'SMELL003', 'SMELL004', 'SMELL005', 'SMELL006']
