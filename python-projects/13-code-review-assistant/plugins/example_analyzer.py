"""
Example Analyzer Plugin

This is a sample plugin that demonstrates how to create custom analyzer plugins.
"""

import re
from typing import List, Dict, Any

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.plugin_base import AnalyzerPlugin, PluginMetadata, PluginType, PluginHook


class ExampleSecurityAnalyzer(AnalyzerPlugin):
    """
    Example security analyzer plugin that detects common security issues.
    """

    def __init__(self):
        metadata = PluginMetadata(
            name="example-security-analyzer",
            version="1.0.0",
            author="Code Review Assistant",
            description="Example plugin that detects hardcoded credentials and dangerous functions",
            plugin_type=PluginType.ANALYZER,
            supported_languages=["python", "javascript"],
            homepage="https://example.com/plugins/security-analyzer",
            license="MIT"
        )
        super().__init__(metadata)

        # Register hooks
        self.register_hook(PluginHook.ON_ISSUE_FOUND, self.on_issue_found)

    def initialize(self) -> bool:
        """Initialize the plugin"""
        print(f"Initializing {self.metadata.name} plugin...")
        return True

    def shutdown(self) -> bool:
        """Shutdown the plugin"""
        print(f"Shutting down {self.metadata.name} plugin...")
        return True

    def analyze(self, code: str, language: str, file_path: str) -> List[Dict[str, Any]]:
        """
        Analyze code for security issues.

        Args:
            code: Code to analyze
            language: Programming language
            file_path: File path

        Returns:
            List of issues found
        """
        issues = []

        # Check for hardcoded credentials
        credential_patterns = [
            (r'password\s*=\s*["\'].+["\']', 'Hardcoded password detected'),
            (r'api[_-]?key\s*=\s*["\'].+["\']', 'Hardcoded API key detected'),
            (r'secret\s*=\s*["\'].+["\']', 'Hardcoded secret detected'),
            (r'token\s*=\s*["\'].+["\']', 'Hardcoded token detected'),
        ]

        lines = code.split('\n')
        for line_num, line in enumerate(lines, 1):
            for pattern, message in credential_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        'type': 'security',
                        'severity': 'critical',
                        'message': message,
                        'file': file_path,
                        'line': line_num,
                        'code_snippet': line.strip(),
                        'plugin': self.metadata.name
                    })

        # Check for dangerous functions (Python)
        if language == 'python':
            dangerous_functions = [
                (r'\beval\s*\(', 'Dangerous use of eval()'),
                (r'\bexec\s*\(', 'Dangerous use of exec()'),
                (r'os\.system\s*\(', 'Potential command injection via os.system()'),
                (r'subprocess\.(call|Popen)\s*\(', 'Potential command injection via subprocess'),
            ]

            for line_num, line in enumerate(lines, 1):
                for pattern, message in dangerous_functions:
                    if re.search(pattern, line):
                        issues.append({
                            'type': 'security',
                            'severity': 'error',
                            'message': message,
                            'file': file_path,
                            'line': line_num,
                            'code_snippet': line.strip(),
                            'plugin': self.metadata.name
                        })

        # Check for dangerous functions (JavaScript)
        elif language == 'javascript':
            dangerous_functions = [
                (r'\beval\s*\(', 'Dangerous use of eval()'),
                (r'innerHTML\s*=', 'Potential XSS via innerHTML'),
                (r'document\.write\s*\(', 'Dangerous use of document.write()'),
            ]

            for line_num, line in enumerate(lines, 1):
                for pattern, message in dangerous_functions:
                    if re.search(pattern, line):
                        issues.append({
                            'type': 'security',
                            'severity': 'error',
                            'message': message,
                            'file': file_path,
                            'line': line_num,
                            'code_snippet': line.strip(),
                            'plugin': self.metadata.name
                        })

        return issues

    def on_issue_found(self, context, issue):
        """
        Hook callback when an issue is found.

        Args:
            context: Plugin context
            issue: Issue details
        """
        # This could log, send notifications, etc.
        print(f"Plugin detected issue: {issue.get('message')}")

    def get_rules(self) -> List[Dict[str, Any]]:
        """Get analysis rules provided by this plugin"""
        return [
            {
                'id': 'PLUGIN_HARDCODED_PASSWORD',
                'name': 'Hardcoded Password',
                'description': 'Detects hardcoded passwords in source code',
                'severity': 'critical',
                'category': 'security'
            },
            {
                'id': 'PLUGIN_DANGEROUS_EVAL',
                'name': 'Dangerous eval() Usage',
                'description': 'Detects use of eval() function',
                'severity': 'error',
                'category': 'security'
            },
            {
                'id': 'PLUGIN_COMMAND_INJECTION',
                'name': 'Command Injection Risk',
                'description': 'Detects potential command injection vulnerabilities',
                'severity': 'error',
                'category': 'security'
            }
        ]


# Plugin entry point
def get_plugin():
    """Return plugin instance"""
    return ExampleSecurityAnalyzer()
