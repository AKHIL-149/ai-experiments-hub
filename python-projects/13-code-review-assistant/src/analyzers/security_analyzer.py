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

    def get_rule_ids(self) -> List[str]:
        """Get all rule IDs this analyzer can detect"""
        return ['SEC002', 'SEC003', 'SEC004']
