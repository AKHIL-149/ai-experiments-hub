"""Security analyzer for detecting vulnerabilities in Python code"""
import ast
import re
from typing import List
from .base_analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity


class SecurityAnalyzer(BaseAnalyzer):
    """Detects security vulnerabilities in code"""

    # Patterns for detecting hardcoded secrets
    SECRET_PATTERNS = [
        (r'sk_live_[a-zA-Z0-9]{24,}', 'Stripe API key'),
        (r'sk_test_[a-zA-Z0-9]{24,}', 'Stripe test key'),
        (r'ghp_[a-zA-Z0-9]{36,}', 'GitHub personal access token'),
        (r'gho_[a-zA-Z0-9]{36,}', 'GitHub OAuth token'),
        (r'AKIA[0-9A-Z]{16}', 'AWS access key'),
        (r'AIza[0-9A-Za-z\\-_]{35}', 'Google API key'),
        (r'xox[baprs]-[0-9a-zA-Z]{10,48}', 'Slack token'),
        (r'[a-zA-Z0-9_-]{32,}', 'Generic API key pattern'),
    ]

    # Variable names that suggest secrets
    SECRET_VAR_NAMES = {
        'password', 'passwd', 'pwd', 'secret', 'api_key', 'apikey',
        'access_token', 'auth_token', 'token', 'private_key', 'secret_key',
        'client_secret', 'app_secret', 'encryption_key', 'auth_key'
    }

    @property
    def analyzer_id(self) -> str:
        return 'security'

    @property
    def category(self) -> IssueCategory:
        return IssueCategory.SECURITY

    def analyze(self, parsed_module, source_code: str) -> List[CodeIssue]:
        """Run all security checks"""
        issues = []

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return issues

        issues.extend(self._check_command_injection(tree, source_code, parsed_module.file_path))
        issues.extend(self._check_hardcoded_secrets(tree, source_code, parsed_module.file_path))
        issues.extend(self._check_path_traversal(tree, source_code, parsed_module.file_path))
        issues.extend(self._check_unsafe_deserialization(tree, source_code, parsed_module.file_path))
        issues.extend(self._check_weak_crypto(tree, source_code, parsed_module.file_path))

        return issues

    def _check_command_injection(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect command injection vulnerabilities"""
        issues = []

        for node in ast.walk(tree):
            # SEC002: os.system() with concatenation or variables
            if isinstance(node, ast.Call):
                if self._is_os_system_call(node):
                    issue = self._check_dangerous_os_system(node, source_code, file_path)
                    if issue:
                        issues.append(issue)

                # SEC003: subprocess with shell=True
                elif self._is_subprocess_call(node):
                    issue = self._check_subprocess_shell(node, source_code, file_path)
                    if issue:
                        issues.append(issue)

        return issues

    def _is_os_system_call(self, node: ast.Call) -> bool:
        """Check if node is os.system() call"""
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == 'system' and isinstance(node.func.value, ast.Name):
                if node.func.value.id == 'os':
                    return True
        return False

    def _check_dangerous_os_system(self, node: ast.Call, source_code: str, file_path: str) -> CodeIssue:
        """Check if os.system() call is dangerous"""
        if not node.args:
            return None

        arg = node.args[0]

        # Check for string concatenation
        if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
            snippet = self.extract_code_snippet(source_code, node.lineno)
            return self.create_issue(
                rule_id='SEC002',
                severity=IssueSeverity.CRITICAL,
                title='Command injection via os.system()',
                description='Using os.system() with string concatenation allows command injection attacks. '
                           'An attacker can inject malicious commands by manipulating the input.',
                file_path=file_path,
                line_number=node.lineno,
                code_snippet=snippet,
                suggestion='Use subprocess.run() with a list of arguments instead of shell commands. '
                          'Example: subprocess.run(["ls", user_input]) instead of os.system("ls " + user_input)',
                confidence=0.95
            )

        # Check for f-strings or variables
        if isinstance(arg, (ast.JoinedStr, ast.Name, ast.FormattedValue)):
            snippet = self.extract_code_snippet(source_code, node.lineno)
            return self.create_issue(
                rule_id='SEC002',
                severity=IssueSeverity.CRITICAL,
                title='Command injection via os.system()',
                description='Using os.system() with variables or f-strings can lead to command injection. '
                           'User input in the command can be exploited to run arbitrary commands.',
                file_path=file_path,
                line_number=node.lineno,
                code_snippet=snippet,
                suggestion='Use subprocess.run() with argument list instead. Never pass user input directly to shell commands.',
                confidence=0.9
            )

        return None

    def _is_subprocess_call(self, node: ast.Call) -> bool:
        """Check if node is subprocess call"""
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in ['call', 'run', 'Popen', 'check_call', 'check_output']:
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess':
                    return True
        return False

    def _check_subprocess_shell(self, node: ast.Call, source_code: str, file_path: str) -> CodeIssue:
        """Check for subprocess with shell=True"""
        for keyword in node.keywords:
            if keyword.arg == 'shell':
                if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    snippet = self.extract_code_snippet(source_code, node.lineno)
                    return self.create_issue(
                        rule_id='SEC003',
                        severity=IssueSeverity.ERROR,
                        title='Subprocess called with shell=True',
                        description='Using shell=True with subprocess enables shell injection attacks. '
                                   'The shell interprets special characters which can be exploited.',
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=snippet,
                        suggestion='Remove shell=True and pass command as a list: '
                                  'subprocess.run(["command", "arg1", "arg2"]) instead of '
                                  'subprocess.run("command arg1 arg2", shell=True)',
                        confidence=1.0
                    )
        return None

    def _check_hardcoded_secrets(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect hardcoded secrets in code"""
        issues = []

        for node in ast.walk(tree):
            # Check variable assignments
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        issue = self._check_secret_assignment(target.id, node.value, node.lineno, source_code, file_path)
                        if issue:
                            issues.append(issue)

            # Check annotated assignments (type hints)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    if node.value:
                        issue = self._check_secret_assignment(node.target.id, node.value, node.lineno, source_code, file_path)
                        if issue:
                            issues.append(issue)

        return issues

    def _check_secret_assignment(self, var_name: str, value_node: ast.AST, line_number: int, source_code: str, file_path: str) -> CodeIssue:
        """Check if variable assignment contains hardcoded secret"""
        # Check if variable name suggests it's a secret
        if not isinstance(value_node, ast.Constant):
            return None

        value = value_node.value
        if not isinstance(value, str):
            return None

        var_lower = var_name.lower()
        is_secret_var = any(secret in var_lower for secret in self.SECRET_VAR_NAMES)

        # Check variable name
        if is_secret_var:
            # Ignore empty strings and common test values
            if value and value not in ['', 'test', 'dummy', 'placeholder', 'changeme', 'YOUR_API_KEY_HERE']:
                snippet = self.extract_code_snippet(source_code, line_number)
                return self.create_issue(
                    rule_id='SEC004',
                    severity=IssueSeverity.CRITICAL,
                    title='Hardcoded secret detected',
                    description=f'Variable "{var_name}" appears to contain a hardcoded secret. '
                               'Hardcoded credentials in source code are a serious security risk. '
                               'They can be exposed in version control, logs, or backups.',
                    file_path=file_path,
                    line_number=line_number,
                    code_snippet=snippet,
                    suggestion='Use environment variables to store secrets: '
                              f'{var_name} = os.getenv("{var_name.upper()}") '
                              'or use a secrets management service.',
                    confidence=0.85,
                    secret_type='suspected_credential'
                )

        # Check value patterns for API keys
        for pattern, secret_type in self.SECRET_PATTERNS[:7]:  # Exclude generic pattern
            if re.search(pattern, value):
                snippet = self.extract_code_snippet(source_code, line_number)
                return self.create_issue(
                    rule_id='SEC004',
                    severity=IssueSeverity.CRITICAL,
                    title=f'Hardcoded {secret_type} detected',
                    description=f'Found what appears to be a hardcoded {secret_type}. '
                               'API keys and tokens should never be committed to source code. '
                               'They should be stored securely in environment variables or secret managers.',
                    file_path=file_path,
                    line_number=line_number,
                    code_snippet=snippet,
                    suggestion='Move this credential to an environment variable or use a secrets manager like AWS Secrets Manager, HashiCorp Vault, or Azure Key Vault.',
                    confidence=0.9,
                    secret_type=secret_type
                )

        return None

    def _check_path_traversal(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect path traversal vulnerabilities"""
        issues = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for open() with variables
                if self._is_file_open_call(node):
                    issue = self._check_dangerous_file_open(node, source_code, file_path)
                    if issue:
                        issues.append(issue)

                # Check for os.path.join with variables
                elif self._is_path_join_call(node):
                    issue = self._check_dangerous_path_join(node, source_code, file_path)
                    if issue:
                        issues.append(issue)

        return issues

    def _is_file_open_call(self, node: ast.Call) -> bool:
        """Check if node is open() call"""
        if isinstance(node.func, ast.Name) and node.func.id == 'open':
            return True
        return False

    def _check_dangerous_file_open(self, node: ast.Call, source_code: str, file_path: str) -> CodeIssue:
        """Check if open() call has path traversal risk"""
        if not node.args:
            return None

        arg = node.args[0]

        # Check for string concatenation or variables
        if isinstance(arg, (ast.BinOp, ast.JoinedStr, ast.Name, ast.FormattedValue)):
            snippet = self.extract_code_snippet(source_code, node.lineno)
            return self.create_issue(
                rule_id='SEC005',
                severity=IssueSeverity.ERROR,
                title='Path traversal risk in file operation',
                description='Using open() with user-controlled paths can lead to path traversal attacks. '
                           'An attacker could access files outside the intended directory by using "../" sequences.',
                file_path=file_path,
                line_number=node.lineno,
                code_snippet=snippet,
                suggestion='Validate and sanitize file paths. Use os.path.normpath() and verify the path stays '
                          'within allowed directories. Example: base_dir = "/safe/path"; '
                          'safe_path = os.path.normpath(os.path.join(base_dir, user_input)); '
                          'if not safe_path.startswith(base_dir): raise ValueError()',
                confidence=0.75
            )

        return None

    def _is_path_join_call(self, node: ast.Call) -> bool:
        """Check if node is os.path.join() call"""
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == 'join':
                if isinstance(node.func.value, ast.Attribute):
                    if node.func.value.attr == 'path' and isinstance(node.func.value.value, ast.Name):
                        if node.func.value.value.id == 'os':
                            return True
        return False

    def _check_dangerous_path_join(self, node: ast.Call, source_code: str, file_path: str) -> CodeIssue:
        """Check if os.path.join() has path traversal risk"""
        # Check if any argument is a variable (not a constant)
        has_variable = False
        for arg in node.args:
            if isinstance(arg, (ast.Name, ast.JoinedStr, ast.FormattedValue)):
                has_variable = True
                break

        if has_variable:
            snippet = self.extract_code_snippet(source_code, node.lineno)
            return self.create_issue(
                rule_id='SEC005',
                severity=IssueSeverity.WARNING,
                title='Potential path traversal in os.path.join()',
                description='Using os.path.join() with user input can be exploited with absolute paths or "../" sequences. '
                           'The function does not prevent path traversal attacks on its own.',
                file_path=file_path,
                line_number=node.lineno,
                code_snippet=snippet,
                suggestion='Validate user input before using in paths. Use os.path.basename() to strip directory components, '
                          'or check that the result stays within allowed directories.',
                confidence=0.65
            )

        return None

    def _check_unsafe_deserialization(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect unsafe deserialization vulnerabilities"""
        issues = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for pickle.loads/load
                if self._is_pickle_call(node):
                    snippet = self.extract_code_snippet(source_code, node.lineno)
                    issues.append(self.create_issue(
                        rule_id='SEC006',
                        severity=IssueSeverity.CRITICAL,
                        title='Unsafe deserialization with pickle',
                        description='Using pickle to deserialize untrusted data can execute arbitrary code. '
                                   'Pickle is not secure against malicious data and should never be used with untrusted input.',
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=snippet,
                        suggestion='Use JSON or other safe serialization formats for untrusted data. '
                                  'Only use pickle with data from trusted sources in controlled environments.',
                        confidence=0.9
                    ))

                # Check for eval()
                elif self._is_eval_call(node):
                    snippet = self.extract_code_snippet(source_code, node.lineno)
                    issues.append(self.create_issue(
                        rule_id='SEC006',
                        severity=IssueSeverity.CRITICAL,
                        title='Use of eval() with user input',
                        description='eval() executes arbitrary Python code and is extremely dangerous with untrusted input. '
                                   'An attacker can execute any Python code on your system.',
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=snippet,
                        suggestion='Never use eval() with user input. Use ast.literal_eval() for safe evaluation of literals, '
                                  'or parse/validate input explicitly.',
                        confidence=1.0
                    ))

                # Check for exec()
                elif self._is_exec_call(node):
                    snippet = self.extract_code_snippet(source_code, node.lineno)
                    issues.append(self.create_issue(
                        rule_id='SEC006',
                        severity=IssueSeverity.CRITICAL,
                        title='Use of exec() with user input',
                        description='exec() executes arbitrary Python code and is extremely dangerous. '
                                   'It should never be used with untrusted input.',
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=snippet,
                        suggestion='Avoid exec() entirely. Redesign your code to use safer alternatives like '
                                  'function dispatch dictionaries or configuration files.',
                        confidence=1.0
                    ))

        return issues

    def _is_pickle_call(self, node: ast.Call) -> bool:
        """Check if node is pickle.loads() or pickle.load()"""
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in ['loads', 'load']:
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'pickle':
                    return True
        return False

    def _is_eval_call(self, node: ast.Call) -> bool:
        """Check if node is eval()"""
        if isinstance(node.func, ast.Name) and node.func.id == 'eval':
            return True
        return False

    def _is_exec_call(self, node: ast.Call) -> bool:
        """Check if node is exec()"""
        if isinstance(node.func, ast.Name) and node.func.id == 'exec':
            return True
        return False

    def _check_weak_crypto(self, tree: ast.AST, source_code: str, file_path: str) -> List[CodeIssue]:
        """Detect weak cryptographic algorithms"""
        issues = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for hashlib.md5() or hashlib.sha1()
                if self._is_weak_hash_call(node):
                    hash_type = node.func.attr
                    snippet = self.extract_code_snippet(source_code, node.lineno)
                    issues.append(self.create_issue(
                        rule_id='SEC007',
                        severity=IssueSeverity.WARNING,
                        title=f'Weak cryptographic hash: {hash_type.upper()}',
                        description=f'{hash_type.upper()} is cryptographically weak and should not be used for security purposes. '
                                   'It is vulnerable to collision attacks and is considered broken for cryptographic use.',
                        file_path=file_path,
                        line_number=node.lineno,
                        code_snippet=snippet,
                        suggestion='Use SHA-256 or SHA-3 for cryptographic purposes: hashlib.sha256() or hashlib.sha3_256(). '
                                  'Only use MD5/SHA1 for non-security purposes like checksums.',
                        confidence=1.0
                    ))

        return issues

    def _is_weak_hash_call(self, node: ast.Call) -> bool:
        """Check if node is hashlib.md5() or hashlib.sha1()"""
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in ['md5', 'sha1']:
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'hashlib':
                    return True
        return False

    def get_rule_ids(self) -> List[str]:
        """Get all rule IDs this analyzer can detect"""
        return ['SEC002', 'SEC003', 'SEC004', 'SEC005', 'SEC006', 'SEC007']
