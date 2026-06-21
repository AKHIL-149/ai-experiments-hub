"""
Java Security Analyzer
Detects security vulnerabilities in Java code
"""

import re
from typing import List, Optional
from ..parsers.models import ParsedModule, FunctionInfo
from .base_analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity


class JavaSecurityAnalyzer(BaseAnalyzer):
    """
    Analyzes Java code for security vulnerabilities.

    Rules:
    - JAVA-SEC001: SQL Injection (string concatenation in queries)
    - JAVA-SEC002: Command Injection (Runtime.exec, ProcessBuilder)
    - JAVA-SEC003: Path Traversal (file operations with user input)
    - JAVA-SEC004: Unsafe Deserialization (ObjectInputStream)
    - JAVA-SEC005: XXE (XML External Entity)
    - JAVA-SEC006: Hardcoded Secrets
    - JAVA-SEC007: Weak Cryptography (MD5, SHA1, DES)
    - JAVA-SEC008: LDAP Injection
    """

    def __init__(self):
        super().__init__()
        self.name = "JavaSecurityAnalyzer"
        self.language = "java"

    @property
    def analyzer_id(self) -> str:
        return 'java_security'

    @property
    def category(self) -> IssueCategory:
        return IssueCategory.SECURITY

    def analyze(self, parsed_module: ParsedModule, source_code: str) -> List[CodeIssue]:
        """Run all security checks"""
        if parsed_module.language != 'java':
            return []

        file_path = parsed_module.file_path
        issues = []
        issues.extend(self._check_sql_injection(source_code, file_path))
        issues.extend(self._check_command_injection(source_code, file_path))
        issues.extend(self._check_path_traversal(source_code, file_path))
        issues.extend(self._check_unsafe_deserialization(source_code, file_path))
        issues.extend(self._check_xxe(source_code, file_path))
        issues.extend(self._check_hardcoded_secrets(source_code, file_path))
        issues.extend(self._check_weak_crypto(source_code, file_path))
        issues.extend(self._check_ldap_injection(source_code, file_path))

        return issues

    def _check_sql_injection(self, code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SEC001: Detect SQL injection vulnerabilities

        Patterns:
        - String concatenation in SQL queries
        - Statement.executeQuery/executeUpdate with concatenation
        - No PreparedStatement usage
        """
        issues = []

        # Pattern 1: Direct string concatenation with SQL keywords
        sql_concat_patterns = [
            r'executeQuery\s*\(\s*"[^"]*"\s*\+',
            r'executeUpdate\s*\(\s*"[^"]*"\s*\+',
            r'execute\s*\(\s*"[^"]*"\s*\+',
            r'"(?:SELECT|INSERT|UPDATE|DELETE)[^"]*"\s*\+\s*\w+',
            r'\w+\s*\+\s*"[^"]*(?:WHERE|FROM|VALUES)[^"]*"',
        ]

        for pattern in sql_concat_patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                line_number = code[:match.start()].count('\n') + 1
                issues.append(CodeIssue(
                    category=IssueCategory.SECURITY,
                    severity=IssueSeverity.CRITICAL,
                    rule_id='JAVA-SEC001',
                    title='SQL Injection Risk',
                    description=(
                        'SQL query uses string concatenation, which is vulnerable to SQL injection. '
                        'Use PreparedStatement with parameterized queries instead.'
                    ),
                    file_path=file_path,
                    line_number=line_number,
                    code_snippet=self._get_line(code, line_number),
                    suggestion='Use PreparedStatement: PreparedStatement ps = conn.prepareStatement("SELECT * FROM users WHERE id = ?"); ps.setInt(1, userId);',
                    confidence=0.9
                ))

        # Pattern 2: String.format with SQL
        format_pattern = r'String\.format\s*\([^)]*(?:SELECT|INSERT|UPDATE|DELETE)[^)]*\)'
        for match in re.finditer(format_pattern, code, re.IGNORECASE):
            line_number = code[:match.start()].count('\n') + 1
            issues.append(CodeIssue(
                    file_path=file_path,
                category=IssueCategory.SECURITY,
                severity=IssueSeverity.CRITICAL,
                rule_id='JAVA-SEC001',
                title='SQL Injection Risk via String.format',
                description='SQL query uses String.format which can lead to SQL injection.',
                line_number=line_number,
                code_snippet=self._get_line(code, line_number),
                suggestion='Use PreparedStatement with parameterized queries',
                confidence=0.85
            ))

        return issues

    def _check_command_injection(self, code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SEC002: Detect command injection vulnerabilities

        Patterns:
        - Runtime.getRuntime().exec()
        - ProcessBuilder with user input
        """
        issues = []

        # Pattern 1: Runtime.exec
        exec_patterns = [
            r'Runtime\.getRuntime\(\)\.exec\s*\(',
            r'\.exec\s*\(\s*\w+',  # exec with variable
        ]

        for pattern in exec_patterns:
            for match in re.finditer(pattern, code):
                line_number = code[:match.start()].count('\n') + 1

                # Check if it's a hardcoded string (safer)
                line = self._get_line(code, line_number)
                is_hardcoded = bool(re.search(r'exec\s*\(\s*"[^"]*"', line))

                issues.append(CodeIssue(
                    category=IssueCategory.SECURITY,
                    severity=IssueSeverity.CRITICAL if not is_hardcoded else IssueSeverity.WARNING,
                    rule_id='JAVA-SEC002',
                    title='Command Injection Risk',
                    description=(
                        'Executing system commands can be dangerous if user input is involved. '
                        'Validate and sanitize all inputs, or use safer alternatives.'
                    ),
                    file_path=file_path,
                    line_number=line_number,
                    code_snippet=line,
                    suggestion='Validate input, use allowlist, or avoid shell commands entirely',
                    confidence=0.8 if not is_hardcoded else 0.6
                ))

        # Pattern 2: ProcessBuilder
        processbuilder_pattern = r'new\s+ProcessBuilder\s*\([^)]*\w+[^)]*\)'
        for match in re.finditer(processbuilder_pattern, code):
            line_number = code[:match.start()].count('\n') + 1
            line = self._get_line(code, line_number)

            # Skip if it's only hardcoded strings
            if not re.search(r'ProcessBuilder\s*\(\s*"[^"]*"\s*\)', line):
                issues.append(CodeIssue(
                    file_path=file_path,
                    category=IssueCategory.SECURITY,
                    severity=IssueSeverity.ERROR,
                    rule_id='JAVA-SEC002',
                    title='ProcessBuilder with Dynamic Input',
                    description='ProcessBuilder with variables may allow command injection',
                    line_number=line_number,
                    code_snippet=line,
                    suggestion='Validate all inputs against an allowlist',
                    confidence=0.75
                ))

        return issues

    def _check_path_traversal(self, code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SEC003: Detect path traversal vulnerabilities

        Patterns:
        - File operations with user input
        - Missing path canonicalization
        """
        issues = []

        # Pattern: File constructor with variables
        file_patterns = [
            r'new\s+File\s*\(\s*\w+',
            r'Files\.(?:readAllBytes|readAllLines|write)\s*\(\s*(?:Paths\.get|Path\.of)\s*\(\s*\w+',
            r'FileInputStream\s*\(\s*\w+',
            r'FileOutputStream\s*\(\s*\w+',
        ]

        for pattern in file_patterns:
            for match in re.finditer(pattern, code):
                line_number = code[:match.start()].count('\n') + 1
                line = self._get_line(code, line_number)

                # Check if canonical path is used nearby (safer)
                context = self._get_context(code, line_number, 5)
                has_canonical_check = bool(re.search(r'getCanonicalPath|normalize', context))

                if not has_canonical_check:
                    issues.append(CodeIssue(
                        category=IssueCategory.SECURITY,
                        severity=IssueSeverity.ERROR,
                        rule_id='JAVA-SEC003',
                        title='Path Traversal Risk',
                        description=(
                            'File operation with user input may allow path traversal attacks. '
                            'Validate and canonicalize file paths.'
                        ),
                        file_path=file_path,
                        line_number=line_number,
                        code_snippet=line,
                        suggestion='Use file.getCanonicalPath() and validate against allowed directories',
                        confidence=0.7
                    ))

        return issues

    def _check_unsafe_deserialization(self, code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SEC004: Detect unsafe deserialization

        Patterns:
        - ObjectInputStream.readObject()
        - XMLDecoder
        """
        issues = []

        # Pattern 1: ObjectInputStream.readObject()
        deserialize_pattern = r'ObjectInputStream.*\.readObject\s*\('
        for match in re.finditer(deserialize_pattern, code):
            line_number = code[:match.start()].count('\n') + 1
            issues.append(CodeIssue(
                category=IssueCategory.SECURITY,
                severity=IssueSeverity.CRITICAL,
                rule_id='JAVA-SEC004',
                title='Unsafe Deserialization',
                description=(
                    'Deserializing untrusted data can lead to remote code execution. '
                    'Avoid deserializing untrusted data or use safe alternatives like JSON.'
                ),
                file_path=file_path,
                line_number=line_number,
                code_snippet=self._get_line(code, line_number),
                suggestion='Use JSON (Jackson, Gson) instead of Java serialization',
                confidence=0.9
            ))

        # Pattern 2: XMLDecoder
        xmldecoder_pattern = r'new\s+XMLDecoder\s*\('
        for match in re.finditer(xmldecoder_pattern, code):
            line_number = code[:match.start()].count('\n') + 1
            issues.append(CodeIssue(
                    file_path=file_path,
                category=IssueCategory.SECURITY,
                severity=IssueSeverity.CRITICAL,
                rule_id='JAVA-SEC004',
                title='Unsafe XMLDecoder Usage',
                description='XMLDecoder is vulnerable to arbitrary code execution',
                line_number=line_number,
                code_snippet=self._get_line(code, line_number),
                suggestion='Use safer XML parsing libraries',
                confidence=0.95
            ))

        return issues

    def _check_xxe(self, code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SEC005: Detect XXE (XML External Entity) vulnerabilities

        Patterns:
        - DocumentBuilderFactory without secure settings
        - SAXParserFactory without secure settings
        """
        issues = []

        # Pattern 1: DocumentBuilderFactory
        dbf_pattern = r'DocumentBuilderFactory\.newInstance\s*\('
        for match in re.finditer(dbf_pattern, code):
            line_number = code[:match.start()].count('\n') + 1

            # Check if secure features are set
            context = self._get_context(code, line_number, 10)
            has_secure_processing = bool(re.search(
                r'setFeature.*(?:FEATURE_SECURE_PROCESSING|disallow-doctype-decl)',
                context
            ))

            if not has_secure_processing:
                issues.append(CodeIssue(
                    category=IssueCategory.SECURITY,
                    severity=IssueSeverity.CRITICAL,
                    rule_id='JAVA-SEC005',
                    title='XXE Vulnerability',
                    description=(
                        'XML parser may be vulnerable to XXE attacks. '
                        'Disable external entity processing.'
                    ),
                    file_path=file_path,
                    line_number=line_number,
                    code_snippet=self._get_line(code, line_number),
                    suggestion='Set feature: dbf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);',
                    confidence=0.8
                ))

        # Pattern 2: SAXParserFactory
        sax_pattern = r'SAXParserFactory\.newInstance\s*\('
        for match in re.finditer(sax_pattern, code):
            line_number = code[:match.start()].count('\n') + 1
            context = self._get_context(code, line_number, 10)
            has_secure_processing = bool(re.search(r'setFeature.*FEATURE_SECURE_PROCESSING', context))

            if not has_secure_processing:
                issues.append(CodeIssue(
                    file_path=file_path,
                    category=IssueCategory.SECURITY,
                    severity=IssueSeverity.CRITICAL,
                    rule_id='JAVA-SEC005',
                    title='XXE Vulnerability in SAXParser',
                    description='SAX parser needs secure configuration to prevent XXE',
                    line_number=line_number,
                    code_snippet=self._get_line(code, line_number),
                    suggestion='Enable secure processing features',
                    confidence=0.8
                ))

        return issues

    def _check_hardcoded_secrets(self, code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SEC006: Detect hardcoded secrets

        Patterns:
        - API keys
        - Passwords
        - Tokens
        - Cryptographic keys
        """
        issues = []

        # Secret patterns (similar to JavaScript analyzer)
        secret_patterns = [
            (r'(?:api[_-]?key|apikey)\s*=\s*["\']([a-zA-Z0-9]{20,})["\']', 'API Key'),
            (r'(?:password|passwd|pwd)\s*=\s*["\']([^"\']{6,})["\']', 'Password'),
            (r'(?:secret|token)\s*=\s*["\']([a-zA-Z0-9]{20,})["\']', 'Secret Token'),
            (r'jdbc:.*://.*:.*@', 'Database Connection String with Credentials'),
            (r'sk_live_[a-zA-Z0-9]{24,}', 'Stripe API Key'),
            (r'ghp_[a-zA-Z0-9]{36,}', 'GitHub Personal Access Token'),
            (r'AKIA[0-9A-Z]{16}', 'AWS Access Key'),
            (r'AIza[0-9A-Za-z-_]{35}', 'Google API Key'),
        ]

        for pattern, secret_type in secret_patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                line_number = code[:match.start()].count('\n') + 1

                # Skip test files and examples
                line = self._get_line(code, line_number)
                if self._is_test_or_example(line):
                    continue

                issues.append(CodeIssue(
                    file_path=file_path,
                    category=IssueCategory.SECURITY,
                    severity=IssueSeverity.CRITICAL,
                    rule_id='JAVA-SEC006',
                    title=f'Hardcoded {secret_type}',
                    description=(
                        f'Hardcoded {secret_type.lower()} detected. '
                        'Use environment variables or secure configuration management.'
                    ),
                    line_number=line_number,
                    code_snippet=self._sanitize_secret(line),
                    suggestion='Use System.getenv() or a configuration service',
                    confidence=0.85
                ))

        return issues

    def _check_weak_crypto(self, code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SEC007: Detect weak cryptography

        Patterns:
        - MD5, SHA1
        - DES, RC4
        - ECB mode
        """
        issues = []

        # Weak hash algorithms
        weak_hash_patterns = [
            (r'MessageDigest\.getInstance\s*\(\s*["\']MD5["\']', 'MD5', IssueSeverity.ERROR),
            (r'MessageDigest\.getInstance\s*\(\s*["\']SHA-?1["\']', 'SHA-1', IssueSeverity.WARNING),
        ]

        for pattern, algo, severity in weak_hash_patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                line_number = code[:match.start()].count('\n') + 1
                issues.append(CodeIssue(
                    file_path=file_path,
                    category=IssueCategory.SECURITY,
                    severity=severity,
                    rule_id='JAVA-SEC007',
                    title=f'Weak Hash Algorithm: {algo}',
                    description=f'{algo} is cryptographically weak. Use SHA-256 or stronger.',
                    line_number=line_number,
                    code_snippet=self._get_line(code, line_number),
                    suggestion='Use MessageDigest.getInstance("SHA-256")',
                    confidence=0.95
                ))

        # Weak encryption algorithms
        weak_cipher_patterns = [
            (r'Cipher\.getInstance\s*\(\s*["\']DES[/"\'"]', 'DES', IssueSeverity.CRITICAL),
            (r'Cipher\.getInstance\s*\(\s*["\']RC4[/"\'"]', 'RC4', IssueSeverity.CRITICAL),
            (r'Cipher\.getInstance\s*\(\s*["\'][^"\']*ECB[^"\']*["\']', 'ECB Mode', IssueSeverity.ERROR),
        ]

        for pattern, algo, severity in weak_cipher_patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                line_number = code[:match.start()].count('\n') + 1
                issues.append(CodeIssue(
                    file_path=file_path,
                    category=IssueCategory.SECURITY,
                    severity=severity,
                    rule_id='JAVA-SEC007',
                    title=f'Weak Encryption: {algo}',
                    description=f'{algo} is insecure. Use AES with GCM or CBC mode.',
                    line_number=line_number,
                    code_snippet=self._get_line(code, line_number),
                    suggestion='Use Cipher.getInstance("AES/GCM/NoPadding")',
                    confidence=0.95
                ))

        return issues

    def _check_ldap_injection(self, code: str, file_path: str) -> List[CodeIssue]:
        """
        JAVA-SEC008: Detect LDAP injection vulnerabilities

        Patterns:
        - String concatenation in LDAP queries
        """
        issues = []

        # LDAP query patterns with concatenation
        ldap_patterns = [
            r'new\s+InitialDirContext.*search\s*\([^)]*\+',
            r'\.search\s*\(\s*"[^"]*"\s*\+',
        ]

        for pattern in ldap_patterns:
            for match in re.finditer(pattern, code):
                line_number = code[:match.start()].count('\n') + 1
                issues.append(CodeIssue(
                    category=IssueCategory.SECURITY,
                    severity=IssueSeverity.ERROR,
                    rule_id='JAVA-SEC008',
                    title='LDAP Injection Risk',
                    description=(
                        'LDAP query uses string concatenation. '
                        'Escape user input to prevent LDAP injection.'
                    ),
                    file_path=file_path,
                    line_number=line_number,
                    code_snippet=self._get_line(code, line_number),
                    suggestion='Escape special LDAP characters in user input',
                    confidence=0.75
                ))

        return issues

    def _get_line(self, code: str, line_number: int) -> str:
        """Get a specific line from code"""
        lines = code.split('\n')
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].strip()
        return ""

    def _get_context(self, code: str, line_number: int, context_lines: int = 5) -> str:
        """Get surrounding lines of code"""
        lines = code.split('\n')
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)
        return '\n'.join(lines[start:end])

    def _is_test_or_example(self, line: str) -> bool:
        """Check if line is from test or example"""
        test_indicators = ['test', 'example', 'demo', 'TODO', 'FIXME', '//']
        return any(indicator in line.lower() for indicator in test_indicators)

    def _sanitize_secret(self, line: str) -> str:
        """Hide actual secret values"""
        # Replace long alphanumeric strings with asterisks
        return re.sub(r'["\']([a-zA-Z0-9]{10,})["\']', r'"***REDACTED***"', line)
