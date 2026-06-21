"""
JavaScript Code Smell Analyzer
Detects code smells and anti-patterns in JavaScript/TypeScript code
"""

import re
from typing import List

from .base_analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity


class JavaScriptSmellAnalyzer(BaseAnalyzer):
    """
    Detects code smells and anti-patterns in JavaScript/TypeScript.

    Rules:
    - JS-SMELL001: Callback hell (deeply nested callbacks)
    - JS-SMELL002: Promise anti-patterns
    - JS-SMELL003: Console.log in production code
    - JS-SMELL004: Long functions (>50 lines)
    - JS-SMELL005: Too many parameters (>5)
    - JS-SMELL006: Magic numbers
    - JS-SMELL007: Unused variables
    - JS-SMELL008: Global variable pollution
    """

    MAX_FUNCTION_LINES = 50
    MAX_PARAMETERS = 5
    CALLBACK_NESTING_THRESHOLD = 3

    @property
    def analyzer_id(self) -> str:
        return 'javascript-smell'

    @property
    def category(self) -> IssueCategory:
        return IssueCategory.SMELL

    def analyze(self, parsed_module, source_code: str) -> List[CodeIssue]:
        """Run all JavaScript code smell checks"""
        issues = []

        issues.extend(self._check_callback_hell(source_code, parsed_module.file_path))
        issues.extend(self._check_promise_antipatterns(source_code, parsed_module.file_path))
        issues.extend(self._check_console_log(source_code, parsed_module.file_path))
        issues.extend(self._check_long_functions(parsed_module, source_code))
        issues.extend(self._check_too_many_parameters(parsed_module, source_code))
        issues.extend(self._check_magic_numbers(source_code, parsed_module.file_path))
        issues.extend(self._check_var_usage(source_code, parsed_module.file_path))
        issues.extend(self._check_global_pollution(source_code, parsed_module.file_path))

        return self.apply_configuration(issues)

    def _check_callback_hell(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect callback hell (deeply nested callbacks)"""
        issues = []
        lines = source_code.split('\n')

        # Track nesting level
        for line_num, line in enumerate(lines, start=1):
            # Look for deeply nested function callbacks
            # Count opening braces and function keywords before this line
            code_before = '\n'.join(lines[:line_num])

            # Simple heuristic: count nested function patterns
            nested_functions = len(re.findall(r'function\s*\([^)]*\)\s*{', code_before))
            nested_arrows = len(re.findall(r'=>\s*{', code_before))
            total_nesting = nested_functions + nested_arrows

            # Count closing braces to approximate actual nesting
            open_braces = code_before.count('{')
            close_braces = code_before.count('}')
            current_depth = open_braces - close_braces

            if current_depth >= self.CALLBACK_NESTING_THRESHOLD and 'function' in line:
                issues.append(self.create_issue(
                    rule_id='JS-SMELL001',
                    severity=IssueSeverity.WARNING,
                    title='Callback hell detected',
                    description=f'Deeply nested callbacks (depth: {current_depth}). '
                               'This makes code hard to read and maintain.',
                    file_path=file_path,
                    line_number=line_num,
                    code_snippet=line.strip(),
                    suggestion='Refactor to use Promises, async/await, or extract named functions. '
                              'Consider breaking down the logic into smaller, testable functions.'
                ))
                break  # Only report once per file

        return issues

    def _check_promise_antipatterns(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect Promise anti-patterns"""
        issues = []

        # Anti-pattern 1: Missing .catch() on promises
        promise_chains = re.finditer(r'\.then\([^)]+\)(?!\s*\.(?:then|catch|finally))', source_code)
        for match in promise_chains:
            line_num = source_code[:match.start()].count('\n') + 1
            # Make sure it's end of statement
            next_char_pos = match.end()
            if next_char_pos < len(source_code):
                next_chars = source_code[next_char_pos:next_char_pos+10].strip()
                if next_chars.startswith(';') or next_chars.startswith('\n'):
                    issues.append(self.create_issue(
                        rule_id='JS-SMELL002',
                        severity=IssueSeverity.WARNING,
                        title='Promise without .catch()',
                        description='Promise chain without .catch() can lead to unhandled rejections.',
                        file_path=file_path,
                        line_number=line_num,
                        code_snippet=self.extract_code_snippet(source_code, line_num),
                        suggestion='Add .catch() to handle errors or use try/catch with async/await.'
                    ))

        # Anti-pattern 2: new Promise() with async executor
        async_executor = re.finditer(r'new\s+Promise\s*\(\s*async\s+', source_code)
        for match in async_executor:
            line_num = source_code[:match.start()].count('\n') + 1
            issues.append(self.create_issue(
                rule_id='JS-SMELL002',
                severity=IssueSeverity.WARNING,
                title='Async Promise executor anti-pattern',
                description='Using async function as Promise executor is an anti-pattern. '
                           'The Promise constructor expects a synchronous executor.',
                file_path=file_path,
                line_number=line_num,
                code_snippet=self.extract_code_snippet(source_code, line_num),
                suggestion='Use async/await directly or return Promise from async function.'
            ))

        # Anti-pattern 3: Nesting Promises instead of chaining
        nested_promises = re.finditer(r'\.then\([^)]*\.then\(', source_code)
        for match in nested_promises:
            line_num = source_code[:match.start()].count('\n') + 1
            issues.append(self.create_issue(
                rule_id='JS-SMELL002',
                severity=IssueSeverity.INFO,
                title='Nested promises detected',
                description='Nesting promises instead of chaining them reduces readability.',
                file_path=file_path,
                line_number=line_num,
                code_snippet=self.extract_code_snippet(source_code, line_num),
                suggestion='Chain promises using .then() or use async/await for better readability.'
            ))

        return issues

    def _check_console_log(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect console.log statements (debug code left in production)"""
        issues = []

        # Check for console.log, console.warn, console.error
        console_patterns = [
            (r'console\.log\s*\(', 'console.log'),
            (r'console\.debug\s*\(', 'console.debug'),
            (r'console\.warn\s*\(', 'console.warn'),
            (r'console\.error\s*\(', 'console.error'),
        ]

        for pattern, method in console_patterns:
            for match in re.finditer(pattern, source_code):
                # Skip if it's in a comment
                line_num = source_code[:match.start()].count('\n') + 1
                line = source_code.split('\n')[line_num - 1] if line_num <= len(source_code.split('\n')) else ''

                if '//' in line and line.index('//') < line.index('console'):
                    continue

                severity = IssueSeverity.INFO if method in ['console.warn', 'console.error'] else IssueSeverity.WARNING

                issues.append(self.create_issue(
                    rule_id='JS-SMELL003',
                    severity=severity,
                    title=f'{method} found in code',
                    description=f'{method} should not be left in production code. '
                               'Use a proper logging library instead.',
                    file_path=file_path,
                    line_number=line_num,
                    code_snippet=line.strip(),
                    suggestion='Remove console statements or use a logging library like winston, bunyan, or pino.'
                ))

        return issues

    def _check_long_functions(self, parsed_module, source_code: str) -> List[CodeIssue]:
        """Detect functions that are too long"""
        issues = []
        lines = source_code.split('\n')

        for func in parsed_module.functions:
            # Find function end by counting braces
            func_line_start = func.line_number - 1
            if func_line_start >= len(lines):
                continue

            # Simple heuristic: find matching closing brace
            brace_count = 0
            func_line_end = func_line_start
            started = False

            for i in range(func_line_start, len(lines)):
                line = lines[i]
                if '{' in line:
                    brace_count += line.count('{')
                    started = True
                if '}' in line:
                    brace_count -= line.count('}')

                if started and brace_count == 0:
                    func_line_end = i
                    break

            func_length = func_line_end - func_line_start + 1

            if func_length > self.MAX_FUNCTION_LINES:
                issues.append(self.create_issue(
                    rule_id='JS-SMELL004',
                    severity=IssueSeverity.WARNING,
                    title=f'Long function: {func.name}',
                    description=f'Function "{func.name}" is {func_length} lines long. '
                               f'Functions longer than {self.MAX_FUNCTION_LINES} lines are hard to understand and maintain.',
                    file_path=parsed_module.file_path,
                    line_number=func.line_number,
                    code_snippet=f'function {func.name}() {{ ... }} // {func_length} lines',
                    suggestion='Break this function into smaller, single-responsibility functions. '
                              'Extract logical blocks into helper functions.'
                ))

        return issues

    def _check_too_many_parameters(self, parsed_module, source_code: str) -> List[CodeIssue]:
        """Detect functions with too many parameters"""
        issues = []

        for func in parsed_module.functions:
            param_count = len(func.parameters)

            if param_count > self.MAX_PARAMETERS:
                issues.append(self.create_issue(
                    rule_id='JS-SMELL005',
                    severity=IssueSeverity.WARNING,
                    title=f'Too many parameters: {func.name}',
                    description=f'Function "{func.name}" has {param_count} parameters. '
                               f'Functions with more than {self.MAX_PARAMETERS} parameters are hard to use and test.',
                    file_path=parsed_module.file_path,
                    line_number=func.line_number,
                    code_snippet=self.extract_code_snippet(source_code, func.line_number),
                    suggestion='Consider using an options object or refactoring the function. '
                              'Example: function foo(options) instead of function foo(a, b, c, d, e, f).'
                ))

        return issues

    def _check_magic_numbers(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect magic numbers (unexplained numeric literals)"""
        issues = []

        # Find numeric literals that aren't 0, 1, -1 (common acceptable values)
        # Skip numbers in comments, strings, or array indices
        magic_number_pattern = r'(?<![a-zA-Z0-9_])([-+]?\d{2,}(?:\.\d+)?(?:[eE][-+]?\d+)?)(?![a-zA-Z0-9_])'

        for match in re.finditer(magic_number_pattern, source_code):
            number = match.group(1)
            line_num = source_code[:match.start()].count('\n') + 1
            line = source_code.split('\n')[line_num - 1] if line_num <= len(source_code.split('\n')) else ''

            # Skip if in comment
            if '//' in line and line.index('//') < match.start() - source_code[:match.start()].rfind('\n'):
                continue

            # Skip if it looks like part of a constant definition
            if re.search(r'(?:const|let)\s+[A-Z_]+\s*=', line):
                continue

            # Skip common acceptable numbers
            if number in ['0', '1', '-1', '100', '1000']:
                continue

            issues.append(self.create_issue(
                rule_id='JS-SMELL006',
                severity=IssueSeverity.INFO,
                title='Magic number detected',
                description=f'Numeric literal "{number}" should be replaced with a named constant.',
                file_path=file_path,
                line_number=line_num,
                code_snippet=line.strip(),
                suggestion=f'Define a constant: const MEANINGFUL_NAME = {number};'
            ))

        # Limit to avoid spam
        return issues[:10]

    def _check_var_usage(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect usage of 'var' instead of 'const' or 'let'"""
        issues = []

        # Find var declarations
        for match in re.finditer(r'\bvar\s+([a-zA-Z_$][a-zA-Z0-9_$]*)', source_code):
            line_num = source_code[:match.start()].count('\n') + 1
            var_name = match.group(1)

            issues.append(self.create_issue(
                rule_id='JS-SMELL007',
                severity=IssueSeverity.INFO,
                title='Use of "var" keyword',
                description=f'Variable "{var_name}" declared with "var". '
                           'Use "const" for constants or "let" for variables in ES6+.',
                file_path=file_path,
                line_number=line_num,
                code_snippet=self.extract_code_snippet(source_code, line_num),
                suggestion='Replace "var" with "const" (if never reassigned) or "let" (if reassigned).'
            ))

        return issues

    def _check_global_pollution(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect potential global variable pollution"""
        issues = []

        # Check for variables declared outside functions without const/let/var
        # This is a simple heuristic
        lines = source_code.split('\n')

        in_function = False
        brace_count = 0

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track if we're inside a function
            if 'function' in stripped or '=>' in stripped:
                in_function = True

            brace_count += stripped.count('{') - stripped.count('}')

            if brace_count == 0:
                in_function = False

            # Look for assignments without declaration keywords at top level
            if not in_function and '=' in stripped:
                # Pattern: identifier = value (without const/let/var)
                if re.match(r'^([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=', stripped):
                    # Make sure it's not a property assignment (no dot before)
                    if not stripped.startswith('.') and 'const ' not in stripped and 'let ' not in stripped and 'var ' not in stripped:
                        # Skip if it's in a class
                        if not any(keyword in source_code[:source_code.find(stripped)] for keyword in ['class ']):
                            var_name = re.match(r'^([a-zA-Z_$][a-zA-Z0-9_$]*)', stripped).group(1)

                            issues.append(self.create_issue(
                                rule_id='JS-SMELL008',
                                severity=IssueSeverity.WARNING,
                                title='Potential global variable',
                                description=f'Variable "{var_name}" may be implicitly global. '
                                           'Always declare variables with const, let, or var.',
                                file_path=file_path,
                                line_number=line_num,
                                code_snippet=stripped,
                                suggestion=f'Add declaration keyword: const {var_name} = ... or let {var_name} = ...'
                            ))

        return issues[:5]  # Limit to avoid spam
