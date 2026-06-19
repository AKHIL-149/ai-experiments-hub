"""Tests for Dashboard Component"""
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


def test_dashboard_javascript_exists():
    """Test that dashboard JavaScript file exists"""
    import os
    js_path = os.path.join('static', 'js', 'dashboard.js')
    assert os.path.exists(js_path), "Dashboard JavaScript should exist"


def test_dashboard_css_exists():
    """Test that dashboard CSS file exists"""
    import os
    css_path = os.path.join('static', 'css', 'dashboard.css')
    assert os.path.exists(css_path), "Dashboard CSS should exist"


def test_dashboard_template_exists():
    """Test that enhanced dashboard template exists"""
    import os
    template_path = os.path.join('templates', 'dashboard_enhanced.html')
    assert os.path.exists(template_path), "Enhanced dashboard template should exist"


def test_dashboard_javascript_has_required_classes():
    """Test that JavaScript defines required component classes"""
    import os
    js_path = os.path.join('static', 'js', 'dashboard.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for main classes
    required_classes = [
        'class HealthScoreCalculator',
        'class HealthScoreCard',
        'class IssueTrendChart',
        'class IssueDistributionChart',
        'class ActivityFeed',
        'class StatsCard'
    ]

    for cls in required_classes:
        assert cls in content, f"Should define {cls}"

    # Check for key methods
    assert 'calculate' in content, "Should have calculate method for health score"
    assert 'render' in content, "Should have render methods"
    assert 'formatTimeAgo' in content, "Should have time formatting"


def test_dashboard_css_has_required_styles():
    """Test that CSS has dashboard component styles"""
    import os
    css_path = os.path.join('static', 'css', 'dashboard.css')

    with open(css_path, 'r') as f:
        content = f.read()

    # Check for required CSS classes
    required_classes = [
        '.health-score-card',
        '.stats-grid',
        '.dashboard-grid',
        '.activity-feed',
        '.chart-container'
    ]

    for css_class in required_classes:
        assert css_class in content, f"CSS should define {css_class}"

    # Check for responsive design
    assert '@media' in content, "CSS should include responsive design rules"


def test_dashboard_metrics_endpoint():
    """Test that dashboard metrics endpoint returns correct data structure"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    # Mock get_all_cached_analyses to return test data
    test_analyses = [
        {
            'filename': 'test/repo1/file1.py',
            'analyzed_at': datetime.now().isoformat(),
            'metadata': {'lines_of_code': 150},
            'issues': [
                {'severity': 'critical', 'category': 'security', 'title': 'SQL Injection'},
                {'severity': 'error', 'category': 'smell', 'title': 'Long Method'},
                {'severity': 'warning', 'category': 'complexity', 'title': 'High Complexity', 'description': 'Complexity: 15'}
            ]
        },
        {
            'filename': 'test/repo2/file2.py',
            'analyzed_at': datetime.now().isoformat(),
            'metadata': {'lines_of_code': 250},
            'issues': [
                {'severity': 'info', 'category': 'smell', 'title': 'Magic Number'}
            ]
        }
    ]

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=test_analyses):
            client = TestClient(app)
            response = client.get("/api/dashboard/metrics")

            assert response.status_code == 200
            data = response.json()

            # Verify structure
            assert "total_issues" in data
            assert "critical_issues" in data
            assert "error_issues" in data
            assert "warning_issues" in data
            assert "info_issues" in data
            assert "total_repositories" in data
            assert "total_lines_of_code" in data
            assert "avg_complexity" in data
            assert "test_coverage" in data

            # Verify counts
            assert data["total_issues"] == 4
            assert data["critical_issues"] == 1
            assert data["error_issues"] == 1
            assert data["warning_issues"] == 1
            assert data["info_issues"] == 1
            assert data["total_lines_of_code"] == 400


def test_dashboard_trends_endpoint():
    """Test that dashboard trends endpoint returns time-series data"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    # Create test data with dates
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    test_analyses = [
        {
            'filename': 'test.py',
            'analyzed_at': today.isoformat(),
            'issues': [
                {'severity': 'critical'},
                {'severity': 'error'}
            ]
        },
        {
            'filename': 'test2.py',
            'analyzed_at': yesterday.isoformat(),
            'issues': [
                {'severity': 'warning'},
                {'severity': 'info'}
            ]
        }
    ]

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=test_analyses):
            client = TestClient(app)
            response = client.get("/api/dashboard/trends?days=7")

            assert response.status_code == 200
            data = response.json()

            # Verify it's an array
            assert isinstance(data, list)
            assert len(data) > 0

            # Verify structure of each item
            if len(data) > 0:
                item = data[0]
                assert "date" in item
                assert "critical" in item
                assert "error" in item
                assert "warning" in item
                assert "info" in item


def test_dashboard_activity_endpoint():
    """Test that dashboard activity endpoint returns recent activities"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    test_analyses = [
        {
            'filename': 'test.py',
            'analyzed_at': datetime.now().isoformat(),
            'issues': [
                {'severity': 'critical', 'title': 'Security Issue', 'description': 'SQL injection detected'}
            ]
        }
    ]

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.get_all_cached_analyses', return_value=test_analyses):
            client = TestClient(app)
            response = client.get("/api/dashboard/activity?limit=5")

            assert response.status_code == 200
            data = response.json()

            # Verify it's an array
            assert isinstance(data, list)

            # Verify structure if activities exist
            if len(data) > 0:
                activity = data[0]
                assert "type" in activity
                assert "title" in activity
                assert "description" in activity
                assert "timestamp" in activity
                assert "icon" in activity

                # Verify activity types
                assert activity["type"] in ["analysis", "issue_found"]


def test_dashboard_template_includes_chartjs():
    """Test that dashboard template includes Chart.js library"""
    import os
    template_path = os.path.join('templates', 'dashboard_enhanced.html')

    with open(template_path, 'r') as f:
        content = f.read()

    # Check for Chart.js CDN
    assert 'chart.js' in content.lower(), "Template should include Chart.js library"
    assert 'canvas' in content.lower(), "Template should have canvas elements for charts"

    # Check for dashboard component initialization
    assert 'HealthScoreCard' in content or 'healthScoreCard' in content, "Template should initialize HealthScoreCard"
    assert 'IssueTrendChart' in content or 'issueTrendChart' in content, "Template should initialize IssueTrendChart"
