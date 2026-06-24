#!/usr/bin/env python3
"""
Security Audit Script
Performs comprehensive security audit of the application
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import json


class SecurityAuditor:
    """Security audit utility"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.findings = []
        self.stats = {
            'critical': 0,
            'high': 0,
            'medium': 0,
            'low': 0,
            'info': 0
        }

    def run_audit(self) -> Dict:
        """Run complete security audit"""
        print("="*70)
        print("SECURITY AUDIT - AI Code Review Assistant")
        print("="*70)

        self.audit_secrets()
        self.audit_sql_injection()
        self.audit_xss_vulnerabilities()
        self.audit_authentication()
        self.audit_dependencies()
        self.audit_file_permissions()
        self.audit_environment_config()
        self.audit_security_headers()
        self.audit_input_validation()
        self.audit_crypto_usage()

        self.print_report()
        return self.get_summary()

    def audit_secrets(self):
        """Audit for hardcoded secrets"""
        print("\n[1/10] Auditing for hardcoded secrets...")

        secret_patterns = [
            (r'password\s*=\s*["\'](?!.*\$\{)([^"\']{8,})["\']', 'Hardcoded password', 'HIGH'),
            (r'api[_-]?key\s*=\s*["\'](?!.*\$\{)([^"\']{10,})["\']', 'Hardcoded API key', 'HIGH'),
            (r'secret[_-]?key\s*=\s*["\'](?!.*\$\{)([^"\']{10,})["\']', 'Hardcoded secret key', 'HIGH'),
            (r'ghp_[a-zA-Z0-9]{36}', 'GitHub personal access token', 'CRITICAL'),
            (r'sk-[a-zA-Z0-9]{48}', 'OpenAI API key', 'CRITICAL'),
            (r'sk-ant-[a-zA-Z0-9-]{95}', 'Anthropic API key', 'CRITICAL'),
            (r'AWS_SECRET_ACCESS_KEY\s*=\s*["\']([^"\']+)["\']', 'AWS secret key', 'CRITICAL'),
        ]

        for py_file in self.project_root.rglob('*.py'):
            if 'venv' in str(py_file) or '.env' in str(py_file):
                continue

            try:
                content = py_file.read_text()
                for pattern, description, severity in secret_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Skip if it's in a comment or test file
                        if 'test_' in py_file.name or '#' in match.group(0):
                            continue

                        self.add_finding(
                            severity=severity,
                            category='Secrets Management',
                            title=description,
                            description=f'Found in {py_file.relative_to(self.project_root)}',
                            location=str(py_file.relative_to(self.project_root)),
                            line=content[:match.start()].count('\n') + 1
                        )
            except Exception as e:
                print(f"Error reading {py_file}: {e}")

        print(f"  ✓ Scanned {len(list(self.project_root.rglob('*.py')))} Python files")

    def audit_sql_injection(self):
        """Audit for SQL injection vulnerabilities"""
        print("\n[2/10] Auditing for SQL injection vulnerabilities...")

        sql_patterns = [
            (r'execute\(["\'].*%s.*["\'].*%', 'String formatting in SQL', 'HIGH'),
            (r'execute\(["\'].*\+.*["\']', 'String concatenation in SQL', 'HIGH'),
            (r'execute\(f["\'].*\{.*\}.*["\']', 'f-string in SQL', 'HIGH'),
        ]

        for py_file in self.project_root.rglob('*.py'):
            if 'venv' in str(py_file) or 'test_' in py_file.name:
                continue

            try:
                content = py_file.read_text()
                for pattern, description, severity in sql_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        self.add_finding(
                            severity=severity,
                            category='SQL Injection',
                            title=description,
                            description=f'Found in {py_file.relative_to(self.project_root)}',
                            location=str(py_file.relative_to(self.project_root)),
                            line=content[:match.start()].count('\n') + 1
                        )
            except Exception:
                pass

        print("  ✓ SQL injection audit complete")

    def audit_xss_vulnerabilities(self):
        """Audit for XSS vulnerabilities"""
        print("\n[3/10] Auditing for XSS vulnerabilities...")

        # Check HTML templates for unescaped variables
        template_files = list(self.project_root.rglob('*.html'))

        for template in template_files:
            try:
                content = template.read_text()

                # Check for potential XSS in Jinja2 templates
                if '|safe' in content or '|raw' in content:
                    self.add_finding(
                        severity='MEDIUM',
                        category='XSS',
                        title='Potentially unsafe template rendering',
                        description=f'Template uses |safe or |raw filter',
                        location=str(template.relative_to(self.project_root))
                    )
            except Exception:
                pass

        print(f"  ✓ Scanned {len(template_files)} template files")

    def audit_authentication(self):
        """Audit authentication implementation"""
        print("\n[4/10] Auditing authentication...")

        checks = [
            ('src/core/auth_manager.py', 'Authentication manager exists'),
            ('SESSION_TTL', 'Session timeout configured'),
            ('password_hash', 'Password hashing used'),
        ]

        for check_file, description in checks[:1]:
            file_path = self.project_root / check_file
            if not file_path.exists():
                self.add_finding(
                    severity='HIGH',
                    category='Authentication',
                    title='Missing authentication manager',
                    description=description,
                    location=check_file
                )

        print("  ✓ Authentication audit complete")

    def audit_dependencies(self):
        """Audit dependencies for known vulnerabilities"""
        print("\n[5/10] Auditing dependencies...")

        requirements_file = self.project_root / 'requirements.txt'

        if not requirements_file.exists():
            self.add_finding(
                severity='MEDIUM',
                category='Dependencies',
                title='Missing requirements.txt',
                description='Cannot audit dependencies without requirements file',
                location='requirements.txt'
            )
            return

        # Known vulnerable packages (example - would use safety or pip-audit in production)
        try:
            content = requirements_file.read_text()
            lines = content.split('\n')

            # Check for unpinned versions
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    if '==' not in line and '>=' not in line:
                        self.add_finding(
                            severity='LOW',
                            category='Dependencies',
                            title='Unpinned dependency version',
                            description=f'Package {line} has no version constraint',
                            location='requirements.txt'
                        )
        except Exception:
            pass

        print("  ✓ Dependency audit complete")

    def audit_file_permissions(self):
        """Audit file permissions"""
        print("\n[6/10] Auditing file permissions...")

        sensitive_files = [
            '.env',
            'data/database.db',
            'data/repos',
        ]

        for file_path in sensitive_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                # Check if file is world-readable (on Unix systems)
                if hasattr(os, 'stat'):
                    stat = full_path.stat()
                    mode = stat.st_mode
                    # Check for world-readable (o+r)
                    if mode & 0o004:
                        self.add_finding(
                            severity='MEDIUM',
                            category='File Permissions',
                            title='Sensitive file is world-readable',
                            description=f'{file_path} has permissive permissions',
                            location=file_path
                        )

        print("  ✓ File permission audit complete")

    def audit_environment_config(self):
        """Audit environment configuration"""
        print("\n[7/10] Auditing environment configuration...")

        env_example = self.project_root / '.env.example'

        if env_example.exists():
            content = env_example.read_text()

            # Check for default/example secrets
            if 'changeme' in content.lower() or 'example' in content.lower():
                self.add_finding(
                    severity='INFO',
                    category='Configuration',
                    title='Default values in .env.example',
                    description='Ensure production deployments use unique values',
                    location='.env.example'
                )

        # Check if .env is in .gitignore
        gitignore = self.project_root / '.gitignore'
        if gitignore.exists():
            content = gitignore.read_text()
            if '.env' not in content:
                self.add_finding(
                    severity='HIGH',
                    category='Configuration',
                    title='.env file not in .gitignore',
                    description='Risk of committing secrets to version control',
                    location='.gitignore'
                )

        print("  ✓ Environment configuration audit complete")

    def audit_security_headers(self):
        """Audit security headers"""
        print("\n[8/10] Auditing security headers...")

        # Check for security headers middleware
        server_file = self.project_root / 'server.py'

        if server_file.exists():
            content = server_file.read_text()

            required_headers = [
                ('X-Content-Type-Options', 'MEDIUM'),
                ('X-Frame-Options', 'MEDIUM'),
                ('Content-Security-Policy', 'LOW'),
                ('Strict-Transport-Security', 'MEDIUM'),
            ]

            for header, severity in required_headers:
                if header not in content:
                    self.add_finding(
                        severity=severity,
                        category='Security Headers',
                        title=f'Missing {header} header',
                        description='Security header not configured',
                        location='server.py'
                    )

        print("  ✓ Security headers audit complete")

    def audit_input_validation(self):
        """Audit input validation"""
        print("\n[9/10] Auditing input validation...")

        # Check for Pydantic models
        api_files = list((self.project_root / 'src').rglob('*_service.py'))

        uses_pydantic = False
        for api_file in api_files:
            try:
                content = api_file.read_text()
                if 'from pydantic import' in content or 'BaseModel' in content:
                    uses_pydantic = True
                    break
            except Exception:
                pass

        if not uses_pydantic:
            self.add_finding(
                severity='MEDIUM',
                category='Input Validation',
                title='Limited input validation detected',
                description='Consider using Pydantic for input validation',
                location='API endpoints'
            )

        print("  ✓ Input validation audit complete")

    def audit_crypto_usage(self):
        """Audit cryptographic usage"""
        print("\n[10/10] Auditing cryptographic usage...")

        weak_crypto = [
            (r'hashlib\.md5', 'MD5 is cryptographically broken', 'HIGH'),
            (r'hashlib\.sha1', 'SHA1 is deprecated', 'MEDIUM'),
            (r'random\.random', 'random module is not cryptographically secure', 'MEDIUM'),
        ]

        for py_file in self.project_root.rglob('*.py'):
            if 'venv' in str(py_file) or 'test_' in py_file.name:
                continue

            try:
                content = py_file.read_text()
                for pattern, description, severity in weak_crypto:
                    if re.search(pattern, content):
                        self.add_finding(
                            severity=severity,
                            category='Cryptography',
                            title='Weak cryptographic algorithm',
                            description=description,
                            location=str(py_file.relative_to(self.project_root))
                        )
            except Exception:
                pass

        print("  ✓ Cryptography audit complete")

    def add_finding(self, severity: str, category: str, title: str, description: str, location: str, line: int = None):
        """Add security finding"""
        self.findings.append({
            'severity': severity,
            'category': category,
            'title': title,
            'description': description,
            'location': location,
            'line': line
        })
        self.stats[severity.lower()] += 1

    def print_report(self):
        """Print security audit report"""
        print("\n" + "="*70)
        print("SECURITY AUDIT REPORT")
        print("="*70)

        print(f"\nTotal Findings: {len(self.findings)}")
        print(f"  Critical: {self.stats['critical']}")
        print(f"  High:     {self.stats['high']}")
        print(f"  Medium:   {self.stats['medium']}")
        print(f"  Low:      {self.stats['low']}")
        print(f"  Info:     {self.stats['info']}")

        # Group by severity
        for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']:
            severity_findings = [f for f in self.findings if f['severity'] == severity]
            if severity_findings:
                print(f"\n{severity} SEVERITY ({len(severity_findings)}):")
                print("-" * 70)
                for finding in severity_findings:
                    print(f"  [{finding['category']}] {finding['title']}")
                    print(f"  Location: {finding['location']}" + (f":{finding['line']}" if finding['line'] else ""))
                    print(f"  {finding['description']}")
                    print()

        print("="*70)

        # Overall score
        score = 100 - (
            self.stats['critical'] * 20 +
            self.stats['high'] * 10 +
            self.stats['medium'] * 5 +
            self.stats['low'] * 2 +
            self.stats['info'] * 1
        )
        score = max(0, score)

        print(f"\nSecurity Score: {score}/100")

        if score >= 90:
            print("Grade: A (Excellent)")
        elif score >= 80:
            print("Grade: B (Good)")
        elif score >= 70:
            print("Grade: C (Fair)")
        elif score >= 60:
            print("Grade: D (Poor)")
        else:
            print("Grade: F (Failing)")

        print("="*70)

    def get_summary(self) -> Dict:
        """Get audit summary"""
        return {
            'total_findings': len(self.findings),
            'by_severity': self.stats,
            'findings': self.findings
        }

    def save_report(self, filename: str):
        """Save report to JSON file"""
        summary = self.get_summary()
        with open(filename, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"\nReport saved to {filename}")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Security audit utility')
    parser.add_argument('--project-root', default='.', help='Project root directory')
    parser.add_argument('--output', help='Output JSON file')

    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    auditor = SecurityAuditor(project_root)
    summary = auditor.run_audit()

    if args.output:
        auditor.save_report(args.output)

    # Exit with error code if critical or high severity findings
    if summary['by_severity']['critical'] > 0 or summary['by_severity']['high'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
