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
        issues.extend(self._check_long_parameter_lists(tree, source_code, parsed_module.file_path))
        issues.extend(self._check_god_classes(tree, source_code, parsed_module.file_path))
        issues.extend(self._check_deep_nesting(tree, source_code, parsed_module.file_path))
        issues.extend(self._check_magic_numbers(tree, source_code, parsed_module.file_path))

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

    def _check_long_parameter_lists(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect functions with too many parameters"""
        issues = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Count parameters (excluding self/cls)
                param_count = self._count_parameters(node)

                if param_count > self.max_parameters:
                    snippet = self.extract_code_snippet(source_code, node.lineno)

                    is_method = self._is_method(node, tree)
                    entity_type = "method" if is_method else "function"

                    issues.append(self.create_issue(
                        rule_id='SMELL002',
                        severity=IssueSeverity.WARNING,
                        title=f'Long parameter list: {node.name}',
                        description=f'The {entity_type} "{node.name}" has {param_count} parameters, '
                                   f'exceeding the recommended maximum of {self.max_parameters}. '
                                   f'Long parameter lists make code harder to understand and use. '
                                   f'They often indicate the {entity_type} is doing too much.',
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=snippet,
                        suggestion=f'Consider grouping related parameters into a dataclass, config object, '
                                  f'or parameter object. Alternatively, split the {entity_type} into smaller '
                                  f'{entity_type}s with fewer responsibilities.',
                        confidence=1.0,
                        parameter_count=param_count,
                        threshold=self.max_parameters
                    ))

        return issues

    def _count_parameters(self, node: ast.FunctionDef) -> int:
        """
        Count function parameters, excluding self/cls.
        Counts *args and **kwargs as 1 each.
        """
        args = node.args
        count = 0

        # Regular positional and keyword arguments
        all_args = args.args + args.kwonlyargs
        for arg in all_args:
            # Skip 'self' and 'cls' parameters
            if arg.arg not in ('self', 'cls'):
                count += 1

        # *args counts as 1
        if args.vararg:
            count += 1

        # **kwargs counts as 1
        if args.kwarg:
            count += 1

        return count

    def _check_god_classes(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect classes that are too large or have too many methods"""
        issues = []
        lines = source_code.split('\n')

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Count methods
                method_count = self._count_class_methods(node)

                # Calculate class LOC
                class_loc = self._count_class_lines(node, lines)

                # Check if it exceeds thresholds
                is_god_class = method_count > self.max_class_methods or class_loc > 500

                if is_god_class:
                    snippet = self.extract_code_snippet(source_code, node.lineno)

                    reasons = []
                    if method_count > self.max_class_methods:
                        reasons.append(f'{method_count} methods (max: {self.max_class_methods})')
                    if class_loc > 500:
                        reasons.append(f'{class_loc} lines of code (max: 500)')

                    reason_str = ' and '.join(reasons)

                    issues.append(self.create_issue(
                        rule_id='SMELL003',
                        severity=IssueSeverity.WARNING,
                        title=f'God class: {node.name}',
                        description=f'The class "{node.name}" is too large with {reason_str}. '
                                   f'God classes violate the Single Responsibility Principle and become '
                                   f'difficult to maintain, test, and understand. They often indicate that '
                                   f'the class is doing too many things.',
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=snippet,
                        suggestion=f'Split this class into smaller, focused classes with single responsibilities. '
                                  f'Look for distinct groups of methods that work with separate data or serve '
                                  f'different purposes. Consider using composition or extracting service classes.',
                        confidence=1.0,
                        method_count=method_count,
                        lines_of_code=class_loc,
                        method_threshold=self.max_class_methods,
                        loc_threshold=500
                    ))

        return issues

    def _count_class_methods(self, class_node: ast.ClassDef) -> int:
        """Count the number of methods in a class"""
        count = 0
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                count += 1
        return count

    def _count_class_lines(self, class_node: ast.ClassDef, lines: List[str]) -> int:
        """Count actual lines of code in a class (excluding blanks and comments)"""
        if not hasattr(class_node, 'end_lineno') or class_node.end_lineno is None:
            return 0

        start_line = class_node.lineno - 1
        end_line = class_node.end_lineno - 1

        loc = 0
        for i in range(start_line, min(end_line + 1, len(lines))):
            line = lines[i].strip()

            # Skip blank lines and comment lines
            if line and not line.startswith('#'):
                loc += 1

        return loc

    def _check_deep_nesting(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect functions with deep nesting levels"""
        issues = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                max_depth = self._calculate_max_nesting_depth(node)

                if max_depth > self.max_nesting_depth:
                    snippet = self.extract_code_snippet(source_code, node.lineno)

                    is_method = self._is_method(node, tree)
                    entity_type = "method" if is_method else "function"

                    issues.append(self.create_issue(
                        rule_id='SMELL004',
                        severity=IssueSeverity.WARNING,
                        title=f'Deep nesting in {entity_type}: {node.name}',
                        description=f'The {entity_type} "{node.name}" has a maximum nesting depth of {max_depth}, '
                                   f'exceeding the recommended maximum of {self.max_nesting_depth}. '
                                   f'Deep nesting makes code harder to understand and follow. '
                                   f'It often indicates complex control flow that should be simplified.',
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=snippet,
                        suggestion=f'Refactor to reduce nesting: use early returns/continue for guard clauses, '
                                  f'extract nested blocks into separate {entity_type}s, or invert conditions. '
                                  f'Consider using polymorphism or lookup tables for complex conditionals.',
                        confidence=1.0,
                        max_depth=max_depth,
                        threshold=self.max_nesting_depth
                    ))

        return issues

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

    def _check_magic_numbers(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect magic numbers (unexplained numeric literals)"""
        issues = []
        # Track numbers we've already reported to avoid duplicates
        reported = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                # Check if it's a number (int or float)
                if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                    # Ignore common constants
                    if node.value in (0, 1, -1, 2, 0.0, 1.0):
                        continue

                    # Create a unique key for this number occurrence
                    location_key = (node.lineno, node.col_offset, node.value)
                    if location_key in reported:
                        continue

                    # Check if it's in a valid context (not in default arguments, type annotations, etc.)
                    if self._is_magic_number_context(node, tree):
                        reported.add(location_key)
                        snippet = self.extract_code_snippet(source_code, node.lineno)

                        issues.append(self.create_issue(
                            rule_id='SMELL005',
                            severity=IssueSeverity.INFO,
                            title=f'Magic number: {node.value}',
                            description=f'Found magic number {node.value} in the code. '
                                       f'Magic numbers are numeric literals without clear meaning. '
                                       f'They make code harder to understand and maintain, and can lead to '
                                       f'errors if the same value needs to be changed in multiple places.',
                            file_path=file_path,
                            line_number=node.lineno,
                            code_snippet=snippet,
                            suggestion=f'Replace this magic number with a named constant that explains its purpose. '
                                      f'For example: MAX_RETRIES = {node.value} or TIMEOUT_SECONDS = {node.value}',
                            confidence=0.7,
                            magic_number=node.value
                        ))

        return issues

    def _is_magic_number_context(self, node: ast.Constant, tree: ast.AST) -> bool:
        """Check if a number is in a context where it should be flagged as magic"""
        # Find the parent context
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                if child is node:
                    # Skip if it's in a comparison (like x > 0)
                    # We only flag numbers in assignments, operations, function calls, etc.
                    # This is a simple heuristic - magic numbers are most problematic
                    # when they appear in logic/calculations
                    if isinstance(parent, (ast.BinOp, ast.UnaryOp, ast.Assign,
                                          ast.AugAssign, ast.Return, ast.Call)):
                        return True
        return False

    def get_rule_ids(self) -> List[str]:
        """Get all rule IDs this analyzer can detect"""
        return ['SMELL001', 'SMELL002', 'SMELL003', 'SMELL004', 'SMELL005', 'SMELL006']
