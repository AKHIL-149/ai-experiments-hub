"""Tests for Analytics API Endpoints"""
import pytest
import sys
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

# Mock celery before imports
mock_celery = Mock()
mock_celery.celery_app = Mock()
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()
sys.modules['celery_app'] = mock_celery

from src.core.database import UserRole


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
                {'severity': 'critical', 'category': 'security', 'rule_id': 'sql_injection', 'title': 'SQL Injection', 'description': 'SQL injection'},
                {'severity': 'error', 'category': 'smell', 'rule_id': 'long_method', 'title': 'Long Method', 'description': 'Long method'}
            ]
        },
        {
            'filename': 'test2.py',
            'analyzed_at': (today - timedelta(days=2)).isoformat(),
            'metadata': {'lines_of_code': 200},
            'issues': [
                {'severity': 'warning', 'category': 'complexity', 'rule_id': 'high_cc', 'title': 'High Complexity', 'description': 'Complexity: 12'},
                {'severity': 'info', 'category': 'smell', 'rule_id': 'magic_number', 'title': 'Magic Number', 'description': 'Magic number'}
            ]
        }
    ]


def test_get_health_score_endpoint(sample_analyses):
    """Test health score endpoint returns correct structure"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=sample_analyses):
            client = TestClient(app)
            response = client.get("/api/analytics/health-score")

            assert response.status_code == 200
            data = response.json()

            # Verify structure
            assert 'score' in data
            assert 'grade' in data
            assert 'color' in data
            assert 'status' in data
            assert 'severity_counts' in data
            assert 'category_breakdown' in data

            # Verify score is calculated
            assert 0 <= data['score'] <= 100
            assert data['grade'] in ['A', 'B', 'C', 'D', 'F']


def test_get_analytics_trends_endpoint(sample_analyses):
    """Test trends endpoint returns time-series data"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=sample_analyses):
            client = TestClient(app)
            response = client.get("/api/analytics/trends?days=7&grouping=day")

            assert response.status_code == 200
            data = response.json()

            # Verify it's an array
            assert isinstance(data, list)

            # Verify structure if data exists
            if len(data) > 0:
                item = data[0]
                assert 'date' in item
                assert 'critical' in item
                assert 'error' in item
                assert 'warning' in item
                assert 'info' in item
                assert 'total' in item


def test_get_repository_analytics_endpoint(sample_analyses):
    """Test repository metrics endpoint"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=sample_analyses):
            client = TestClient(app)
            response = client.get("/api/analytics/repository")

            assert response.status_code == 200
            data = response.json()

            # Verify all expected fields
            assert 'total_analyses' in data
            assert 'total_issues' in data
            assert 'total_files' in data
            assert 'total_lines_of_code' in data
            assert 'avg_issues_per_file' in data
            assert 'avg_complexity' in data
            assert 'most_common_issues' in data
            assert 'severity_distribution' in data
            assert 'category_distribution' in data
            assert 'health_score' in data

            # Verify counts
            assert data['total_analyses'] == 2
            assert data['total_issues'] == 4
            assert data['total_files'] == 2


def test_get_analytics_insights_endpoint(sample_analyses):
    """Test insights endpoint returns actionable insights"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=sample_analyses):
            client = TestClient(app)
            response = client.get("/api/analytics/insights")

            assert response.status_code == 200
            data = response.json()

            # Should be an array
            assert isinstance(data, list)

            # Each insight should have required fields
            for insight in data:
                assert 'type' in insight
                assert 'severity' in insight
                assert 'title' in insight
                assert 'message' in insight
                assert 'recommendation' in insight


def test_compare_periods_endpoint(sample_analyses):
    """Test period comparison endpoint"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=sample_analyses):
            client = TestClient(app)
            response = client.get("/api/analytics/compare?current_days=3&previous_days=3")

            assert response.status_code == 200
            data = response.json()

            # Verify structure
            assert 'current' in data
            assert 'previous' in data
            assert 'changes' in data

            # Verify changes have correct structure
            assert 'total_issues' in data['changes']
            assert 'health_score' in data['changes']
            assert 'avg_complexity' in data['changes']

            # Each change should have these fields
            for change_key in ['total_issues', 'health_score', 'avg_complexity']:
                assert 'change' in data['changes'][change_key]
                assert 'percentage' in data['changes'][change_key]
                assert 'direction' in data['changes'][change_key]


def test_export_analytics_json(sample_analyses):
    """Test analytics export in JSON format"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=sample_analyses):
            client = TestClient(app)
            response = client.get("/api/analytics/export?format=json&days=7")

            assert response.status_code == 200
            data = response.json()

            # Verify structure
            assert 'export_date' in data
            assert 'period_days' in data
            assert 'health_score' in data
            assert 'repository_metrics' in data
            assert 'trends' in data

            # Verify period
            assert data['period_days'] == 7


def test_export_analytics_csv(sample_analyses):
    """Test analytics export in CSV format"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=sample_analyses):
            client = TestClient(app)
            response = client.get("/api/analytics/export?format=csv&days=7")

            assert response.status_code == 200

            # Verify content type
            assert response.headers['content-type'] == 'text/csv; charset=utf-8'

            # Verify Content-Disposition header for download
            assert 'Content-Disposition' in response.headers
            assert 'attachment' in response.headers['Content-Disposition']
            assert 'analytics_export_' in response.headers['Content-Disposition']

            # Verify CSV content
            content = response.text
            assert 'Health Score Metrics' in content
            assert 'Repository Metrics' in content
            assert 'Issue Trends' in content


def test_analytics_endpoints_require_auth():
    """Test that analytics endpoints require authentication"""
    from server import app

    client = TestClient(app)

    endpoints = [
        "/api/analytics/health-score",
        "/api/analytics/trends",
        "/api/analytics/repository",
        "/api/analytics/insights",
        "/api/analytics/compare",
        "/api/analytics/export"
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 401, f"{endpoint} should require auth"


def test_trends_with_different_groupings(sample_analyses):
    """Test trends endpoint with different grouping options"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    groupings = ['day', 'week', 'month']

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=sample_analyses):
            client = TestClient(app)

            for grouping in groupings:
                response = client.get(f"/api/analytics/trends?grouping={grouping}")
                assert response.status_code == 200
                data = response.json()
                assert isinstance(data, list)


def test_export_with_empty_data():
    """Test export endpoint handles empty data gracefully"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=[]):
            client = TestClient(app)
            response = client.get("/api/analytics/export?format=json")

            assert response.status_code == 200
            data = response.json()

            # Should still have structure even with no data
            assert 'health_score' in data
            assert 'repository_metrics' in data


def test_repository_analytics_calculates_averages(sample_analyses):
    """Test that repository analytics calculates averages correctly"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=sample_analyses):
            client = TestClient(app)
            response = client.get("/api/analytics/repository")

            assert response.status_code == 200
            data = response.json()

            # Should have calculated averages
            assert data['avg_issues_per_file'] == 2.0  # 4 issues / 2 files
            assert data['total_lines_of_code'] == 350  # 150 + 200
