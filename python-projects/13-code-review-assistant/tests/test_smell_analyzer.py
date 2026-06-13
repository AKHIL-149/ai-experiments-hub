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


# SMELL002: Long parameter list tests

def test_long_parameter_list_detection(smell_analyzer, python_parser):
    """Test detection of functions with too many parameters"""
    code = '''
def function_with_many_params(a, b, c, d, e, f, g):
    """Function with 7 parameters"""
    return a + b + c + d + e + f + g
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell002_issues = [i for i in issues if i.rule_id == 'SMELL002']
    assert len(smell002_issues) > 0
    assert smell002_issues[0].severity == IssueSeverity.WARNING
    assert 'parameter' in smell002_issues[0].title.lower()


def test_short_parameter_list_not_flagged(smell_analyzer, python_parser):
    """Test that functions with few parameters are not flagged"""
    code = '''
def function_with_few_params(a, b, c):
    """Function with 3 parameters"""
    return a + b + c
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell002_issues = [i for i in issues if i.rule_id == 'SMELL002']
    assert len(smell002_issues) == 0


def test_method_self_excluded_from_count(smell_analyzer, python_parser):
    """Test that 'self' parameter is excluded from count"""
    code = '''
class MyClass:
    def method_with_params(self, a, b, c, d, e):
        """Method with 5 params (excluding self)"""
        return a + b + c + d + e
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    # Should not be flagged (5 params excluding self)
    smell002_issues = [i for i in issues if i.rule_id == 'SMELL002']
    assert len(smell002_issues) == 0


def test_classmethod_cls_excluded_from_count(smell_analyzer, python_parser):
    """Test that 'cls' parameter is excluded from count"""
    code = '''
class MyClass:
    @classmethod
    def classmethod_with_params(cls, a, b, c, d, e):
        """Class method with 5 params (excluding cls)"""
        return a + b + c + d + e
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    # Should not be flagged (5 params excluding cls)
    smell002_issues = [i for i in issues if i.rule_id == 'SMELL002']
    assert len(smell002_issues) == 0


def test_varargs_kwargs_counted_as_one(smell_analyzer, python_parser):
    """Test that *args and **kwargs are counted as 1 each"""
    code = '''
def function_with_varargs(a, b, c, d, *args, **kwargs):
    """Function with regular params + *args + **kwargs"""
    return sum([a, b, c, d])
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    # 4 regular + 1 for *args + 1 for **kwargs = 6 total (should be flagged)
    smell002_issues = [i for i in issues if i.rule_id == 'SMELL002']
    assert len(smell002_issues) > 0


def test_long_parameter_list_custom_threshold(smell_analyzer_custom, python_parser):
    """Test custom threshold for parameter count"""
    code = '''
def function_with_four_params(a, b, c, d):
    """Function with 4 parameters"""
    return a + b + c + d
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer_custom.analyze(parsed, code)

    # Custom threshold is 3, so 4 should be flagged
    smell002_issues = [i for i in issues if i.rule_id == 'SMELL002']
    assert len(smell002_issues) > 0


def test_process_order_long_params(smell_analyzer, python_parser, vulnerable_code_path):
    """Test that process_order function is flagged for long parameter list"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    source_code = Path(vulnerable_code_path).read_text()
    issues = smell_analyzer.analyze(parsed, source_code)

    smell002_issues = [i for i in issues if i.rule_id == 'SMELL002']
    assert len(smell002_issues) > 0

    # Check that process_order is detected (has 9 parameters)
    assert any('process_order' in i.title for i in smell002_issues)


def test_long_param_list_metadata(smell_analyzer, python_parser):
    """Test that SMELL002 issues contain parameter count metadata"""
    code = '''
def func(a, b, c, d, e, f, g):
    return a
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell002_issues = [i for i in issues if i.rule_id == 'SMELL002']
    assert len(smell002_issues) > 0

    issue = smell002_issues[0]
    assert 'parameter_count' in issue.metadata
    assert 'threshold' in issue.metadata
    assert issue.metadata['parameter_count'] > issue.metadata['threshold']


# SMELL003: God class tests

def test_god_class_too_many_methods(smell_analyzer, python_parser):
    """Test detection of class with too many methods"""
    code = '''
class GodClass:
    """Class with too many methods"""
    def method1(self): pass
    def method2(self): pass
    def method3(self): pass
    def method4(self): pass
    def method5(self): pass
    def method6(self): pass
    def method7(self): pass
    def method8(self): pass
    def method9(self): pass
    def method10(self): pass
    def method11(self): pass
    def method12(self): pass
    def method13(self): pass
    def method14(self): pass
    def method15(self): pass
    def method16(self): pass
    def method17(self): pass
    def method18(self): pass
    def method19(self): pass
    def method20(self): pass
    def method21(self): pass
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell003_issues = [i for i in issues if i.rule_id == 'SMELL003']
    assert len(smell003_issues) > 0
    assert smell003_issues[0].severity == IssueSeverity.WARNING
    assert 'god class' in smell003_issues[0].title.lower()


def test_god_class_too_many_lines(smell_analyzer, python_parser):
    """Test detection of class with too many lines"""
    code = 'class LargeClass:\n    """Large class"""\n'
    # Add enough methods to exceed 500 lines
    for i in range(100):
        code += f'    def method{i}(self):\n'
        code += f'        x = {i}\n'
        code += f'        y = {i * 2}\n'
        code += f'        z = {i * 3}\n'
        code += f'        return x + y + z\n\n'

    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell003_issues = [i for i in issues if i.rule_id == 'SMELL003']
    assert len(smell003_issues) > 0


def test_small_class_not_flagged(smell_analyzer, python_parser):
    """Test that small classes are not flagged"""
    code = '''
class SmallClass:
    """A small, focused class"""
    def __init__(self):
        self.value = 0

    def get_value(self):
        return self.value

    def set_value(self, value):
        self.value = value
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell003_issues = [i for i in issues if i.rule_id == 'SMELL003']
    assert len(smell003_issues) == 0


def test_application_manager_god_class(smell_analyzer, python_parser, vulnerable_code_path):
    """Test that ApplicationManager class is flagged as god class"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    source_code = Path(vulnerable_code_path).read_text()
    issues = smell_analyzer.analyze(parsed, source_code)

    smell003_issues = [i for i in issues if i.rule_id == 'SMELL003']
    assert len(smell003_issues) > 0

    # Check that ApplicationManager is detected
    assert any('ApplicationManager' in i.title for i in smell003_issues)


def test_god_class_metadata(smell_analyzer, python_parser):
    """Test that SMELL003 issues contain method count and LOC metadata"""
    code = 'class GodClass:\n'
    for i in range(25):
        code += f'    def method{i}(self): pass\n'

    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell003_issues = [i for i in issues if i.rule_id == 'SMELL003']
    assert len(smell003_issues) > 0

    issue = smell003_issues[0]
    assert 'method_count' in issue.metadata
    assert 'lines_of_code' in issue.metadata
    assert 'method_threshold' in issue.metadata
    assert 'loc_threshold' in issue.metadata


def test_god_class_async_methods_counted(smell_analyzer, python_parser):
    """Test that async methods are counted in god class detection"""
    code = 'class AsyncClass:\n'
    for i in range(25):
        code += f'    async def async_method{i}(self): pass\n'

    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell003_issues = [i for i in issues if i.rule_id == 'SMELL003']
    assert len(smell003_issues) > 0


def test_multiple_god_classes(smell_analyzer, python_parser):
    """Test detection of multiple god classes"""
    code = 'class GodClass1:\n'
    for i in range(25):
        code += f'    def method{i}(self): pass\n'
    code += '\nclass GodClass2:\n'
    for i in range(25):
        code += f'    def method{i}(self): pass\n'

    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell003_issues = [i for i in issues if i.rule_id == 'SMELL003']
    assert len(smell003_issues) >= 2


def test_all_smell_rules_in_vulnerable_code(smell_analyzer, python_parser, vulnerable_code_path):
    """Test that all smell rules are detected in vulnerable code"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    source_code = Path(vulnerable_code_path).read_text()
    issues = smell_analyzer.analyze(parsed, source_code)

    # Should find SMELL001 (process_order long method)
    smell001_issues = [i for i in issues if i.rule_id == 'SMELL001']
    assert len(smell001_issues) > 0

    # Should find SMELL002 (process_order long params)
    smell002_issues = [i for i in issues if i.rule_id == 'SMELL002']
    assert len(smell002_issues) > 0

    # Should find SMELL003 (ApplicationManager god class)
    smell003_issues = [i for i in issues if i.rule_id == 'SMELL003']
    assert len(smell003_issues) > 0


# SMELL004: Deep nesting tests

def test_deep_nesting_detection(smell_analyzer, python_parser):
    """Test detection of deeply nested code"""
    code = '''
def deeply_nested():
    """Function with 5 levels of nesting"""
    if True:
        if True:
            if True:
                if True:
                    if True:
                        return "deep"
    return "shallow"
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell004_issues = [i for i in issues if i.rule_id == 'SMELL004']
    assert len(smell004_issues) > 0
    assert smell004_issues[0].severity == IssueSeverity.WARNING
    assert 'nesting' in smell004_issues[0].title.lower()


def test_shallow_nesting_not_flagged(smell_analyzer, python_parser):
    """Test that shallow nesting is not flagged"""
    code = '''
def shallow_function():
    """Function with only 3 levels"""
    if True:
        if True:
            if True:
                return "ok"
    return "done"
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell004_issues = [i for i in issues if i.rule_id == 'SMELL004']
    assert len(smell004_issues) == 0


def test_deep_nesting_with_loops(smell_analyzer, python_parser):
    """Test nesting with for/while loops"""
    code = '''
def nested_loops():
    """Mixed nesting with loops"""
    for i in range(10):
        while i > 0:
            if i % 2 == 0:
                for j in range(5):
                    if j > 2:
                        return i
    return 0
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell004_issues = [i for i in issues if i.rule_id == 'SMELL004']
    assert len(smell004_issues) > 0


def test_complex_validation_deep_nesting(smell_analyzer, python_parser, vulnerable_code_path):
    """Test that complex_validation is flagged for deep nesting"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    source_code = Path(vulnerable_code_path).read_text()
    issues = smell_analyzer.analyze(parsed, source_code)

    smell004_issues = [i for i in issues if i.rule_id == 'SMELL004']
    assert len(smell004_issues) > 0

    # Check that complex_validation is detected
    assert any('complex_validation' in i.title for i in smell004_issues)


def test_deep_nesting_metadata(smell_analyzer, python_parser):
    """Test that SMELL004 issues contain depth metadata"""
    code = '''
def deep():
    if 1:
        if 1:
            if 1:
                if 1:
                    if 1:
                        pass
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell004_issues = [i for i in issues if i.rule_id == 'SMELL004']
    assert len(smell004_issues) > 0

    issue = smell004_issues[0]
    assert 'max_depth' in issue.metadata
    assert 'threshold' in issue.metadata
    assert issue.metadata['max_depth'] > issue.metadata['threshold']


def test_nesting_with_try_except(smell_analyzer, python_parser):
    """Test that try/except counts toward nesting"""
    code = '''
def with_try():
    try:
        if True:
            for i in range(10):
                while i > 0:
                    with open('file') as f:
                        return f.read()
    except:
        pass
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell004_issues = [i for i in issues if i.rule_id == 'SMELL004']
    assert len(smell004_issues) > 0


def test_nesting_custom_threshold(smell_analyzer_custom, python_parser):
    """Test custom nesting depth threshold"""
    # smell_analyzer_custom has max_nesting_depth of 4 (default)
    # This code has exactly 4 levels, so should be flagged
    code = '''
def medium_nesting():
    if 1:
        if 1:
            if 1:
                if 1:
                    if 1:
                        pass
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer_custom.analyze(parsed, code)

    smell004_issues = [i for i in issues if i.rule_id == 'SMELL004']
    # Should be flagged as it exceeds threshold of 4
    assert len(smell004_issues) > 0


# SMELL005: Magic numbers tests

def test_magic_number_detection(smell_analyzer, python_parser):
    """Test detection of magic numbers"""
    code = '''
def calculate():
    """Function with magic numbers"""
    result = value * 3.14
    if result > 100:
        return result * 1.5
    return result
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell005_issues = [i for i in issues if i.rule_id == 'SMELL005']
    assert len(smell005_issues) > 0
    assert smell005_issues[0].severity == IssueSeverity.INFO


def test_common_constants_not_flagged(smell_analyzer, python_parser):
    """Test that 0, 1, -1, 2 are not flagged as magic"""
    code = '''
def with_common_numbers():
    """Using common constants"""
    x = 0
    y = 1
    z = -1
    a = 2
    return x + y + z + a
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell005_issues = [i for i in issues if i.rule_id == 'SMELL005']
    assert len(smell005_issues) == 0


def test_magic_numbers_in_calculations(smell_analyzer, python_parser):
    """Test magic numbers in arithmetic operations"""
    code = '''
def area_circle(radius):
    """Calculate area with magic number"""
    return radius * radius * 3.14159
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell005_issues = [i for i in issues if i.rule_id == 'SMELL005']
    assert len(smell005_issues) > 0
    assert any('3.14159' in str(i.metadata.get('magic_number')) for i in smell005_issues)


def test_calculate_score_magic_numbers(smell_analyzer, python_parser, vulnerable_code_path):
    """Test that calculate_score is flagged for magic numbers"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    source_code = Path(vulnerable_code_path).read_text()
    issues = smell_analyzer.analyze(parsed, source_code)

    smell005_issues = [i for i in issues if i.rule_id == 'SMELL005']
    assert len(smell005_issues) > 0

    # Check for some of the magic numbers in calculate_score
    magic_values = [i.metadata.get('magic_number') for i in smell005_issues]
    # Should find numbers like 1000, 1.5, 500, 1.25, 100, 1.1
    assert any(val in [1000, 500, 100, 1.5, 1.25, 1.1] for val in magic_values)


def test_magic_number_metadata(smell_analyzer, python_parser):
    """Test that SMELL005 issues contain the magic number value"""
    code = '''
def func():
    return x * 42
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell005_issues = [i for i in issues if i.rule_id == 'SMELL005']
    assert len(smell005_issues) > 0

    issue = smell005_issues[0]
    assert 'magic_number' in issue.metadata
    assert issue.metadata['magic_number'] == 42


def test_magic_numbers_multiple_occurrences(smell_analyzer, python_parser):
    """Test detection of multiple different magic numbers"""
    code = '''
def pricing():
    base = 99.99
    tax = base * 0.08
    shipping = 15.50
    return base + tax + shipping
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell005_issues = [i for i in issues if i.rule_id == 'SMELL005']
    # Should detect 99.99, 0.08, 15.50
    assert len(smell005_issues) >= 3


def test_magic_numbers_in_return(smell_analyzer, python_parser):
    """Test magic numbers in return statements"""
    code = '''
def get_timeout():
    return 30
'''
    parsed = python_parser.parse_code(code)
    issues = smell_analyzer.analyze(parsed, code)

    smell005_issues = [i for i in issues if i.rule_id == 'SMELL005']
    assert len(smell005_issues) > 0
    assert smell005_issues[0].metadata['magic_number'] == 30
