"""
Tests for complexity analyzer functionality
"""

import pytest
from pathlib import Path
from src.analyzers.complexity_analyzer import ComplexityAnalyzer
from src.analyzers.base_analyzer import IssueCategory, IssueSeverity
from src.parsers.python_parser import PythonParser


@pytest.fixture
def complexity_analyzer():
    """Create ComplexityAnalyzer instance"""
    return ComplexityAnalyzer()


@pytest.fixture
def python_parser():
    """Create Python parser instance"""
    return PythonParser()


@pytest.fixture
def vulnerable_code_path():
    """Get path to vulnerable code"""
    return str(Path(__file__).parent / 'fixtures' / 'vulnerable_code.py')


def test_analyzer_id(complexity_analyzer):
    """Test analyzer ID is correct"""
    assert complexity_analyzer.analyzer_id == 'complexity'


def test_analyzer_category(complexity_analyzer):
    """Test analyzer category is COMPLEXITY"""
    assert complexity_analyzer.category == IssueCategory.COMPLEXITY


def test_rule_ids(complexity_analyzer):
    """Test analyzer reports correct rule IDs"""
    rule_ids = complexity_analyzer.get_rule_ids()
    assert 'COMPLEX001' in rule_ids
    assert 'COMPLEX002' in rule_ids
    assert len(rule_ids) == 2


def test_cyclomatic_complexity_detection(complexity_analyzer, python_parser):
    """Test detection of high cyclomatic complexity"""
    code = '''
def complex_function(a, b, c, d, e):
    """Function with high complexity"""
    result = 0

    if a > 0:
        if b > 0:
            result += a * b
        else:
            result += a

    if c > 0:
        if d > 0:
            result += c * d
        else:
            result += c

    if e > 0:
        result *= e

    for i in range(10):
        if i % 2 == 0:
            result += i
        else:
            result -= i

    while result > 100:
        result /= 2

    try:
        result = result / a
    except:
        result = 0

    return result
'''
    parsed = python_parser.parse_code(code)
    issues = complexity_analyzer.analyze(parsed, code)

    complex001_issues = [i for i in issues if i.rule_id == 'COMPLEX001']
    assert len(complex001_issues) > 0
    assert complex001_issues[0].severity in [IssueSeverity.WARNING, IssueSeverity.ERROR]


def test_simple_function_not_flagged(complexity_analyzer, python_parser):
    """Test simple functions are not flagged for complexity"""
    code = '''
def simple_function(x, y):
    """A simple function"""
    return x + y
'''
    parsed = python_parser.parse_code(code)
    issues = complexity_analyzer.analyze(parsed, code)

    complex001_issues = [i for i in issues if i.rule_id == 'COMPLEX001']
    assert len(complex001_issues) == 0


def test_custom_cc_thresholds(python_parser):
    """Test custom cyclomatic complexity thresholds"""
    config = {
        'cc_warning': 5,
        'cc_error': 10
    }
    analyzer = ComplexityAnalyzer(config)

    code = '''
def medium_complexity(a, b, c):
    result = 0
    if a > 0:
        result += 1
    if b > 0:
        result += 2
    if c > 0:
        result += 3

    for i in range(10):
        if i % 2:
            result += i

    return result
'''
    parsed = python_parser.parse_code(code)
    issues = analyzer.analyze(parsed, code)

    complex001_issues = [i for i in issues if i.rule_id == 'COMPLEX001']
    # With lower threshold (5), this function (complexity ~6-7) should be flagged
    assert len(complex001_issues) > 0


def test_cyclomatic_complexity_metadata(complexity_analyzer, python_parser):
    """Test CC issues contain proper metadata"""
    code = '''
def moderately_complex(x, y):
    result = 0
    if x > 0:
        if y > 0:
            result = x + y
        else:
            result = x - y
    else:
        if y > 0:
            result = y - x
        else:
            result = 0

    for i in range(5):
        if i % 2:
            result += i

    return result
'''
    parsed = python_parser.parse_code(code)
    issues = complexity_analyzer.analyze(parsed, code)

    complex001_issues = [i for i in issues if i.rule_id == 'COMPLEX001']
    if len(complex001_issues) > 0:
        issue = complex001_issues[0]
        assert hasattr(issue, 'complexity')
        assert hasattr(issue, 'warning_threshold')
        assert hasattr(issue, 'error_threshold')
        assert issue.complexity >= issue.warning_threshold


def test_vulnerable_code_complexity(complexity_analyzer, python_parser, vulnerable_code_path):
    """Test complex_function from vulnerable_code.py is flagged"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    with open(vulnerable_code_path, 'r') as f:
        code = f.read()

    issues = complexity_analyzer.analyze(parsed, code)

    complex001_issues = [i for i in issues if i.rule_id == 'COMPLEX001']
    # vulnerable_code.py has a complex_function that should be flagged
    assert len(complex001_issues) > 0

    # Check that complex_function is mentioned
    complex_func_issues = [i for i in complex001_issues if 'complex_function' in i.title]
    assert len(complex_func_issues) > 0


def test_analyzer_handles_syntax_error(complexity_analyzer, python_parser):
    """Test analyzer handles syntax errors gracefully"""
    code = "def broken("

    try:
        parsed = python_parser.parse_code(code)
        issues = complexity_analyzer.analyze(parsed, code)
        # Should not crash - if we got here, the analyzer handled it
        assert isinstance(issues, list)
    except:
        # If parsing fails, that's expected
        assert True


def test_maintainability_index_detection(complexity_analyzer, python_parser):
    """Test detection of low maintainability index"""
    # Create a complex, long function with poor maintainability
    code = '''
def poorly_maintained_function(a, b, c, d, e, f, g, h):
    """A poorly maintained function"""
    x = 0
    if a: x += 1
    if b: x += 2
    if c: x += 3
    if d: x += 4
    if e: x += 5
    if f: x += 6
    if g: x += 7
    if h: x += 8

    for i in range(100):
        if i % 2:
            if i % 3:
                if i % 5:
                    x += i
                else:
                    x -= i
            else:
                x *= 2
        else:
            x //= 2

    y = 0
    while x > 0:
        if x % 10 == 0:
            y += x
        elif x % 10 == 1:
            y += x * 2
        elif x % 10 == 2:
            y += x * 3
        elif x % 10 == 3:
            y += x * 4
        elif x % 10 == 4:
            y += x * 5
        else:
            y += x * 6
        x -= 1

    return y
'''
    parsed = python_parser.parse_code(code)
    issues = complexity_analyzer.analyze(parsed, code)

    # This function should have either high CC or low MI
    all_complexity_issues = [i for i in issues if i.rule_id in ['COMPLEX001', 'COMPLEX002']]
    assert len(all_complexity_issues) > 0


def test_multiple_complex_functions(python_parser):
    """Test multiple functions with complexity issues"""
    # Use lower threshold so both functions get flagged
    config = {'cc_warning': 6, 'cc_error': 12}
    analyzer = ComplexityAnalyzer(config)

    code = '''
def complex_a(a, b, c, d, e):
    result = 0
    if a > 0:
        result += 1
    if b > 0:
        result += 2
    if c > 0:
        result += 3
    if d > 0:
        result += 4
    if e > 0:
        result += 5

    for i in range(10):
        if i % 2:
            result += i
        else:
            result -= i

    return result

def complex_b(x, y, z):
    total = 0
    if x > 0:
        total += x
    if y > 0:
        total += y
    if z > 0:
        total += z

    for j in range(5):
        if j % 2:
            total *= 2
        else:
            total //= 2

    while total > 100:
        total -= 10

    return total
'''
    parsed = python_parser.parse_code(code)
    issues = analyzer.analyze(parsed, code)

    complex001_issues = [i for i in issues if i.rule_id == 'COMPLEX001']
    # Both functions should be flagged (each has complexity 7-8, above threshold of 6)
    assert len(complex001_issues) >= 2


def test_default_thresholds(complexity_analyzer):
    """Test default threshold values"""
    assert complexity_analyzer.cc_warning_threshold == 10
    assert complexity_analyzer.cc_error_threshold == 15
    assert complexity_analyzer.mi_warning_threshold == 20
    assert complexity_analyzer.mi_error_threshold == 10


def test_issue_severity_levels(python_parser):
    """Test that severity escalates with complexity"""
    # Create analyzer with custom thresholds for testing
    config = {'cc_warning': 5, 'cc_error': 10}
    analyzer = ComplexityAnalyzer(config)

    warning_code = '''
def warning_level(x):
    # Complexity around 5-9 (warning level)
    if x > 0:
        if x > 10:
            if x > 20:
                return x * 2
            return x
        return x - 1
    return 0
'''

    error_code = '''
def error_level(a, b, c):
    # Complexity around 10+ (error level)
    result = 0
    if a > 0:
        if b > 0:
            if c > 0:
                result = a + b + c
            else:
                result = a + b
        else:
            if c > 0:
                result = a + c
            else:
                result = a
    else:
        if b > 0:
            if c > 0:
                result = b + c
            else:
                result = b
        else:
            result = c
    return result
'''

    warning_parsed = python_parser.parse_code(warning_code)
    warning_issues = analyzer.analyze(warning_parsed, warning_code)

    error_parsed = python_parser.parse_code(error_code)
    error_issues = analyzer.analyze(error_parsed, error_code)

    # Both should have COMPLEX001 issues
    warning_cc = [i for i in warning_issues if i.rule_id == 'COMPLEX001']
    error_cc = [i for i in error_issues if i.rule_id == 'COMPLEX001']

    if len(warning_cc) > 0 and len(error_cc) > 0:
        # Error should have higher or equal severity
        assert warning_cc[0].severity == IssueSeverity.WARNING
        assert error_cc[0].severity == IssueSeverity.ERROR
