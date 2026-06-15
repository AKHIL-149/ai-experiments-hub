"""Tests for CodeAnalyzerService"""
import pytest
from pathlib import Path
from src.services.code_analyzer_service import CodeAnalyzerService


@pytest.fixture
def service():
    """Create analyzer service instance"""
    return CodeAnalyzerService()


@pytest.fixture
def vulnerable_code():
    """Sample vulnerable code for testing"""
    return '''
import pickle
password = "hardcoded123"

def complex_function(a, b, c):
    result = 0
    if a:
        if b:
            if c:
                for i in range(10):
                    if i % 2:
                        result += i
    return result
'''


@pytest.fixture
def clean_code():
    """Sample clean code for testing"""
    return '''
def add(x, y):
    """Add two numbers"""
    return x + y

def multiply(x, y):
    """Multiply two numbers"""
    return x * y
'''


def test_analyze_code_success(service, vulnerable_code):
    """Test analyzing code successfully"""
    result = service.analyze_code(vulnerable_code, 'test.py')

    assert result['success'] is True
    assert result['file_path'] == 'test.py'
    assert 'report' in result

    report = result['report']
    assert 'total_issues' in report
    assert 'issues' in report
    assert 'health_score' in report
    assert 'stats' in report
    assert 'summary' in report


def test_analyze_code_finds_issues(service, vulnerable_code):
    """Test that analyzer finds issues in vulnerable code"""
    result = service.analyze_code(vulnerable_code, 'test.py')

    assert result['success'] is True
    report = result['report']

    # Should find multiple issues
    assert report['total_issues'] > 0

    # Should have issues by category
    assert len(report['by_category']) > 0

    # Should have issues by severity
    assert len(report['by_severity']) > 0


def test_analyze_code_clean(service, clean_code):
    """Test analyzing clean code"""
    result = service.analyze_code(clean_code, 'clean.py')

    assert result['success'] is True
    report = result['report']

    # Should find no issues
    assert report['total_issues'] == 0
    assert len(report['issues']) == 0
    assert 'No issues found' in report['summary']


def test_analyze_code_with_specific_analyzers(service, vulnerable_code):
    """Test running specific analyzers only"""
    # Run only security analyzer
    result = service.analyze_code(vulnerable_code, 'test.py', analyzer_ids=['security'])

    assert result['success'] is True
    report = result['report']

    # All issues should be security issues
    for issue in report['issues']:
        assert issue['category'] == 'security'


def test_report_structure(service, vulnerable_code):
    """Test that report has correct structure"""
    result = service.analyze_code(vulnerable_code, 'test.py')
    report = result['report']

    # Check main structure
    assert 'file_path' in report
    assert 'total_issues' in report
    assert 'issues' in report
    assert 'by_category' in report
    assert 'by_severity' in report
    assert 'by_rule' in report
    assert 'health_score' in report
    assert 'stats' in report
    assert 'summary' in report

    # Check health score structure
    health = report['health_score']
    assert 'overall_score' in health
    assert 'grade' in health
    assert 'total_issues' in health

    # Check stats structure
    stats = report['stats']
    assert 'total_lines' in stats
    assert 'code_lines' in stats
    assert 'blank_lines' in stats
    assert 'comment_lines' in stats


def test_issues_grouped_correctly(service, vulnerable_code):
    """Test that issues are grouped by category, severity, and rule"""
    result = service.analyze_code(vulnerable_code, 'test.py')
    report = result['report']

    # by_category should match total issues
    total_in_categories = sum(len(issues) for issues in report['by_category'].values())
    assert total_in_categories == report['total_issues']

    # by_severity should match total issues
    total_in_severities = sum(len(issues) for issues in report['by_severity'].values())
    assert total_in_severities == report['total_issues']

    # by_rule should match total issues
    total_in_rules = sum(len(issues) for issues in report['by_rule'].values())
    assert total_in_rules == report['total_issues']


def test_code_stats_calculation(service):
    """Test that code statistics are calculated correctly"""
    code = '''
# This is a comment
def test():
    # Another comment
    x = 1

    y = 2
    return x + y
'''
    result = service.analyze_code(code, 'test.py')
    stats = result['report']['stats']

    assert stats['total_lines'] == 9
    assert stats['comment_lines'] == 2
    assert stats['blank_lines'] >= 1
    assert stats['code_lines'] > 0


def test_summary_generation(service, vulnerable_code):
    """Test summary text generation"""
    result = service.analyze_code(vulnerable_code, 'test.py')
    summary = result['report']['summary']

    assert isinstance(summary, str)
    assert len(summary) > 0

    # Should contain health score
    assert 'Health score' in summary or 'score' in summary.lower()


def test_summary_for_clean_code(service, clean_code):
    """Test summary for code with no issues"""
    result = service.analyze_code(clean_code, 'test.py')
    summary = result['report']['summary']

    assert 'No issues found' in summary or 'looks good' in summary


def test_analyze_file_not_found(service):
    """Test analyzing non-existent file"""
    result = service.analyze_file('/nonexistent/file.py')

    assert result['success'] is False
    assert 'error' in result
    assert 'Failed to read file' in result['error']


def test_analyze_file_success(service, tmp_path):
    """Test analyzing actual file"""
    # Create temp file
    test_file = tmp_path / "test.py"
    test_file.write_text('''
def simple():
    return 42
''')

    result = service.analyze_file(str(test_file))

    assert result['success'] is True
    assert 'report' in result


def test_analyze_multiple_files(service, tmp_path):
    """Test analyzing multiple files"""
    # Create test files
    file1 = tmp_path / "file1.py"
    file1.write_text('password = "secret"')

    file2 = tmp_path / "file2.py"
    file2.write_text('def clean(): return 1')

    result = service.analyze_multiple_files([str(file1), str(file2)])

    assert result['success'] is True
    assert result['files_analyzed'] == 2
    assert 'overall_health' in result
    assert 'files' in result
    assert len(result['files']) == 2


def test_analyze_multiple_files_aggregation(service, tmp_path):
    """Test that multiple file analysis aggregates correctly"""
    # Create test files
    file1 = tmp_path / "bad1.py"
    file1.write_text('password = "secret123"')

    file2 = tmp_path / "bad2.py"
    file2.write_text('api_key = "sk_live_abc123"')

    result = service.analyze_multiple_files([str(file1), str(file2)])

    assert result['success'] is True
    assert result['files_analyzed'] == 2
    assert result['files_with_issues'] == 2
    assert result['total_issues'] > 0


def test_syntax_error_handling(service):
    """Test handling of syntax errors"""
    bad_code = "def broken("

    result = service.analyze_code(bad_code, 'bad.py')

    # Service should handle gracefully
    assert 'error' in result or result['success'] is False


def test_empty_code(service):
    """Test analyzing empty code"""
    result = service.analyze_code('', 'empty.py')

    assert result['success'] is True
    report = result['report']
    assert report['total_issues'] == 0


def test_health_score_in_report(service, vulnerable_code):
    """Test that health score is included in report"""
    result = service.analyze_code(vulnerable_code, 'test.py')
    health = result['report']['health_score']

    assert 'overall_score' in health
    assert 'grade' in health
    assert health['overall_score'] >= 0
    assert health['overall_score'] <= 100


def test_issue_serialization(service, vulnerable_code):
    """Test that issues are properly serialized to dicts"""
    result = service.analyze_code(vulnerable_code, 'test.py')

    if result['report']['total_issues'] > 0:
        issue = result['report']['issues'][0]

        # Should be a dict
        assert isinstance(issue, dict)

        # Should have required fields
        assert 'rule_id' in issue
        assert 'category' in issue
        assert 'severity' in issue
        assert 'title' in issue
        assert 'description' in issue
        assert 'file_path' in issue
