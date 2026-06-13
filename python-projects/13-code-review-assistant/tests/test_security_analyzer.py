"""
Tests for SecurityAnalyzer functionality
"""

import pytest
from pathlib import Path
from src.analyzers.security_analyzer import SecurityAnalyzer
from src.parsers.python_parser import PythonParser
from src.analyzers.base_analyzer import IssueSeverity


@pytest.fixture
def security_analyzer():
    """Create SecurityAnalyzer instance"""
    return SecurityAnalyzer()


@pytest.fixture
def python_parser():
    """Create Python parser instance"""
    return PythonParser()


@pytest.fixture
def vulnerable_code_path():
    """Get path to vulnerable code"""
    return str(Path(__file__).parent / 'fixtures' / 'vulnerable_code.py')


def test_analyzer_id(security_analyzer):
    """Test analyzer ID is correct"""
    assert security_analyzer.analyzer_id == 'security'


def test_analyzer_category(security_analyzer):
    """Test analyzer category is security"""
    from src.analyzers.base_analyzer import IssueCategory
    assert security_analyzer.category == IssueCategory.SECURITY


def test_rule_ids(security_analyzer):
    """Test analyzer returns correct rule IDs"""
    rule_ids = security_analyzer.get_rule_ids()
    assert 'SEC002' in rule_ids  # Command injection
    assert 'SEC003' in rule_ids  # Subprocess shell=True
    assert 'SEC004' in rule_ids  # Hardcoded secrets
    assert 'SEC005' in rule_ids  # Path traversal
    assert 'SEC006' in rule_ids  # Unsafe deserialization
    assert 'SEC007' in rule_ids  # Weak crypto


def test_command_injection_os_system(security_analyzer, python_parser):
    """Test detection of os.system() with string concatenation"""
    code = """
import os
def run_cmd(user_input):
    os.system("ls " + user_input)
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec002_issues = [i for i in issues if i.rule_id == 'SEC002']
    assert len(sec002_issues) > 0
    assert sec002_issues[0].severity == IssueSeverity.CRITICAL
    assert 'command injection' in sec002_issues[0].title.lower()


def test_command_injection_os_system_fstring(security_analyzer, python_parser):
    """Test detection of os.system() with f-string"""
    code = """
import os
def run_cmd(cmd):
    os.system(f"echo {cmd}")
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec002_issues = [i for i in issues if i.rule_id == 'SEC002']
    assert len(sec002_issues) > 0
    assert sec002_issues[0].severity == IssueSeverity.CRITICAL


def test_subprocess_shell_true(security_analyzer, python_parser):
    """Test detection of subprocess with shell=True"""
    code = """
import subprocess
def execute(cmd):
    subprocess.call(cmd, shell=True)
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec003_issues = [i for i in issues if i.rule_id == 'SEC003']
    assert len(sec003_issues) > 0
    assert sec003_issues[0].severity == IssueSeverity.ERROR
    assert 'shell=True' in sec003_issues[0].title


def test_subprocess_safe_usage(security_analyzer, python_parser):
    """Test subprocess without shell=True is not flagged"""
    code = """
import subprocess
def execute():
    subprocess.run(["ls", "-l"])
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec003_issues = [i for i in issues if i.rule_id == 'SEC003']
    assert len(sec003_issues) == 0


def test_hardcoded_api_key_stripe(security_analyzer, python_parser):
    """Test detection of Stripe API key"""
    # Build test string to avoid GitHub push protection
    stripe_prefix = "sk_" + "live_"
    test_key = stripe_prefix + "1234567890abcdefghijklmnopqrstuvwxyz"
    code = f"""
API_KEY = "{test_key}"
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)

    sec004_issues = [i for i in issues if i.rule_id == 'SEC004']
    assert len(sec004_issues) > 0
    assert sec004_issues[0].severity == IssueSeverity.CRITICAL
    assert 'Stripe' in sec004_issues[0].title or 'secret' in sec004_issues[0].title.lower()


def test_hardcoded_github_token(security_analyzer, python_parser):
    """Test detection of GitHub token"""
    # Build test string to avoid GitHub push protection
    github_prefix = "gh" + "p_"
    test_token = github_prefix + "1234567890abcdefghijklmnopqrstuvwxyz1234567890"
    code = f"""
TOKEN = "{test_token}"
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)

    sec004_issues = [i for i in issues if i.rule_id == 'SEC004']
    assert len(sec004_issues) > 0
    assert 'GitHub' in sec004_issues[0].title or 'secret' in sec004_issues[0].title.lower()


def test_hardcoded_password_variable(security_analyzer, python_parser):
    """Test detection of hardcoded password by variable name"""
    code = """
password = "secret123"
api_key = "myapikey"
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec004_issues = [i for i in issues if i.rule_id == 'SEC004']
    assert len(sec004_issues) >= 2  # password and api_key


def test_hardcoded_secret_ignores_test_values(security_analyzer, python_parser):
    """Test that test/placeholder values are ignored"""
    code = """
password = "test"
api_key = "changeme"
secret = "YOUR_API_KEY_HERE"
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec004_issues = [i for i in issues if i.rule_id == 'SEC004']
    assert len(sec004_issues) == 0


def test_path_traversal_open_concatenation(security_analyzer, python_parser):
    """Test detection of path traversal in open() with concatenation"""
    code = """
def read_file(filename):
    with open("/data/" + filename, 'r') as f:
        return f.read()
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec005_issues = [i for i in issues if i.rule_id == 'SEC005']
    assert len(sec005_issues) > 0
    assert sec005_issues[0].severity == IssueSeverity.ERROR
    assert 'path traversal' in sec005_issues[0].title.lower()


def test_path_traversal_open_fstring(security_analyzer, python_parser):
    """Test detection of path traversal in open() with f-string"""
    code = """
def read_file(name):
    path = f"/data/{name}"
    return open(path).read()
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec005_issues = [i for i in issues if i.rule_id == 'SEC005']
    assert len(sec005_issues) > 0


def test_path_traversal_os_path_join(security_analyzer, python_parser):
    """Test detection of os.path.join with variables"""
    code = """
import os
def get_file(user_input):
    path = os.path.join('/data', user_input)
    return open(path).read()
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec005_issues = [i for i in issues if i.rule_id == 'SEC005']
    assert len(sec005_issues) >= 1  # os.path.join and/or open()


def test_unsafe_pickle_loads(security_analyzer, python_parser):
    """Test detection of pickle.loads()"""
    code = """
import pickle
def load_data(data):
    return pickle.loads(data)
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec006_issues = [i for i in issues if i.rule_id == 'SEC006']
    assert len(sec006_issues) > 0
    assert sec006_issues[0].severity == IssueSeverity.CRITICAL
    assert 'pickle' in sec006_issues[0].title.lower()


def test_unsafe_eval(security_analyzer, python_parser):
    """Test detection of eval()"""
    code = """
def calculate(expr):
    return eval(expr)
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec006_issues = [i for i in issues if i.rule_id == 'SEC006']
    assert len(sec006_issues) > 0
    assert any('eval' in i.title.lower() for i in sec006_issues)


def test_unsafe_exec(security_analyzer, python_parser):
    """Test detection of exec()"""
    code = """
def run_code(code):
    exec(code)
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec006_issues = [i for i in issues if i.rule_id == 'SEC006']
    assert len(sec006_issues) > 0
    assert any('exec' in i.title.lower() for i in sec006_issues)


def test_weak_crypto_md5(security_analyzer, python_parser):
    """Test detection of MD5 usage"""
    code = """
import hashlib
def hash_data(data):
    return hashlib.md5(data.encode()).hexdigest()
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec007_issues = [i for i in issues if i.rule_id == 'SEC007']
    assert len(sec007_issues) > 0
    assert sec007_issues[0].severity == IssueSeverity.WARNING
    assert 'MD5' in sec007_issues[0].title


def test_weak_crypto_sha1(security_analyzer, python_parser):
    """Test detection of SHA1 usage"""
    code = """
import hashlib
def hash_data(data):
    return hashlib.sha1(data.encode()).hexdigest()
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec007_issues = [i for i in issues if i.rule_id == 'SEC007']
    assert len(sec007_issues) > 0
    assert 'SHA1' in sec007_issues[0].title


def test_strong_crypto_not_flagged(security_analyzer, python_parser):
    """Test that SHA256 is not flagged"""
    code = """
import hashlib
def hash_data(data):
    return hashlib.sha256(data.encode()).hexdigest()
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    sec007_issues = [i for i in issues if i.rule_id == 'SEC007']
    assert len(sec007_issues) == 0


def test_analyze_vulnerable_code_file(security_analyzer, python_parser, vulnerable_code_path):
    """Test analyzing the full vulnerable code file"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    source_code = Path(vulnerable_code_path).read_text()
    issues = security_analyzer.analyze(parsed, source_code)
    
    # Should find multiple issues
    assert len(issues) > 0
    
    # Check for each rule type
    rule_ids = {issue.rule_id for issue in issues}
    assert 'SEC002' in rule_ids or 'SEC003' in rule_ids  # Command injection
    assert 'SEC004' in rule_ids  # Hardcoded secrets
    assert 'SEC005' in rule_ids  # Path traversal
    assert 'SEC006' in rule_ids  # Unsafe deserialization
    assert 'SEC007' in rule_ids  # Weak crypto


def test_issue_contains_code_snippet(security_analyzer, python_parser):
    """Test that issues include code snippets"""
    code = """
import os
def bad_func(user_input):
    os.system("ls " + user_input)
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    assert len(issues) > 0
    assert issues[0].code_snippet is not None
    assert 'os.system' in issues[0].code_snippet


def test_issue_contains_suggestion(security_analyzer, python_parser):
    """Test that issues include fix suggestions"""
    code = """
import subprocess
subprocess.call("ls", shell=True)
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    assert len(issues) > 0
    assert issues[0].suggestion is not None
    assert len(issues[0].suggestion) > 0


def test_issue_has_confidence_score(security_analyzer, python_parser):
    """Test that issues have confidence scores"""
    code = """
password = "hardcoded123"
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    assert len(issues) > 0
    assert 0.0 <= issues[0].confidence <= 1.0


def test_analyzer_handles_syntax_error(security_analyzer):
    """Test analyzer handles syntax errors gracefully"""
    from src.parsers.models import ParsedModule
    
    invalid_code = "def broken("
    parsed = ParsedModule(
        file_path='<test>',
        language='python',
        imports=[],
        functions=[],
        classes=[],
        global_variables=[]
    )
    
    issues = security_analyzer.analyze(parsed, invalid_code)
    # Should return empty list, not crash
    assert isinstance(issues, list)


def test_multiple_issues_same_line(security_analyzer, python_parser):
    """Test that multiple issues on same construct are handled"""
    code = """
import os
user_input = input()
os.system("rm -rf " + user_input)  # Multiple concerns
"""
    parsed = python_parser.parse_code(code)
    issues = security_analyzer.analyze(parsed, code)
    
    # Should detect command injection
    assert len(issues) > 0
    assert any(i.rule_id == 'SEC002' for i in issues)
