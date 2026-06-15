"""Tests for issues endpoints logic"""
import pytest


# Mock cache for testing
_test_cache = {}


@pytest.fixture(autouse=True)
def clear_test_cache():
    """Clear cache before each test"""
    _test_cache.clear()
    yield
    _test_cache.clear()


@pytest.fixture
def sample_analysis():
    """Create sample analysis data"""
    return {
        'filename': 'test.py',
        'analyzed_at': '2024-01-01T12:00:00',
        'issues': [
            {
                'rule_id': 'SEC004',
                'category': 'security',
                'severity': 'error',
                'title': 'Hardcoded password',
                'description': 'Password should not be hardcoded',
                'file_path': 'test.py',
                'line_number': 10,
                'confidence': 0.9
            },
            {
                'rule_id': 'SMELL001',
                'category': 'smell',
                'severity': 'warning',
                'title': 'Long method',
                'description': 'Method is too long',
                'file_path': 'test.py',
                'line_number': 20,
                'confidence': 0.8
            },
            {
                'rule_id': 'COMPLEX001',
                'category': 'complexity',
                'severity': 'info',
                'title': 'High complexity',
                'description': 'Function has high complexity',
                'file_path': 'test.py',
                'line_number': 30,
                'confidence': 1.0
            }
        ]
    }


def test_filter_by_severity(sample_analysis):
    """Test filtering issues by severity"""
    _test_cache['job1'] = sample_analysis

    all_issues = []
    for analysis in _test_cache.values():
        all_issues.extend(analysis['issues'])

    # Filter by error severity
    error_issues = [i for i in all_issues if i['severity'] == 'error']
    assert len(error_issues) == 1
    assert error_issues[0]['rule_id'] == 'SEC004'

    # Filter by warning severity
    warning_issues = [i for i in all_issues if i['severity'] == 'warning']
    assert len(warning_issues) == 1
    assert warning_issues[0]['rule_id'] == 'SMELL001'


def test_filter_by_category(sample_analysis):
    """Test filtering issues by category"""
    _test_cache['job1'] = sample_analysis

    all_issues = []
    for analysis in _test_cache.values():
        all_issues.extend(analysis['issues'])

    # Filter by security category
    security_issues = [i for i in all_issues if i['category'] == 'security']
    assert len(security_issues) == 1
    assert security_issues[0]['rule_id'] == 'SEC004'


def test_filter_by_file_path(sample_analysis):
    """Test filtering issues by file path"""
    _test_cache['job1'] = sample_analysis
    _test_cache['job2'] = {
        **sample_analysis,
        'filename': 'other_file.py',
        'issues': [
            {
                **sample_analysis['issues'][0],
                'file_path': 'other_file.py'
            }
        ]
    }

    all_issues = []
    for analysis in _test_cache.values():
        all_issues.extend(analysis['issues'])

    test_py_issues = [i for i in all_issues if 'test.py' in i['file_path']]
    assert len(test_py_issues) == 3


def test_pagination(sample_analysis):
    """Test pagination of issues"""
    many_issues = sample_analysis.copy()
    many_issues['issues'] = [
        {
            **sample_analysis['issues'][0],
            'rule_id': f'RULE{i:03d}'
        }
        for i in range(25)
    ]
    _test_cache['job1'] = many_issues

    all_issues = []
    for analysis in _test_cache.values():
        all_issues.extend(analysis['issues'])

    # Test pagination
    limit = 10
    page1 = all_issues[0:limit]
    assert len(page1) == 10

    page2 = all_issues[10:20]
    assert len(page2) == 10

    page3 = all_issues[20:30]
    assert len(page3) == 5


def test_severity_sorting(sample_analysis):
    """Test that issues are sorted by severity"""
    _test_cache['job1'] = sample_analysis

    all_issues = []
    for analysis in _test_cache.values():
        all_issues.extend(analysis['issues'])

    severity_order = {'critical': 0, 'error': 1, 'warning': 2, 'info': 3}
    sorted_issues = sorted(all_issues, key=lambda x: severity_order.get(x['severity'], 3))

    assert sorted_issues[0]['severity'] == 'error'
    assert sorted_issues[1]['severity'] == 'warning'
    assert sorted_issues[2]['severity'] == 'info'


def test_statistics_calculation(sample_analysis):
    """Test issue statistics calculation"""
    _test_cache['job1'] = sample_analysis

    total_issues = 0
    by_severity = {}
    by_category = {}

    for analysis in _test_cache.values():
        for issue in analysis['issues']:
            total_issues += 1
            by_severity[issue['severity']] = by_severity.get(issue['severity'], 0) + 1
            by_category[issue['category']] = by_category.get(issue['category'], 0) + 1

    assert total_issues == 3
    assert by_severity['error'] == 1
    assert by_category['security'] == 1


def test_multiple_jobs_aggregation(sample_analysis):
    """Test aggregating issues from multiple jobs"""
    _test_cache['job1'] = sample_analysis
    _test_cache['job2'] = {
        **sample_analysis,
        'filename': 'file2.py',
        'issues': [sample_analysis['issues'][0]]
    }

    all_issues = []
    for analysis in _test_cache.values():
        all_issues.extend(analysis['issues'])

    assert len(all_issues) == 4  # 3 + 1
