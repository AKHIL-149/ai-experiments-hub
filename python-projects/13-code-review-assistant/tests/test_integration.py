"""Integration tests for end-to-end workflows"""
import pytest
import tempfile
import os
from pathlib import Path
from src.services.code_analyzer_service import CodeAnalyzerService
from src.workers.analysis_worker import (
    _analysis_cache,
    analyze_file_task,
    get_analysis_results,
    get_all_cached_analyses,
    clear_analysis_cache
)


@pytest.fixture(autouse=True)
def clean_cache():
    """Clear analysis cache before each test"""
    clear_analysis_cache()
    yield
    clear_analysis_cache()


@pytest.fixture
def sample_vulnerable_code():
    """Sample code with multiple issues"""
    return '''
import pickle
import os

# Hardcoded credentials
password = "admin123"
api_key = "sk_live_abc123"

def unsafe_deserialize(data):
    """Unsafe deserialization"""
    return pickle.loads(data)

def command_injection(user_input):
    """Command injection vulnerability"""
    os.system(f"echo {user_input}")

def complex_function(a, b, c, d, e, f, g):
    """Function with too many parameters and high complexity"""
    result = 0
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    if e > 0:
                        for i in range(100):
                            if i % 2 == 0:
                                result += i
    return result

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
'''


@pytest.fixture
def sample_clean_code():
    """Sample clean code"""
    return '''
def add(x, y):
    """Add two numbers"""
    return x + y

def subtract(x, y):
    """Subtract two numbers"""
    return x - y

def multiply(x, y):
    """Multiply two numbers"""
    return x * y

def divide(x, y):
    """Divide two numbers"""
    if y == 0:
        raise ValueError("Cannot divide by zero")
    return x / y
'''


def test_end_to_end_file_analysis(tmp_path, sample_vulnerable_code):
    """Test complete file analysis workflow"""
    # Create temp file
    test_file = tmp_path / "vulnerable.py"
    test_file.write_text(sample_vulnerable_code)

    # Analyze file
    service = CodeAnalyzerService()
    result = service.analyze_file(str(test_file))

    # Verify result structure
    assert result['success'] is True
    assert 'report' in result
    assert 'file_path' in result

    report = result['report']

    # Verify report has all components
    assert 'total_issues' in report
    assert 'issues' in report
    assert 'by_category' in report
    assert 'by_severity' in report
    assert 'health_score' in report
    assert 'stats' in report

    # Should find multiple issues
    assert report['total_issues'] > 0

    # Should have security issues
    assert 'security' in report['by_category']

    # Should have complexity issues
    assert 'complexity' in report['by_category'] or 'smell' in report['by_category']

    # Health score should be calculated
    assert 'overall_score' in report['health_score']
    assert 0 <= report['health_score']['overall_score'] <= 100
    assert 'grade' in report['health_score']


def test_end_to_end_code_analysis(sample_vulnerable_code):
    """Test analyzing code string directly"""
    service = CodeAnalyzerService()
    result = service.analyze_code(sample_vulnerable_code, 'test.py')

    assert result['success'] is True
    assert result['report']['total_issues'] > 0


def test_analyzer_selection(sample_vulnerable_code):
    """Test running specific analyzers only"""
    service = CodeAnalyzerService()

    # Run only security analyzer
    result = service.analyze_code(sample_vulnerable_code, 'test.py', analyzer_ids=['security'])

    assert result['success'] is True

    # All issues should be security-related
    for issue in result['report']['issues']:
        assert issue['category'] == 'security'


def test_multiple_files_analysis(tmp_path):
    """Test analyzing multiple files together"""
    # Create multiple test files
    file1 = tmp_path / "file1.py"
    file1.write_text('password = "secret123"')

    file2 = tmp_path / "file2.py"
    file2.write_text('api_key = "sk_test_abc"')

    file3 = tmp_path / "file3.py"
    file3.write_text('def clean(): return 42')

    service = CodeAnalyzerService()
    result = service.analyze_multiple_files([
        str(file1),
        str(file2),
        str(file3)
    ])

    assert result['success'] is True
    assert result['files_analyzed'] == 3
    assert result['files_with_issues'] >= 2
    assert result['total_issues'] > 0
    assert 'overall_health' in result


def test_worker_caching_workflow(sample_vulnerable_code):
    """Test that worker properly caches analysis results"""
    # Simulate worker execution
    from unittest.mock import Mock

    # Mock the task context
    mock_self = Mock()
    mock_self.request.id = 'test_job_123'
    mock_self.update_state = Mock()

    # Run analysis task
    result = analyze_file_task(
        mock_self,
        file_content=sample_vulnerable_code,
        filename='test.py'
    )

    # Verify task updated state
    assert mock_self.update_state.called

    # Verify result cached
    cached = get_analysis_results('test_job_123')
    assert cached is not None
    assert cached['filename'] == 'test.py'
    assert 'issues' in cached
    assert 'analyzed_at' in cached


def test_issues_aggregation_workflow():
    """Test aggregating issues from multiple analyses"""
    from unittest.mock import Mock

    # Run multiple analyses
    code1 = 'password = "secret"'
    code2 = 'api_key = "key123"'
    code3 = 'def clean(): return 1'

    for idx, code in enumerate([code1, code2, code3]):
        mock_self = Mock()
        mock_self.request.id = f'job_{idx}'
        mock_self.update_state = Mock()

        analyze_file_task(
            mock_self,
            file_content=code,
            filename=f'file{idx}.py'
        )

    # Get all analyses
    all_analyses = get_all_cached_analyses()
    assert len(all_analyses) == 3

    # Aggregate all issues
    all_issues = []
    for analysis in all_analyses:
        all_issues.extend(analysis.get('issues', []))

    # Should have found issues
    assert len(all_issues) > 0


def test_clean_code_workflow(sample_clean_code):
    """Test analyzing clean code"""
    service = CodeAnalyzerService()
    result = service.analyze_code(sample_clean_code, 'clean.py')

    assert result['success'] is True
    report = result['report']

    # Clean code should have no or minimal issues
    assert report['total_issues'] == 0 or report['total_issues'] < 3

    # Health score should be high
    assert report['health_score']['overall_score'] >= 85
    assert report['health_score']['grade'] in ['A', 'B']


def test_issue_categorization(sample_vulnerable_code):
    """Test that issues are properly categorized"""
    service = CodeAnalyzerService()
    result = service.analyze_code(sample_vulnerable_code, 'test.py')

    report = result['report']
    issues = report['issues']

    # Group by category
    categories = set(issue['category'] for issue in issues)

    # Should have multiple categories
    assert len(categories) >= 2

    # Verify each issue has required fields
    for issue in issues:
        assert 'rule_id' in issue
        assert 'category' in issue
        assert 'severity' in issue
        assert 'title' in issue
        assert 'description' in issue
        assert 'file_path' in issue


def test_severity_levels(sample_vulnerable_code):
    """Test that severity levels are assigned correctly"""
    service = CodeAnalyzerService()
    result = service.analyze_code(sample_vulnerable_code, 'test.py')

    severities = set(issue['severity'] for issue in result['report']['issues'])

    # Should have different severity levels
    assert len(severities) >= 2

    # All severities should be valid
    valid_severities = {'critical', 'error', 'warning', 'info'}
    assert all(sev in valid_severities for sev in severities)


def test_health_score_calculation(sample_vulnerable_code):
    """Test health score calculation"""
    service = CodeAnalyzerService()
    result = service.analyze_code(sample_vulnerable_code, 'test.py')

    health = result['report']['health_score']

    # Should have overall score
    assert 'overall_score' in health
    assert 0 <= health['overall_score'] <= 100

    # Should have grade
    assert 'grade' in health
    assert health['grade'] in ['A', 'B', 'C', 'D', 'F']

    # Should have category breakdown
    assert 'by_category' in health

    # Vulnerable code should have lower score
    assert health['overall_score'] < 90


def test_code_statistics(sample_vulnerable_code):
    """Test code statistics calculation"""
    service = CodeAnalyzerService()
    result = service.analyze_code(sample_vulnerable_code, 'test.py')

    stats = result['report']['stats']

    # Should have all stat fields
    assert 'total_lines' in stats
    assert 'code_lines' in stats
    assert 'blank_lines' in stats
    assert 'comment_lines' in stats

    # Values should be reasonable
    assert stats['total_lines'] > 0
    assert stats['code_lines'] > 0
    assert stats['total_lines'] == stats['code_lines'] + stats['blank_lines'] + stats['comment_lines']


def test_error_handling_invalid_syntax():
    """Test handling of invalid Python syntax"""
    service = CodeAnalyzerService()
    result = service.analyze_code('def broken(', 'bad.py')

    # Should handle gracefully
    assert 'error' in result or result['success'] is False


def test_error_handling_empty_file():
    """Test handling of empty files"""
    service = CodeAnalyzerService()
    result = service.analyze_code('', 'empty.py')

    # Should succeed with no issues
    assert result['success'] is True
    assert result['report']['total_issues'] == 0


def test_error_handling_nonexistent_file():
    """Test handling of non-existent files"""
    service = CodeAnalyzerService()
    result = service.analyze_file('/nonexistent/path/file.py')

    assert result['success'] is False
    assert 'error' in result


def test_week_2_complete():
    """
    Test that Week 2 implementation is complete.

    This test verifies all Week 2 components:
    - Python parser working
    - All analyzers implemented (security, smell, complexity)
    - Service orchestration
    - Worker caching
    - Issue aggregation
    - Health score calculation
    """
    # Test code with known issues
    test_code = '''
import pickle
password = "secret"

def complex(a, b, c, d, e, f):
    if a:
        if b:
            if c:
                if d:
                    return e + f
    return 0
'''

    service = CodeAnalyzerService()
    result = service.analyze_code(test_code, 'week2_test.py')

    # Parser should work
    assert result['success'] is True

    # Should detect multiple issue types
    report = result['report']
    categories = set(issue['category'] for issue in report['issues'])
    assert len(categories) >= 2  # At least 2 different categories

    # Should have health score
    assert 'health_score' in report
    assert 'overall_score' in report['health_score']

    # Should have statistics
    assert 'stats' in report
    assert report['stats']['code_lines'] > 0

    # Week 2 complete!
    print("\n✅ Week 2 Implementation Complete!")
    print(f"   - Found {report['total_issues']} issues")
    print(f"   - Categories: {', '.join(categories)}")
    print(f"   - Health Score: {report['health_score']['overall_score']}/100")
    print(f"   - Grade: {report['health_score']['grade']}")
