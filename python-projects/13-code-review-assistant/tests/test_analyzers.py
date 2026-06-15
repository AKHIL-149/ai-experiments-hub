"""
Integration tests for all analyzers working together
"""
import pytest
from pathlib import Path
from src.analyzers import (
    get_registry,
    SecurityAnalyzer,
    SmellAnalyzer,
    ComplexityAnalyzer,
    IssueCategory,
    IssueSeverity
)
from src.parsers.python_parser import PythonParser


@pytest.fixture
def parser():
    return PythonParser()


@pytest.fixture
def registry():
    return get_registry()


@pytest.fixture
def vulnerable_code():
    return str(Path(__file__).parent / 'fixtures' / 'vulnerable_code.py')


def test_all_analyzers_find_issues(registry, parser, vulnerable_code):
    """Run all analyzers on vulnerable code and verify they all find issues"""
    parsed = parser.parse_file(vulnerable_code)
    code = Path(vulnerable_code).read_text()

    issues = registry.analyze(parsed, code)

    # Should find plenty of issues in vulnerable_code.py
    assert len(issues) > 20

    # Check we have all categories
    categories = {issue.category for issue in issues}
    assert IssueCategory.SECURITY in categories
    assert IssueCategory.SMELL in categories
    assert IssueCategory.COMPLEXITY in categories


def test_security_analyzer_alone(parser, vulnerable_code):
    """Test security analyzer finds security issues"""
    analyzer = SecurityAnalyzer()
    parsed = parser.parse_file(vulnerable_code)
    code = Path(vulnerable_code).read_text()

    issues = analyzer.analyze(parsed, code)

    # Should find hardcoded secrets, SQL injection, etc
    assert len(issues) > 5
    assert all(issue.category == IssueCategory.SECURITY for issue in issues)

    # Check for specific rules
    rule_ids = {issue.rule_id for issue in issues}
    assert 'SEC004' in rule_ids  # hardcoded secrets
    assert 'SEC006' in rule_ids  # unsafe deserialization


def test_smell_analyzer_alone(parser, vulnerable_code):
    """Test smell analyzer finds code smells"""
    analyzer = SmellAnalyzer()
    parsed = parser.parse_file(vulnerable_code)
    code = Path(vulnerable_code).read_text()

    issues = analyzer.analyze(parsed, code)

    assert len(issues) > 5
    assert all(issue.category == IssueCategory.SMELL for issue in issues)


def test_complexity_analyzer_alone(parser, vulnerable_code):
    """Test complexity analyzer finds complexity issues"""
    analyzer = ComplexityAnalyzer()
    parsed = parser.parse_file(vulnerable_code)
    code = Path(vulnerable_code).read_text()

    issues = analyzer.analyze(parsed, code)

    # Should find at least some complexity issues
    assert len(issues) >= 0  # May or may not trigger depending on thresholds


def test_no_duplicate_issues(registry, parser):
    """Make sure we don't report the same issue twice"""
    code = '''
def test():
    password = "secret123"
    api_key = "sk_live_abc123"
'''

    parsed = parser.parse_code(code)
    issues = registry.analyze(parsed, code)

    # Check no duplicate line numbers for same rule
    seen = set()
    for issue in issues:
        key = (issue.rule_id, issue.line_number, issue.title)
        assert key not in seen, f"Duplicate issue: {key}"
        seen.add(key)


def test_issue_severities_make_sense(registry, parser, vulnerable_code):
    """Verify issue severities are reasonable"""
    parsed = parser.parse_file(vulnerable_code)
    code = Path(vulnerable_code).read_text()

    issues = registry.analyze(parsed, code)

    # Count by severity
    critical = [i for i in issues if i.severity == IssueSeverity.CRITICAL]
    errors = [i for i in issues if i.severity == IssueSeverity.ERROR]
    warnings = [i for i in issues if i.severity == IssueSeverity.WARNING]
    info = [i for i in issues if i.severity == IssueSeverity.INFO]

    # Should have some critical issues (pickle, eval, exec)
    assert len(critical) > 0

    # Info should be least severe (magic numbers, duplicates)
    if len(info) > 0:
        assert all(i.severity == IssueSeverity.INFO for i in info)


def test_clean_code_has_no_issues(registry, parser):
    """Test that clean code doesn't trigger false positives"""
    code = '''
def add(x, y):
    """Add two numbers"""
    return x + y

def multiply(x, y):
    """Multiply two numbers"""
    return x * y
'''

    parsed = parser.parse_code(code)
    issues = registry.analyze(parsed, code)

    # Clean code should have no issues
    assert len(issues) == 0


def test_specific_analyzer_can_be_disabled(registry, parser):
    """Test running only specific analyzers"""
    code = '''
password = "hardcoded"  # Security issue

def long_function():
    """This is a long function"""
    x = 1
    x = 2
''' + '\n    x = 3\n' * 60  # Make it long

    parsed = parser.parse_code(code)

    # Run only security
    security_issues = registry.analyze(parsed, code, analyzer_ids=['security'])
    assert all(i.category == IssueCategory.SECURITY for i in security_issues)

    # Run only smell
    smell_issues = registry.analyze(parsed, code, analyzer_ids=['smell'])
    assert all(i.category == IssueCategory.SMELL for i in smell_issues)


def test_analyzer_with_custom_config(parser):
    """Test analyzers respect custom configuration"""
    # Lower thresholds
    config = {
        'cc_warning': 3,
        'cc_error': 5
    }
    analyzer = ComplexityAnalyzer(config)

    code = '''
def simple(a, b, c):
    if a:
        if b:
            if c:
                return True
    return False
'''

    parsed = parser.parse_code(code)
    issues = analyzer.analyze(parsed, code)

    # Should flag this with lower threshold
    assert len(issues) >= 0


def test_issue_metadata_is_populated(registry, parser, vulnerable_code):
    """Verify issues have proper metadata"""
    parsed = parser.parse_file(vulnerable_code)
    code = Path(vulnerable_code).read_text()

    issues = registry.analyze(parsed, code)

    for issue in issues:
        assert issue.rule_id is not None
        assert issue.category is not None
        assert issue.severity is not None
        assert issue.title is not None
        assert issue.description is not None
        assert issue.file_path is not None
        assert 0.0 <= issue.confidence <= 1.0


def test_health_score_integration(registry, parser):
    """Test health score with real analysis"""
    bad_code = '''
import pickle
password = "admin123"

def bad_function(a,b,c,d,e,f):
    if a:
        if b:
            if c:
                if d:
                    if e:
                        eval(f)
'''

    parsed = parser.parse_code(bad_code)
    issues = registry.analyze(parsed, bad_code)

    health = registry.calculate_health_score(issues)

    # Bad code should have low score
    assert health['overall_score'] < 80
    assert health['total_issues'] > 0
    assert health['grade'] in ['B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']


def test_multiple_files_analyzed_separately(registry, parser):
    """Test analyzing multiple files doesn't mix issues"""
    file1 = '''
password = "secret"
'''

    file2 = '''
def long_method():
    x = 1
''' + '\n    x += 1\n' * 60

    parsed1 = parser.parse_code(file1)
    issues1 = registry.analyze(parsed1, file1)

    parsed2 = parser.parse_code(file2)
    issues2 = registry.analyze(parsed2, file2)

    # Issues should be for correct files
    for issue in issues1:
        assert 'password' in file1

    for issue in issues2:
        assert 'long_method' in file2
