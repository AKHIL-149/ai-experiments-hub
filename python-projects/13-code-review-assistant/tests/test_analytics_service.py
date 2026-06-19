"""Tests for Analytics Service"""
import pytest
from datetime import datetime, timedelta
from src.services.analytics_service import AnalyticsService, analytics_service


@pytest.fixture
def service():
    """Create analytics service instance"""
    return AnalyticsService()


@pytest.fixture
def sample_issues():
    """Sample issues for testing"""
    return [
        {'severity': 'critical', 'category': 'security', 'rule_id': 'sql_injection', 'description': 'SQL injection'},
        {'severity': 'error', 'category': 'smell', 'rule_id': 'long_method', 'description': 'Long method'},
        {'severity': 'warning', 'category': 'complexity', 'rule_id': 'high_cc', 'description': 'Complexity: 15'},
        {'severity': 'info', 'category': 'smell', 'rule_id': 'magic_number', 'description': 'Magic number'},
    ]


@pytest.fixture
def sample_analyses():
    """Sample analyses for testing"""
    today = datetime.now()
    return [
        {
            'filename': 'test1.py',
            'analyzed_at': (today - timedelta(days=1)).isoformat(),
            'metadata': {'lines_of_code': 150},
            'issues': [
                {'severity': 'critical', 'category': 'security', 'rule_id': 'sql_injection'},
                {'severity': 'error', 'category': 'smell', 'rule_id': 'long_method'}
            ]
        },
        {
            'filename': 'test2.py',
            'analyzed_at': (today - timedelta(days=2)).isoformat(),
            'metadata': {'lines_of_code': 200},
            'issues': [
                {'severity': 'warning', 'category': 'complexity', 'rule_id': 'high_cc', 'description': 'Complexity: 12'},
                {'severity': 'info', 'category': 'smell', 'rule_id': 'magic_number'}
            ]
        }
    ]


def test_calculate_health_score_perfect(service):
    """Test health score calculation for perfect code"""
    result = service.calculate_health_score([])

    assert result['score'] == 100.0
    assert result['grade'] == 'A'
    assert result['status'] == 'Excellent'
    assert result['total_issues'] == 0


def test_calculate_health_score_with_issues(service, sample_issues):
    """Test health score calculation with various issues"""
    result = service.calculate_health_score(sample_issues)

    # Score should be reduced based on severity
    # critical: -10, error: -5, warning: -2, info: -0.5
    # 100 - 10 - 5 - 2 - 0.5 = 82.5
    assert result['score'] == 82.5
    assert result['grade'] == 'B'
    assert result['total_issues'] == 4
    assert result['severity_counts']['critical'] == 1
    assert result['severity_counts']['error'] == 1


def test_calculate_health_score_with_code_stats(service, sample_issues):
    """Test health score calculation with code statistics"""
    code_stats = {
        'avg_complexity': 18,  # High complexity: penalty of (18-15) * 0.5 = 1.5
        'test_coverage': 85    # Good coverage: bonus of 5
    }

    result = service.calculate_health_score(sample_issues, code_stats)

    # 100 - 10 - 5 - 2 - 0.5 - 1.5 + 5 = 86
    assert result['score'] == 86.0
    assert result['metrics']['avg_complexity'] == 18
    assert result['metrics']['test_coverage'] == 85


def test_health_score_grading(service):
    """Test health score to grade conversion"""
    test_cases = [
        ([], 'A'),  # 100
        ([{'severity': 'error'} for _ in range(3)], 'B'),  # 85
        ([{'severity': 'error'} for _ in range(5)], 'C'),  # 75
        ([{'severity': 'error'} for _ in range(7)], 'D'),  # 65
        ([{'severity': 'critical'} for _ in range(5)], 'F'),  # 50
    ]

    for issues, expected_grade in test_cases:
        result = service.calculate_health_score(issues)
        assert result['grade'] == expected_grade


def test_calculate_category_breakdown(service, sample_issues):
    """Test category breakdown calculation"""
    breakdown = service._calculate_category_breakdown(sample_issues)

    assert breakdown['security'] == 1
    assert breakdown['smell'] == 2
    assert breakdown['complexity'] == 1


def test_calculate_issue_trends_daily(service, sample_analyses):
    """Test issue trends calculation with daily grouping"""
    trends = service.calculate_issue_trends(sample_analyses, days=7, grouping='day')

    assert isinstance(trends, list)
    assert len(trends) > 0

    # Check structure
    for trend in trends:
        assert 'date' in trend
        assert 'critical' in trend
        assert 'error' in trend
        assert 'warning' in trend
        assert 'info' in trend
        assert 'total' in trend


def test_calculate_issue_trends_empty(service):
    """Test issue trends with no data"""
    trends = service.calculate_issue_trends([], days=7)

    assert isinstance(trends, list)
    # Should still have date buckets, just with 0 counts
    assert all(trend['total'] == 0 for trend in trends)


def test_calculate_repository_metrics(service, sample_analyses):
    """Test repository metrics calculation"""
    metrics = service.calculate_repository_metrics(sample_analyses)

    assert metrics['total_analyses'] == 2
    assert metrics['total_issues'] == 4
    assert metrics['total_files'] == 2
    assert metrics['total_lines_of_code'] == 350
    assert metrics['avg_issues_per_file'] == 2.0
    assert 'severity_distribution' in metrics
    assert 'category_distribution' in metrics
    assert 'health_score' in metrics


def test_calculate_repository_metrics_empty(service):
    """Test repository metrics with no data"""
    metrics = service.calculate_repository_metrics([])

    assert metrics['total_analyses'] == 0
    assert metrics['total_issues'] == 0
    assert metrics['health_score'] == 100


def test_aggregate_time_series_sum(service):
    """Test time-series aggregation with sum"""
    data = [
        {'date': '2024-01-01', 'value': 10},
        {'date': '2024-01-01', 'value': 20},
        {'date': '2024-01-02', 'value': 15},
    ]

    result = service.aggregate_time_series(data, 'value', aggregation='sum')

    assert len(result) == 2
    assert result[0]['value'] == 30  # 10 + 20
    assert result[1]['value'] == 15


def test_aggregate_time_series_avg(service):
    """Test time-series aggregation with average"""
    data = [
        {'date': '2024-01-01', 'value': 10},
        {'date': '2024-01-01', 'value': 20},
        {'date': '2024-01-02', 'value': 15},
    ]

    result = service.aggregate_time_series(data, 'value', aggregation='avg')

    assert len(result) == 2
    assert result[0]['value'] == 15.0  # (10 + 20) / 2
    assert result[1]['value'] == 15.0


def test_compare_periods(service, sample_analyses):
    """Test period comparison"""
    current = sample_analyses
    previous = [sample_analyses[0]]  # Only one analysis in previous period

    result = service.compare_periods(current, previous)

    assert 'current' in result
    assert 'previous' in result
    assert 'changes' in result

    # Current should have more issues
    assert result['current']['total_issues'] > result['previous']['total_issues']
    assert result['changes']['total_issues']['direction'] == 'up'


def test_compare_periods_improvement(service, sample_analyses):
    """Test period comparison showing improvement"""
    current = [sample_analyses[0]]  # Fewer issues
    previous = sample_analyses  # More issues

    result = service.compare_periods(current, previous)

    # Current should have fewer issues (improvement)
    assert result['changes']['total_issues']['direction'] == 'down'


def test_generate_insights_healthy_code(service):
    """Test insights generation for healthy code"""
    metrics = {
        'total_issues': 10,
        'total_files': 5,
        'health_score': 95,
        'avg_complexity': 5,
        'category_distribution': {}
    }

    insights = service.generate_insights(metrics)

    # Should have minimal or no insights for healthy code
    assert isinstance(insights, list)


def test_generate_insights_problematic_code(service):
    """Test insights generation for problematic code"""
    metrics = {
        'total_issues': 150,
        'total_files': 10,
        'health_score': 45,
        'avg_complexity': 18,
        'category_distribution': {
            'security': {'count': 10, 'percentage': 6.7},
            'smell': {'count': 100, 'percentage': 66.7}
        }
    }

    insights = service.generate_insights(metrics)

    # Should generate multiple insights
    assert len(insights) > 0

    # Check for specific insight types
    insight_types = [i['type'] for i in insights]
    assert 'high_issue_count' in insight_types
    assert 'low_health_score' in insight_types
    assert 'high_complexity' in insight_types
    assert 'security_issues' in insight_types


def test_extract_complexity_value(service):
    """Test complexity value extraction from description"""
    assert service._extract_complexity_value("Complexity: 15") == 15
    assert service._extract_complexity_value("Cyclomatic complexity of 12") == 12
    assert service._extract_complexity_value("No number here") is None


def test_global_analytics_service_instance():
    """Test that global instance exists and is usable"""
    assert analytics_service is not None
    assert isinstance(analytics_service, AnalyticsService)

    # Can call methods on global instance
    result = analytics_service.calculate_health_score([])
    assert result['score'] == 100.0


def test_calculate_distribution(service):
    """Test distribution calculation"""
    items = [
        {'category': 'security'},
        {'category': 'security'},
        {'category': 'smell'},
        {'category': 'complexity'},
    ]

    dist = service._calculate_distribution(items, 'category')

    assert dist['security']['count'] == 2
    assert dist['security']['percentage'] == 50.0
    assert dist['smell']['count'] == 1
    assert dist['smell']['percentage'] == 25.0


def test_most_common_issues(service):
    """Test most common issues tracking"""
    analyses = [
        {
            'filename': 'test.py',
            'analyzed_at': datetime.now().isoformat(),
            'issues': [
                {'category': 'security', 'rule_id': 'sql_injection'},
                {'category': 'security', 'rule_id': 'sql_injection'},
                {'category': 'smell', 'rule_id': 'long_method'},
            ]
        }
    ]

    metrics = service.calculate_repository_metrics(analyses)

    assert len(metrics['most_common_issues']) > 0
    # SQL injection should be most common (appears twice)
    assert metrics['most_common_issues'][0]['count'] == 2
    assert 'sql_injection' in metrics['most_common_issues'][0]['type']
