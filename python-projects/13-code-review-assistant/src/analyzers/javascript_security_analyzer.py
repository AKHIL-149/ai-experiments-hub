"""
JavaScript Security Analyzer
Detects security vulnerabilities in JavaScript/TypeScript code
"""

import re
from typing import List, Optional

try:
    import esprima
    from esprima import nodes
    ESPRIMA_AVAILABLE = True
except ImportError:
    ESPRIMA_AVAILABLE = False

from .base_analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity


class JavaScriptSecurityAnalyzer(BaseAnalyzer):
    """
    Detects security vulnerabilities in JavaScript/TypeScript code.

    Rules:
    - JS-SEC001: eval() usage
    - JS-SEC002: innerHTML assignment (XSS)
    - JS-SEC003: document.write() (XSS)
    - JS-SEC004: Prototype pollution
    - JS-SEC005: Unsafe regex (ReDoS)
    - JS-SEC006: Hardcoded secrets/credentials
    """

    # Patterns for detecting hardcoded secrets
    SECRET_PATTERNS = [
        (r'sk_live_[a-zA-Z0-9]{24,}', 'Stripe API key'),
        (r'sk_test_[a-zA-Z0-9]{24,}', 'Stripe test key'),
        (r'ghp_[a-zA-Z0-9]{36,}', 'GitHub personal access token'),
        (r'gho_[a-zA-Z0-9]{36,}', 'GitHub OAuth token'),
        (r'AKIA[0-9A-Z]{16}', 'AWS access key'),
        (r'AIza[0-9A-Za-z\\-_]{35}', 'Google API key'),
        (r'xox[baprs]-[0-9a-zA-Z]{10,48}', 'Slack token'),
    ]

    # Variable names that suggest secrets
    SECRET_VAR_NAMES = {
        'password', 'passwd', 'pwd', 'secret', 'apiKey', 'api_key',
        'accessToken', 'access_token', 'authToken', 'auth_token',
        'token', 'privateKey', 'private_key', 'secretKey', 'secret_key',
        'clientSecret', 'client_secret', 'appSecret', 'app_secret'
    }

    # Dangerous functions that can lead to XSS
    XSS_SINKS = {
        'innerHTML', 'outerHTML', 'insertAdjacentHTML',
        'document.write', 'document.writeln'
    }

    # ReDoS-prone regex patterns
    REDOS_PATTERNS = [
        r'(\w+)*',  # Nested quantifiers
        r'(\w*)*',
        r'(\w+)+',
        r'(\w*)+',
        r'(a|a)*',  # Alternation with overlap
        r'(a|ab)*',
    ]

    @property
    def analyzer_id(self) -> str:
        return 'javascript-security'

    @property
    def category(self) -> IssueCategory:
        return IssueCategory.SECURITY

    def analyze(self, parsed_module, source_code: str) -> List[CodeIssue]:
        """Run all JavaScript security checks"""
        issues = []

        # Try esprima AST parsing first
        if ESPRIMA_AVAILABLE:
            try:
                issues.extend(self._analyze_with_ast(source_code, parsed_module.file_path))
            except Exception:
                # Fallback to regex if AST parsing fails
                issues.extend(self._analyze_with_regex(source_code, parsed_module.file_path))
        else:
            # Use regex-based analysis
            issues.extend(self._analyze_with_regex(source_code, parsed_module.file_path))

        return self.apply_configuration(issues)

    def _analyze_with_ast(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Analyze using esprima AST"""
        issues = []

        try:
            tree = esprima.parseScript(source_code, {'loc': True, 'tolerant': True})
        except Exception:
            # If script parsing fails, try module parsing
            try:
                tree = esprima.parseModule(source_code, {'loc': True, 'tolerant': True})
            except Exception:
                return []

        # Walk the AST
        issues.extend(self._check_eval_usage_ast(tree, source_code, file_path))
        issues.extend(self._check_xss_sinks_ast(tree, source_code, file_path))
        issues.extend(self._check_prototype_pollution_ast(tree, source_code, file_path))

        return issues

    def _analyze_with_regex(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Analyze using regex patterns (fallback)"""
        issues = []

        issues.extend(self._check_eval_usage(source_code, file_path))
        issues.extend(self._check_xss_vulnerabilities(source_code, file_path))
        issues.extend(self._check_prototype_pollution(source_code, file_path))
        issues.extend(self._check_unsafe_regex(source_code, file_path))
        issues.extend(self._check_hardcoded_secrets(source_code, file_path))

        return issues

    # ============================================================================
    # AST-based Checks
    # ============================================================================

    def _check_eval_usage_ast(self, tree, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect eval() usage via AST"""
        issues = []

        def walk(node):
            if isinstance(node, nodes.CallExpression):
                # Direct eval()
                if isinstance(node.callee, nodes.Identifier) and node.callee.name == 'eval':
                    line_num = node.loc.start.line if hasattr(node, 'loc') else None
                    issues.append(self.create_issue(
                        rule_id='JS-SEC001',
                        severity=IssueSeverity.CRITICAL,
                        title='Use of eval() detected',
                        description='eval() executes arbitrary code and is extremely dangerous. '
                                   'It can lead to code injection vulnerabilities if user input is involved.',
                        file_path=file_path,
                        line_number=line_num,
                        code_snippet=self.extract_code_snippet(source_code, line_num) if line_num else None,
                        suggestion='Avoid eval(). Use JSON.parse() for parsing JSON, or refactor to use safer alternatives.'
                    ))

                # Function constructor (similar to eval)
                elif isinstance(node.callee, nodes.Identifier) and node.callee.name == 'Function':
                    line_num = node.loc.start.line if hasattr(node, 'loc') else None
                    issues.append(self.create_issue(
                        rule_id='JS-SEC001',
                        severity=IssueSeverity.CRITICAL,
                        title='Use of Function constructor detected',
                        description='Function constructor with string arguments acts like eval() and poses similar security risks.',
                        file_path=file_path,
                        line_number=line_num,
                        code_snippet=self.extract_code_snippet(source_code, line_num) if line_num else None,
                        suggestion='Use regular function declarations instead of Function constructor.'
                    ))

            # Recursively walk child nodes
            for key in dir(node):
                if key.startswith('_'):
                    continue
                value = getattr(node, key, None)
                if isinstance(value, nodes.Node):
                    walk(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, nodes.Node):
                            walk(item)

        walk(tree)
        return issues

    def _check_xss_sinks_ast(self, tree, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect XSS sinks via AST"""
        issues = []

        def walk(node):
            # innerHTML, outerHTML assignments
            if isinstance(node, nodes.AssignmentExpression):
                if isinstance(node.left, nodes.MemberExpression):
                    if hasattr(node.left.property, 'name'):
                        prop_name = node.left.property.name
                        if prop_name in ['innerHTML', 'outerHTML']:
                            line_num = node.loc.start.line if hasattr(node, 'loc') else None
                            issues.append(self.create_issue(
                                rule_id='JS-SEC002',
                                severity=IssueSeverity.ERROR,
                                title=f'Unsafe {prop_name} assignment (XSS)',
                                description=f'Assigning unsanitized data to {prop_name} can lead to XSS attacks. '
                                           'User input should always be sanitized before insertion into the DOM.',
                                file_path=file_path,
                                line_number=line_num,
                                code_snippet=self.extract_code_snippet(source_code, line_num) if line_num else None,
                                suggestion='Use textContent instead, or sanitize input with DOMPurify or similar library.'
                            ))

            # document.write()
            elif isinstance(node, nodes.CallExpression):
                if isinstance(node.callee, nodes.MemberExpression):
                    if (hasattr(node.callee.object, 'name') and
                        node.callee.object.name == 'document' and
                        hasattr(node.callee.property, 'name') and
                        node.callee.property.name in ['write', 'writeln']):
                        line_num = node.loc.start.line if hasattr(node, 'loc') else None
                        issues.append(self.create_issue(
                            rule_id='JS-SEC003',
                            severity=IssueSeverity.WARNING,
                            title='Use of document.write() (XSS)',
                            description='document.write() can introduce XSS vulnerabilities and can overwrite the entire page.',
                            file_path=file_path,
                            line_number=line_num,
                            code_snippet=self.extract_code_snippet(source_code, line_num) if line_num else None,
                            suggestion='Use modern DOM methods like createElement() and appendChild() instead.'
                        ))

            # Recursive walk
            for key in dir(node):
                if key.startswith('_'):
                    continue
                value = getattr(node, key, None)
                if isinstance(value, nodes.Node):
                    walk(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, nodes.Node):
                            walk(item)

        walk(tree)
        return issues

    def _check_prototype_pollution_ast(self, tree, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect prototype pollution via AST"""
        issues = []

        def walk(node):
            # obj[key] = value where key is user-controlled
            if isinstance(node, nodes.AssignmentExpression):
                if isinstance(node.left, nodes.MemberExpression) and node.left.computed:
                    # Check if property name could be __proto__ or prototype
                    line_num = node.loc.start.line if hasattr(node, 'loc') else None
                    snippet = self.extract_code_snippet(source_code, line_num) if line_num else ''

                    if '__proto__' in snippet or 'prototype' in snippet:
                        issues.append(self.create_issue(
                            rule_id='JS-SEC004',
                            severity=IssueSeverity.ERROR,
                            title='Potential prototype pollution',
                            description='Dynamic property assignment can lead to prototype pollution if the key is user-controlled. '
                                       'Attackers can modify Object.prototype affecting all objects.',
                            file_path=file_path,
                            line_number=line_num,
                            code_snippet=snippet,
                            suggestion='Validate property names and avoid setting __proto__ or prototype. '
                                      'Use Object.create(null) for dictionaries or Map instead of plain objects.'
                        ))

            # Recursive walk
            for key in dir(node):
                if key.startswith('_'):
                    continue
                value = getattr(node, key, None)
                if isinstance(value, nodes.Node):
                    walk(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, nodes.Node):
                            walk(item)

        walk(tree)
        return issues

    # ============================================================================
    # Regex-based Checks (Fallback)
    # ============================================================================

    def _check_eval_usage(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect eval() and Function() usage"""
        issues = []

        # Check for eval()
        for match in re.finditer(r'\beval\s*\(', source_code):
            line_num = source_code[:match.start()].count('\n') + 1
            issues.append(self.create_issue(
                rule_id='JS-SEC001',
                severity=IssueSeverity.CRITICAL,
                title='Use of eval() detected',
                description='eval() executes arbitrary code and is extremely dangerous.',
                file_path=file_path,
                line_number=line_num,
                code_snippet=self.extract_code_snippet(source_code, line_num),
                suggestion='Avoid eval(). Use JSON.parse() or safer alternatives.'
            ))

        # Check for Function constructor
        for match in re.finditer(r'new\s+Function\s*\(', source_code):
            line_num = source_code[:match.start()].count('\n') + 1
            issues.append(self.create_issue(
                rule_id='JS-SEC001',
                severity=IssueSeverity.CRITICAL,
                title='Use of Function constructor detected',
                description='Function constructor with string arguments acts like eval().',
                file_path=file_path,
                line_number=line_num,
                code_snippet=self.extract_code_snippet(source_code, line_num),
                suggestion='Use regular function declarations.'
            ))

        return issues

    def _check_xss_vulnerabilities(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect XSS vulnerabilities"""
        issues = []

        # innerHTML assignment
        for match in re.finditer(r'\.innerHTML\s*=', source_code):
            line_num = source_code[:match.start()].count('\n') + 1
            issues.append(self.create_issue(
                rule_id='JS-SEC002',
                severity=IssueSeverity.ERROR,
                title='Unsafe innerHTML assignment (XSS)',
                description='Assigning to innerHTML with unsanitized data can lead to XSS attacks.',
                file_path=file_path,
                line_number=line_num,
                code_snippet=self.extract_code_snippet(source_code, line_num),
                suggestion='Use textContent or sanitize with DOMPurify.'
            ))

        # document.write()
        for match in re.finditer(r'document\.write(?:ln)?\s*\(', source_code):
            line_num = source_code[:match.start()].count('\n') + 1
            issues.append(self.create_issue(
                rule_id='JS-SEC003',
                severity=IssueSeverity.WARNING,
                title='Use of document.write() (XSS)',
                description='document.write() can introduce XSS vulnerabilities.',
                file_path=file_path,
                line_number=line_num,
                code_snippet=self.extract_code_snippet(source_code, line_num),
                suggestion='Use modern DOM methods instead.'
            ))

        return issues

    def _check_prototype_pollution(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect prototype pollution risks"""
        issues = []

        # __proto__ assignment
        for match in re.finditer(r'__proto__\s*[=:]', source_code):
            line_num = source_code[:match.start()].count('\n') + 1
            issues.append(self.create_issue(
                rule_id='JS-SEC004',
                severity=IssueSeverity.ERROR,
                title='Prototype pollution via __proto__',
                description='Modifying __proto__ can affect all objects and lead to security vulnerabilities.',
                file_path=file_path,
                line_number=line_num,
                code_snippet=self.extract_code_snippet(source_code, line_num),
                suggestion='Use Object.create(null) or Map for dictionaries.'
            ))

        return issues

    def _check_unsafe_regex(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect potentially unsafe regular expressions (ReDoS)"""
        issues = []

        # Find regex literals
        regex_pattern = r'/([^/\\]|\\.)*/[gimsuvy]*'
        for match in re.finditer(regex_pattern, source_code):
            regex_content = match.group(0)

            # Check for nested quantifiers (ReDoS risk)
            if re.search(r'\([^)]*[*+]\)[*+]', regex_content):
                line_num = source_code[:match.start()].count('\n') + 1
                issues.append(self.create_issue(
                    rule_id='JS-SEC005',
                    severity=IssueSeverity.WARNING,
                    title='Potentially unsafe regex (ReDoS)',
                    description='This regex contains nested quantifiers which can cause catastrophic backtracking (ReDoS attack).',
                    file_path=file_path,
                    line_number=line_num,
                    code_snippet=self.extract_code_snippet(source_code, line_num),
                    suggestion='Simplify the regex pattern or add limits to prevent excessive backtracking.'
                ))

        return issues

    def _check_hardcoded_secrets(self, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect hardcoded secrets and credentials"""
        issues = []

        # Check for secret patterns
        for pattern, secret_type in self.SECRET_PATTERNS:
            for match in re.finditer(pattern, source_code):
                line_num = source_code[:match.start()].count('\n') + 1
                issues.append(self.create_issue(
                    rule_id='JS-SEC006',
                    severity=IssueSeverity.CRITICAL,
                    title=f'Hardcoded {secret_type} detected',
                    description=f'Found what appears to be a hardcoded {secret_type}. '
                               'Secrets should never be committed to source code.',
                    file_path=file_path,
                    line_number=line_num,
                    code_snippet=self.extract_code_snippet(source_code, line_num),
                    suggestion='Use environment variables or a secrets management system.'
                ))

        # Check for suspicious variable names
        for var_name in self.SECRET_VAR_NAMES:
            pattern = rf'\b(?:const|let|var)\s+{var_name}\s*=\s*[\'"][^\'"]+[\'"]'
            for match in re.finditer(pattern, source_code, re.IGNORECASE):
                line_num = source_code[:match.start()].count('\n') + 1
                issues.append(self.create_issue(
                    rule_id='JS-SEC006',
                    severity=IssueSeverity.WARNING,
                    title='Potential hardcoded credential',
                    description=f'Variable "{var_name}" appears to contain a hardcoded value. '
                               'Credentials should be stored securely.',
                    file_path=file_path,
                    line_number=line_num,
                    code_snippet=self.extract_code_snippet(source_code, line_num),
                    suggestion='Use environment variables via process.env or a config service.'
                ))

        return issues
