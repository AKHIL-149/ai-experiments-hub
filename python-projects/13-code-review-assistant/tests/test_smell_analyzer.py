"""
Tests for SmellAnalyzer functionality
"""

import pytest
from pathlib import Path
from src.analyzers.smell_analyzer import SmellAnalyzer
from src.parsers.python_parser import PythonParser
from src.analyzers.base_analyzer import IssueSeverity


@pytest.fixture
def smell_analyzer():
    """Create SmellAnalyzer instance with default config"""
    return SmellAnalyzer()


@pytest.fixture
def smell_analyzer_custom():
    """Create SmellAnalyzer with custom thresholds"""
    return SmellAnalyzer(config={
        'max_method_lines': 30,
        'max_parameters': 3
    })


@pytest.fixture
def python_parser():
    """Create Python parser instance"""
    return PythonParser()


@pytest.fixture
def vulnerable_code_path():
    """Get path to vulnerable code"""
    return str(Path(__file__).parent / 'fixtures' / 'vulnerable_code.py')


def test_analyzer_id(smell_analyzer):
    """Test analyzer ID is correct"""
    assert smell_analyzer.analyzer_id == 'smell'


def test_analyzer_category(smell_analyzer):
    """Test analyzer category is smell"""
    from src.analyzers.base_analyzer import IssueCategory
    assert smell_analyzer.category == IssueCategory.SMELL


def test_rule_ids(smell_analyzer):
    """Test analyzer returns correct rule IDs"""
    rule_ids = smell_analyzer.get_rule_ids()
    assert 'SMELL001' in rule_ids  # Long methods


def test_long_method_detection(smell_analyzer, python_parser):
    """Test detection of long methods"""
    # Create a function with more than 50 lines
    code = '''
def long_function():
    """A very long function"""
    x = 1
    y = 2
    z = 3
    a = 4
    b = 5
    c = 6
    d = 7
    e = 8
    f = 9
    g = 10
    h = 11
    i = 12
    j = 13
    k = 14
    l = 15
    m = 16
    n = 17
    o = 18
    p = 19
    q = 20
    r = 21
    s = 22
    t = 23
    u = 24
    v = 25
    w = 26
    xx = 27
    yy = 28
    zz = 29
    aa = 30
    bb = 31
    cc = 32
    dd = 33
    ee = 34
    ff = 35
    gg = 36
    hh = 37
    ii = 38
    jj = 39
    kk = 40
    ll = 41
    mm = 42
    nn = 43
    oo = 44
    pp = 45
    qq = 46
    rr = 47
    ss = 48
    tt = 49
    uu = 50
    vv = 51
    return vv
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)
    
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) > 0
    assert smell001_issues[0].severity == IssueSeverity.WARNING
    assert 'long_function' in smell001_issues[0].title.lower()


def test_short_method_not_flagged(smell_analyzer, python_parser):
    """Test that short methods are not flagged"""
    code = '''
def short_function():
    """A short function"""
    x = 1
    y = 2
    return x + y
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)
    
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) == 0


def test_long_method_with_comments_and_blanks(smell_analyzer, python_parser):
    """Test that comments and blank lines are excluded from count"""
    code = '''
def function_with_comments():
    """Docstring should be excluded"""
    # This is a comment
    x = 1
    
    # Another comment
    y = 2
    
    # More comments
    z = 3
    
    return x + y + z
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)
    
    # Should not be flagged as long (only 3 real lines of code)
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) == 0


def test_method_vs_function_detection(smell_analyzer, python_parser):
    """Test that methods are identified correctly"""
    code = '''
class MyClass:
    def long_method(self):
        """A long method"""
''' + '\n'.join([f'        x{i} = {i}' for i in range(55)]) + '''
        return x0

def long_function():
    """A long function"""
''' + '\n'.join([f'    x{i} = {i}' for i in range(55)]) + '''
    return x0
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)
    
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) >= 2
    
    # Check that we identified one as method and one as function
    titles = [i.title for i in smell001_issues]
    assert any('method' in t.lower() for t in titles)
    assert any('function' in t.lower() for t in titles)


def test_custom_threshold(smell_analyzer_custom, python_parser):
    """Test custom threshold configuration"""
    # Create function with 35 lines (over custom threshold of 30)
    code = 'def medium_function():\n    """Doc"""\n'
    code += '\n'.join([f'    x{i} = {i}' for i in range(35)])
    code += '\n    return x0'
    
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer_custom.analyze(parsed, code)
    
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) > 0


def test_async_function_detection(smell_analyzer, python_parser):
    """Test that async functions are also checked"""
    code = 'async def long_async():\n    """Async function"""\n'
    code += '\n'.join([f'    x{i} = {i}' for i in range(55)])
    code += '\n    return x0'
    
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)
    
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) > 0


def test_multiline_docstring_excluded(smell_analyzer, python_parser):
    """Test that multiline docstrings are excluded from count"""
    code = '''
def function_with_docstring():
    """
    This is a long docstring
    that spans multiple lines
    and should not be counted
    as lines of code.
    
    It has many lines but
    they are all documentation.
    """
    x = 1
    y = 2
    z = 3
    return x + y + z
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)
    
    # Should not be flagged (only 4 real lines of code)
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) == 0


def test_issue_contains_metadata(smell_analyzer, python_parser):
    """Test that issues include useful metadata"""
    code = 'def long_func():\n    """Doc"""\n'
    code += '\n'.join([f'    x{i} = {i}' for i in range(55)])
    code += '\n    return x0'
    
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)
    
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) > 0
    
    issue = smell001_issues[0]
    assert 'lines_of_code' in issue.metadata
    assert 'threshold' in issue.metadata
    assert issue.metadata['lines_of_code'] > issue.metadata['threshold']


def test_issue_contains_suggestion(smell_analyzer, python_parser):
    """Test that issues include fix suggestions"""
    code = 'def long_func():\n    """Doc"""\n'
    code += '\n'.join([f'    x{i} = {i}' for i in range(55)])
    code += '\n    return x0'
    
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)
    
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) > 0
    assert smell001_issues[0].suggestion is not None
    assert 'extract' in smell001_issues[0].suggestion.lower()


def test_analyze_vulnerable_code_file(smell_analyzer, python_parser, vulnerable_code_path):
    """Test analyzing the vulnerable code fixture"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    source_code = Path(vulnerable_code_path).read_text()
    issues = smell_analyzer.analyze(parsed, source_code)
    
    # Should find the process_order function (>50 lines)
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) > 0
    
    # Check that process_order is detected
    assert any('process_order' in i.title for i in smell001_issues)


def test_analyzer_handles_syntax_error(smell_analyzer):
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
    
    issues = smell_analyzer.analyze(parsed, invalid_code)
    # Should return empty list, not crash
    assert isinstance(issues, list)


def test_multiple_long_functions(smell_analyzer, python_parser):
    """Test detection of multiple long functions"""
    code = 'def func1():\n    """Doc1"""\n'
    code += '\n'.join([f'    x{i} = {i}' for i in range(55)])
    code += '\n    return x0\n\n'
    code += 'def func2():\n    """Doc2"""\n'
    code += '\n'.join([f'    y{i} = {i}' for i in range(55)])
    code += '\n    return y0'
    
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)
    
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) >= 2


def test_default_thresholds(smell_analyzer):
    """Test that default thresholds are set correctly"""
    assert smell_analyzer.max_method_lines == 50
    assert smell_analyzer.max_parameters == 5
    assert smell_analyzer.max_nesting_depth == 4
    assert smell_analyzer.max_class_methods == 20
