"""
Java Code Smell Analyzer
Detects code smells and anti-patterns in Java code
"""

import re
from typing import List
from ..parsers.models import ParsedModule, ClassInfo, FunctionInfo
from .base_analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity


class JavaSmellAnalyzer(BaseAnalyzer):
    """
    Analyzes Java code for code smells and anti-patterns.

    Rules:
    - JAVA-SMELL001: God Class (too many responsibilities)
    - JAVA-SMELL002: Long Method (>50 lines)
    - JAVA-SMELL003: Too Many Parameters (>5 parameters)
    - JAVA-SMELL004: Deep Nesting (>4 levels)
    - JAVA-SMELL005: Magic Numbers
    - JAVA-SMELL006: Empty Catch Blocks
    - JAVA-SMELL007: System.out.println in Production
    - JAVA-SMELL008: Unused Imports
    """

    # Thresholds
    MAX_CLASS_LINES = 500
    MAX_CLASS_METHODS = 20
    MAX_METHOD_LINES = 50
    MAX_PARAMETERS = 5
    MAX_NESTING_DEPTH = 4

    def __init__(self):
        super().__init__()
        self.name = "JavaSmellAnalyzer"
        self.language = "java"

    @property
    def analyzer_id(self) -> str:
        return 'java_smell'

    @property
    def category(self) -> IssueCategory:
        return IssueCategory.SMELL

    def analyze(self, parsed_module: ParsedModule, source_code: str) -> List[CodeIssue]:
        """Run all code smell checks"""
        if parsed_module.language != 'java':
            return []

        file_path = parsed_module.file_path
        issues = []
        issues.extend(self._check_god_classes(parsed_module, source_code, file_path))
        issues.extend(self._check_long_methods(parsed_module, source_code, file_path))
        issues.extend(self._check_too_many_parameters(parsed_module, file_path))
        issues.extend(self._check_deep_nesting(source_code, file_path))
        issues.extend(self._check_magic_numbers(source_code, file_path))
        issues.extend(self._check_empty_catch_blocks(source_code, file_path))
        issues.extend(self._check_system_out(source_code, file_path))
        issues.extend(self._check_unused_imports(parsed_module, source_code, file_path))

        return issues

    def _check_god_classes(self, parsed_module: ParsedModule, source_code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SMELL001: Detect God Classes (classes doing too much)

        Criteria:
        - >500 lines of code
        - >20 methods
        """
        issues = []

        for cls in parsed_module.classes:
            # Skip interfaces and enums
            if 'interface' in cls.name.lower() or 'enum' in cls.name.lower():
                continue

            # Count methods
            method_count = len(cls.methods)

            # Estimate class size (count lines in source)
            class_lines = self._count_class_lines(cls, source_code)

            if class_lines > self.MAX_CLASS_LINES or method_count > self.MAX_CLASS_METHODS:
                severity = IssueSeverity.WARNING
                if class_lines > self.MAX_CLASS_LINES * 2 or method_count > self.MAX_CLASS_METHODS * 2:
                    severity = IssueSeverity.ERROR

                issues.append(CodeIssue(
                    category=IssueCategory.SMELL,
                    severity=severity,
                    rule_id='JAVA-SMELL001',
                    title='God Class Detected',
                    description=(
                        f'Class "{cls.name}" has {method_count} methods and ~{class_lines} lines. '
                        'Consider breaking it into smaller, focused classes following Single Responsibility Principle.'
                    ),
                    file_path=file_path,
                    line_number=cls.line_number,
                    code_snippet=f"class {cls.name}",
                    suggestion='Split into smaller classes with single responsibilities',
                    confidence=0.8
                ))

        return issues

    def _check_long_methods(self, parsed_module: ParsedModule, source_code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SMELL002: Detect long methods

        Threshold: >50 lines
        """
        issues = []

        for cls in parsed_module.classes:
            for method in cls.methods:
                method_lines = self._count_method_lines(method, source_code)

                if method_lines > self.MAX_METHOD_LINES:
                    severity = IssueSeverity.INFO
                    if method_lines > self.MAX_METHOD_LINES * 2:
                        severity = IssueSeverity.WARNING

                    issues.append(CodeIssue(
                        category=IssueCategory.SMELL,
                        severity=severity,
                        rule_id='JAVA-SMELL002',
                        title='Long Method',
                        description=(
                            f'Method "{method.name}" has ~{method_lines} lines. '
                            'Long methods are hard to understand and maintain.'
                        ),
                    file_path=file_path,
                        line_number=method.line_number,
                        code_snippet=f"Method: {method.name}()",
                        suggestion='Extract smaller methods with descriptive names',
                        confidence=0.85
                    ))

        # Also check top-level functions
        for func in parsed_module.functions:
            func_lines = self._count_method_lines(func, source_code)
            if func_lines > self.MAX_METHOD_LINES:
                issues.append(CodeIssue(
                    category=IssueCategory.SMELL,
                    severity=IssueSeverity.INFO,
                    rule_id='JAVA-SMELL002',
                    title='Long Function',
                    description=f'Function "{func.name}" has ~{func_lines} lines',
                    file_path=file_path,
                    line_number=func.line_number,
                    code_snippet=f"Function: {func.name}()",
                    suggestion='Break into smaller functions',
                    confidence=0.85
                ))

        return issues

    def _check_too_many_parameters(self, parsed_module: ParsedModule, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SMELL003: Detect methods with too many parameters

        Threshold: >5 parameters
        """
        issues = []

        for cls in parsed_module.classes:
            for method in cls.methods:
                param_count = len(method.parameters)

                if param_count > self.MAX_PARAMETERS:
                    severity = IssueSeverity.INFO
                    if param_count > self.MAX_PARAMETERS * 2:
                        severity = IssueSeverity.WARNING

                    issues.append(CodeIssue(
                        category=IssueCategory.SMELL,
                        severity=severity,
                        rule_id='JAVA-SMELL003',
                        title='Too Many Parameters',
                        description=(
                            f'Method "{method.name}" has {param_count} parameters. '
                            'Methods with many parameters are hard to use and test.'
                        ),
                    file_path=file_path,
                        line_number=method.line_number,
                        code_snippet=f"{method.name}({', '.join(p.name for p in method.parameters)})",
                        suggestion='Use a parameter object or builder pattern',
                        confidence=0.9
                    ))

        return issues

    def _check_deep_nesting(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SMELL004: Detect deeply nested code

        Threshold: >4 levels of nesting
        """
        issues = []
        lines = source_code.split('\n')

        for i, line in enumerate(lines, 1):
            # Count nesting level by counting braces
            nesting_level = self._calculate_nesting_level(lines, i - 1)

            if nesting_level > self.MAX_NESTING_DEPTH:
                issues.append(CodeIssue(
                    category=IssueCategory.SMELL,
                    severity=IssueSeverity.WARNING,
                    rule_id='JAVA-SMELL004',
                    title='Deep Nesting',
                    description=(
                        f'Code has {nesting_level} levels of nesting. '
                        'Deep nesting reduces readability and increases cognitive complexity.'
                    ),
                    file_path=file_path,
                    line_number=i,
                    code_snippet=line.strip(),
                    suggestion='Extract methods or use early returns (guard clauses)',
                    confidence=0.75
                ))

        return issues

    def _check_magic_numbers(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SMELL005: Detect magic numbers

        Pattern: Numeric literals (except 0, 1, -1)
        """
        issues = []

        # Pattern: numeric literals not in common exceptions
        # Exclude: variable declarations, array indices, comparisons with 0/1
        magic_number_pattern = r'(?<![a-zA-Z0-9_])((?!0|1|-1)\d{2,}|(?!0\.0|1\.0)\d+\.\d+)(?![a-zA-Z0-9_])'

        for match in re.finditer(magic_number_pattern, source_code):
            line_number = source_code[:match.start()].count('\n') + 1
            line = self._get_line(source_code, line_number)

            # Skip if in comment
            if '//' in line and line.index('//') < line.find(match.group()):
                continue

            # Skip if it looks like a constant declaration
            if re.search(r'(?:static\s+)?final\s+\w+\s+\w+\s*=', line):
                continue

            issues.append(CodeIssue(
                category=IssueCategory.SMELL,
                severity=IssueSeverity.INFO,
                rule_id='JAVA-SMELL005',
                title='Magic Number',
                description=(
                    f'Magic number "{match.group()}" should be a named constant. '
                    'Use descriptive constant names for better readability.'
                ),
                    file_path=file_path,
                line_number=line_number,
                code_snippet=line.strip(),
                suggestion='Define as: private static final int MEANINGFUL_NAME = value;',
                confidence=0.6
            ))

        return issues

    def _check_empty_catch_blocks(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SMELL006: Detect empty catch blocks

        Pattern: catch (...) { } or catch with only comments
        """
        issues = []

        # Pattern: catch block followed by empty or near-empty body
        empty_catch_pattern = r'catch\s*\([^)]+\)\s*\{\s*(?://[^\n]*)?\s*\}'

        for match in re.finditer(empty_catch_pattern, source_code):
            line_number = source_code[:match.start()].count('\n') + 1
            issues.append(CodeIssue(
                category=IssueCategory.SMELL,
                severity=IssueSeverity.WARNING,
                rule_id='JAVA-SMELL006',
                title='Empty Catch Block',
                description=(
                    'Empty catch block swallows exceptions silently. '
                    'At minimum, log the exception.'
                ),
                file_path=file_path,
                line_number=line_number,
                code_snippet=self._get_line(source_code, line_number),
                suggestion='Log exception: logger.error("Error message", e);',
                confidence=0.9
            ))

        return issues

    def _check_system_out(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SMELL007: Detect System.out.println in production code

        Pattern: System.out.println, System.err.println
        """
        issues = []

        # Pattern: System.out/err
        sysout_patterns = [
            r'System\.out\.print(?:ln)?\s*\(',
            r'System\.err\.print(?:ln)?\s*\(',
        ]

        for pattern in sysout_patterns:
            for match in re.finditer(pattern, source_code):
                line_number = source_code[:match.start()].count('\n') + 1

                # Check if it's in a test file (more acceptable)
                # This is a simplified check
                is_test = 'test' in source_code.lower()[:200]  # Check file header

                if not is_test:
                    issues.append(CodeIssue(
                        category=IssueCategory.SMELL,
                        severity=IssueSeverity.INFO,
                        rule_id='JAVA-SMELL007',
                        title='System.out in Production Code',
                        description=(
                            'Using System.out.println in production code. '
                            'Use a proper logging framework instead.'
                        ),
                    file_path=file_path,
                        line_number=line_number,
                        code_snippet=self._get_line(source_code, line_number),
                        suggestion='Use logger: logger.info("message");',
                        confidence=0.85
                    ))

        return issues

    def _check_unused_imports(self, parsed_module: ParsedModule, source_code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SMELL008: Detect potentially unused imports

        Note: This is a simplified check using regex
        """
        issues = []

        # Get all imports
        imports = parsed_module.imports

        for import_stmt in imports:
            # Extract the class name from import
            # e.g., "java.util.ArrayList" -> "ArrayList"
            if '.*' in import_stmt:
                # Wildcard import - skip for now
                continue

            class_name = import_stmt.split('.')[-1]

            # Check if class name appears in source (simple check)
            # This is not perfect but catches obvious cases
            if class_name not in source_code:
                # Find the line number of the import
                import_line_pattern = re.escape(import_stmt)
                match = re.search(f'import\\s+{import_line_pattern}', source_code)

                if match:
                    line_number = source_code[:match.start()].count('\n') + 1
                    issues.append(CodeIssue(
                        category=IssueCategory.SMELL,
                        severity=IssueSeverity.INFO,
                        rule_id='JAVA-SMELL008',
                        title='Potentially Unused Import',
                        description=f'Import "{import_stmt}" may not be used',
                    file_path=file_path,
                        line_number=line_number,
                        code_snippet=f"import {import_stmt};",
                        suggestion='Remove unused imports',
                        confidence=0.5  # Low confidence as this is a simple check
                    ))

        return issues

    def _count_class_lines(self, cls: ClassInfo, source_code: str) -> int:
        """Estimate number of lines in a class"""
        if not cls.line_number:
            return 0

        # Count methods' lines
        total_lines = 0
        for method in cls.methods:
            total_lines += self._count_method_lines(method, source_code)

        # Add overhead for class structure (rough estimate)
        return total_lines + len(cls.attributes) * 2 + 10

    def _count_method_lines(self, method: FunctionInfo, source_code: str) -> int:
        """Estimate number of lines in a method"""
        if not method.line_number:
            return 0

        lines = source_code.split('\n')
        start_line = method.line_number - 1

        if start_line >= len(lines):
            return 0

        # Find the opening brace
        brace_count = 0
        in_method = False
        line_count = 0

        for i in range(start_line, min(start_line + 200, len(lines))):
            line = lines[i]
            line_count += 1

            # Count braces
            brace_count += line.count('{') - line.count('}')

            if '{' in line:
                in_method = True

            if in_method and brace_count == 0:
                # Found the closing brace
                return line_count

        # If we didn't find the end, return an estimate
        return min(line_count, 100)

    def _calculate_nesting_level(self, lines: List[str], line_idx: int) -> int:
        """Calculate the nesting level at a given line"""
        nesting = 0

        # Count opening and closing braces up to this line
        for i in range(line_idx + 1):
            line = lines[i]
            # Remove string literals to avoid counting braces in strings
            line_without_strings = re.sub(r'"[^"]*"', '', line)
            nesting += line_without_strings.count('{')
            nesting -= line_without_strings.count('}')

        return max(0, nesting)

    def _get_line(self, code: str, line_number: int) -> str:
        """Get a specific line from code"""
        lines = code.split('\n')
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].strip()
        return ""
