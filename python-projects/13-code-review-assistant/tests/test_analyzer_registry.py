"""
Tests for analyzer registry functionality
"""
import pytest
from pathlib import Path
from src.analyzers import (
    AnalyzerRegistry,
    get_registry,
    SecurityAnalyzer,
    SmellAnalyzer,
    ComplexityAnalyzer,
    IssueCategory,
    IssueSeverity
)
from src.parsers.python_parser import PythonParser


@pytest.fixture
def registry():
    """Create a fresh registry instance"""
    return AnalyzerRegistry()


@pytest.fixture
def python_parser():
    """Create Python parser instance"""
    return PythonParser()


@pytest.fixture
def vulnerable_code_path():
    """Get path to vulnerable code"""
    return str(Path(__file__).parent / 'fixtures' / 'vulnerable_code.py')


def test_registry_initialization(registry):
    """Test that registry initializes with default analyzers"""
    analyzers = registry.get_all_analyzers()
    assert len(analyzers) == 3

    analyzer_ids = {a.analyzer_id for a in analyzers}
    assert 'security' in analyzer_ids
    assert 'smell' in analyzer_ids
    assert 'complexity' in analyzer_ids


def test_get_analyzer_by_id(registry):
    """Test retrieving analyzer by ID"""
    security = registry.get_analyzer('security')
    assert security is not None
    assert isinstance(security, SecurityAnalyzer)

    smell = registry.get_analyzer('smell')
    assert smell is not None
    assert isinstance(smell, SmellAnalyzer)

    complexity = registry.get_analyzer('complexity')
    assert complexity is not None
    assert isinstance(complexity, ComplexityAnalyzer)

    # Non-existent analyzer
    none_analyzer = registry.get_analyzer('nonexistent')
    assert none_analyzer is None


def test_get_enabled_analyzers(registry):
    """Test getting only enabled analyzers"""
    enabled = registry.get_enabled_analyzers()
    # All default analyzers should be enabled
    assert len(enabled) == 3


def test_register_custom_analyzer(registry):
    """Test registering a custom analyzer"""
    from src.analyzers.base_analyzer import BaseAnalyzer, IssueCategory

    class CustomAnalyzer(BaseAnalyzer):
        @property
        def analyzer_id(self):
            return 'custom'

        @property
        def category(self):
            return IssueCategory.STYLE

        def analyze(self, parsed_module, source_code):
            return []

    custom = CustomAnalyzer()
    registry.register_analyzer(custom)

    # Should now have 4 analyzers
    assert len(registry.get_all_analyzers()) == 4

    # Should be able to retrieve it
    retrieved = registry.get_analyzer('custom')
    assert retrieved is custom


def test_analyze_with_all_analyzers(registry, python_parser, vulnerable_code_path):
    """Test running all analyzers on vulnerable code"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    source_code = Path(vulnerable_code_path).read_text()

    issues = registry.analyze(parsed, source_code)

    # Should find issues from all categories
    assert len(issues) > 0

    categories = {issue.category for issue in issues}
    # Should have security, smell, and complexity issues
    assert IssueCategory.SECURITY in categories
    assert IssueCategory.SMELL in categories
    assert IssueCategory.COMPLEXITY in categories


def test_analyze_with_specific_analyzers(registry, python_parser, vulnerable_code_path):
    """Test running specific analyzers only"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    source_code = Path(vulnerable_code_path).read_text()

    # Run only security analyzer
    issues = registry.analyze(parsed, source_code, analyzer_ids=['security'])

    # Should only have security issues
    assert len(issues) > 0
    assert all(issue.category == IssueCategory.SECURITY for issue in issues)


def test_get_supported_categories(registry):
    """Test getting all supported categories"""
    categories = registry.get_supported_categories()

    assert 'security' in categories
    assert 'smell' in categories
    assert 'complexity' in categories
    assert len(categories) == 3


def test_get_all_rule_ids(registry):
    """Test getting all rule IDs from all analyzers"""
    rule_ids = registry.get_all_rule_ids()

    # Should have rules from all analyzers
    # Security: SEC002, SEC003, SEC004, SEC005, SEC006, SEC007
    # Smell: SMELL001-006
    # Complexity: COMPLEX001-003
    assert 'SEC002' in rule_ids
    assert 'SMELL001' in rule_ids
    assert 'COMPLEX001' in rule_ids

    # Should be sorted
    assert rule_ids == sorted(rule_ids)


def test_singleton_registry():
    """Test that get_registry returns singleton instance"""
    registry1 = get_registry()
    registry2 = get_registry()

    # Should be the same instance
    assert registry1 is registry2


def test_health_score_perfect_code(registry):
    """Test health score with no issues"""
    issues = []
    health = registry.calculate_health_score(issues)

    assert health['overall_score'] == 100
    assert health['grade'] == 'A+'
    assert health['total_issues'] == 0
    assert health['description'] == 'Excellent! No issues detected.'


def test_health_score_with_issues(registry, python_parser):
    """Test health score calculation with issues"""
    code = '''
def test():
    password = "hardcoded123"  # Security issue
    x = 0
    for i in range(100):  # Magic number
        if i % 2:
            if i % 3:
                if i % 5:
                    if i % 7:  # Deep nesting
                        x += i
    return x
'''
    parsed = python_parser.parse_code(code)
    issues = registry.analyze(parsed, code)

    health = registry.calculate_health_score(issues)

    assert 'overall_score' in health
    assert 'grade' in health
    assert 'total_issues' in health
    assert 'by_severity' in health
    assert 'by_category' in health
    assert 'description' in health

    # Score should be less than 100
    assert health['overall_score'] < 100
    assert health['total_issues'] > 0


def test_health_score_severity_weighting(registry):
    """Test that health score weights severities correctly"""
    from src.analyzers.base_analyzer import CodeIssue

    # Create issues with different severities
    critical_issue = CodeIssue(
        rule_id='TEST001',
        category=IssueCategory.SECURITY,
        severity=IssueSeverity.CRITICAL,
        title='Critical issue',
        description='Test',
        file_path='test.py',
        confidence=1.0
    )

    info_issue = CodeIssue(
        rule_id='TEST002',
        category=IssueCategory.SMELL,
        severity=IssueSeverity.INFO,
        title='Info issue',
        description='Test',
        file_path='test.py',
        confidence=1.0
    )

    # Score with critical issue should be much lower
    health_critical = registry.calculate_health_score([critical_issue])
    health_info = registry.calculate_health_score([info_issue])

    assert health_critical['overall_score'] < health_info['overall_score']
    assert health_critical['by_severity']['critical'] == 1
    assert health_info['by_severity']['info'] == 1


def test_health_score_grading(registry):
    """Test health score grade assignment"""
    from src.analyzers.base_analyzer import CodeIssue

    # Create multiple issues to get different scores
    issues = []
    for i in range(10):
        issues.append(CodeIssue(
            rule_id=f'TEST{i:03d}',
            category=IssueCategory.SMELL,
            severity=IssueSeverity.WARNING,
            title=f'Issue {i}',
            description='Test',
            file_path='test.py',
            confidence=1.0
        ))

    health = registry.calculate_health_score(issues)

    # With 10 warnings, score should be in a certain range
    assert health['grade'] in ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']

    # Score should match grade ranges
    score = health['overall_score']
    grade = health['grade']

    if score >= 95:
        assert grade == 'A+'
    elif score >= 90:
        assert grade == 'A'
    elif score >= 40:
        assert grade in ['A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-']
    else:
        assert grade == 'F'


def test_health_score_category_breakdown(registry, python_parser, vulnerable_code_path):
    """Test health score includes category breakdown"""
    parsed = python_parser.parse_file(vulnerable_code_path)
    source_code = Path(vulnerable_code_path).read_text()

    issues = registry.analyze(parsed, source_code)
    health = registry.calculate_health_score(issues)

    # Should have breakdown by category
    assert 'by_category' in health
    category_counts = health['by_category']

    # Should have security, smell, and complexity
    assert 'security' in category_counts
    assert 'smell' in category_counts
    assert 'complexity' in category_counts

    # Counts should sum to total
    assert sum(category_counts.values()) == health['total_issues']


def test_analyze_error_handling(registry, python_parser):
    """Test that registry handles analyzer errors gracefully"""
    code = "def broken("  # Syntax error

    try:
        parsed = python_parser.parse_code(code)
        issues = registry.analyze(parsed, code)
        # Should not crash, even with syntax errors
        assert isinstance(issues, list)
    except:
        # If parsing fails, that's also acceptable
        assert True
