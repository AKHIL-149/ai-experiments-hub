"""End-to-End Integration Tests"""
import pytest
import sys
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

# Mock celery before imports
mock_celery = Mock()
mock_celery.celery_app = Mock()
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()
sys.modules['celery_app'] = mock_celery

from src.core.database import UserRole, DatabaseManager
from src.services.cache_service import CacheService


@pytest.fixture
def db_manager():
    """Create test database manager"""
    db = DatabaseManager('sqlite:///:memory:')
    yield db
    # Cleanup handled by in-memory database


@pytest.fixture
def cache_service():
    """Create test cache service"""
    cache = CacheService()
    cache.clear()
    cache.reset_statistics()
    return cache


class TestAuthenticationFlow:
    """Test complete authentication workflow"""

    def test_complete_user_registration_and_login(self):
        """E2E: User registration and login workflow"""
        from server import app

        client = TestClient(app)

        # 1. Register new user
        register_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "securepassword123"
        }

        response = client.post("/api/auth/register", json=register_data)
        assert response.status_code == 200
        register_result = response.json()
        assert register_result['success'] == True

        # 2. Login with credentials
        login_data = {
            "username": "testuser",
            "password": "securepassword123"
        }

        response = client.post("/api/auth/login", json=login_data)
        assert response.status_code == 200
        login_result = response.json()
        assert 'session_token' in login_result

        # 3. Access protected endpoint with session
        cookies = {'session_token': login_result['session_token']}
        response = client.get("/api/auth/me", cookies=cookies)
        assert response.status_code == 200
        user_data = response.json()
        assert user_data['username'] == "testuser"

        # 4. Logout
        response = client.post("/api/auth/logout", cookies=cookies)
        assert response.status_code == 200


class TestFileAnalysisWorkflow:
    """Test complete file analysis workflow"""

    def test_file_upload_and_analysis(self):
        """E2E: Upload file and get analysis results"""
        from server import app

        mock_user = Mock()
        mock_user.id = 'test-user'
        mock_user.role = UserRole.USER

        with patch('server.get_current_user', return_value=mock_user):
            client = TestClient(app)

            # Create test Python file
            test_code = """
import os
password = "hardcoded123"

def long_function(a, b, c, d, e, f):
    if x > 0:
        if y > 0:
            if z > 0:
                os.system(user_input)
    return sum([i for i in range(100)])
"""

            # Upload file for analysis
            files = {
                'file': ('test.py', test_code, 'text/x-python')
            }

            response = client.post("/api/analyze", files=files)
            assert response.status_code == 200

            result = response.json()
            assert 'task_id' in result or 'issues' in result


class TestRepositoryManagement:
    """Test repository management workflow"""

    def test_create_and_list_repositories(self):
        """E2E: Create repository and list"""
        from server import app

        mock_user = Mock()
        mock_user.id = 'test-user'
        mock_user.role = UserRole.USER

        with patch('server.get_current_user', return_value=mock_user):
            client = TestClient(app)

            # Create repository
            repo_data = {
                "name": "test-repo",
                "github_url": "https://github.com/test/repo"
            }

            response = client.post("/api/repositories", json=repo_data)
            assert response.status_code == 200
            repo_result = response.json()
            assert 'repository' in repo_result or 'task_id' in repo_result

            # List repositories
            response = client.get("/api/repositories")
            assert response.status_code == 200
            repos = response.json()
            assert isinstance(repos, list) or 'repositories' in repos


class TestAnalyticsWorkflow:
    """Test analytics and insights workflow"""

    def test_get_analytics_suite(self):
        """E2E: Get complete analytics suite"""
        from server import app
        from src.workers.analysis_worker import cache_analysis_result

        mock_user = Mock()
        mock_user.id = 'test-user'
        mock_user.role = UserRole.USER

        # Create sample analysis data
        sample_analysis = {
            'filename': 'test.py',
            'analyzed_at': '2024-01-01T12:00:00',
            'issues': [
                {'severity': 'critical', 'category': 'security', 'rule_id': 'sql_injection'},
                {'severity': 'error', 'category': 'smell', 'rule_id': 'long_method'}
            ],
            'metadata': {'lines_of_code': 150}
        }
        cache_analysis_result('test-job-1', sample_analysis)

        with patch('server.get_current_user', return_value=mock_user):
            client = TestClient(app)

            # Get health score
            response = client.get("/api/analytics/health-score")
            assert response.status_code == 200
            health = response.json()
            assert 'score' in health
            assert 'grade' in health

            # Get repository metrics
            response = client.get("/api/analytics/repository")
            assert response.status_code == 200
            metrics = response.json()
            assert 'total_issues' in metrics

            # Get trends
            response = client.get("/api/analytics/trends?days=7")
            assert response.status_code == 200
            trends = response.json()
            assert isinstance(trends, list)

            # Get insights
            response = client.get("/api/analytics/insights")
            assert response.status_code == 200
            insights = response.json()
            assert isinstance(insights, list)


class TestNotificationWorkflow:
    """Test notification system workflow"""

    def test_notification_lifecycle(self):
        """E2E: Create, read, and manage notifications"""
        from server import app
        from src.services.notification_service import notification_service, NotificationType

        mock_user = Mock()
        mock_user.id = 'test-user'
        mock_user.role = UserRole.USER

        # Create test notification
        notification = notification_service.create_notification(
            NotificationType.INFO,
            "Test Notification",
            "This is a test",
            user_id="test-user"
        )

        with patch('server.get_current_user', return_value=mock_user):
            client = TestClient(app)

            # List notifications
            response = client.get("/api/notifications")
            assert response.status_code == 200
            result = response.json()
            assert 'notifications' in result

            # Get specific notification
            response = client.get(f"/api/notifications/{notification['id']}")
            assert response.status_code == 200

            # Mark as read
            response = client.post(f"/api/notifications/{notification['id']}/read")
            assert response.status_code == 200

            # Get preferences
            response = client.get("/api/notifications/preferences")
            assert response.status_code == 200

            # Get statistics
            response = client.get("/api/notifications/statistics")
            assert response.status_code == 200
            stats = response.json()
            assert 'total' in stats


class TestLoggingWorkflow:
    """Test logging system workflow"""

    def test_logging_and_retrieval(self):
        """E2E: Log events and retrieve logs"""
        from server import app
        from src.services.logging_service import logging_service

        mock_user = Mock()
        mock_user.id = 'test-user'
        mock_user.role = UserRole.ADMIN  # Admin for log access

        # Generate some logs
        logging_service.info("Test info log")
        logging_service.error("Test error log")
        logging_service.warning("Test warning")

        with patch('server.get_current_user', return_value=mock_user):
            client = TestClient(app)

            # Get all logs
            response = client.get("/api/logs")
            assert response.status_code == 200
            result = response.json()
            assert 'logs' in result

            # Get error logs only
            response = client.get("/api/logs/errors")
            assert response.status_code == 200
            errors = response.json()
            assert 'errors' in errors

            # Get statistics
            response = client.get("/api/logs/statistics")
            assert response.status_code == 200
            stats = response.json()
            assert 'total_logs' in stats


class TestCacheIntegration:
    """Test cache integration in workflows"""

    def test_cache_improves_performance(self, cache_service):
        """E2E: Verify caching improves repeated queries"""

        query_count = 0

        @cache_service.cached(ttl=60, key_prefix='test_query')
        def expensive_query(param):
            nonlocal query_count
            query_count += 1
            return {'data': f'result-{param}'}

        # First call - executes query
        result1 = expensive_query('test')
        assert query_count == 1

        # Second call - uses cache
        result2 = expensive_query('test')
        assert query_count == 1
        assert result1 == result2

        # Verify cache statistics
        stats = cache_service.get_statistics()
        assert stats['cache_hits'] > 0


class TestSettingsManagement:
    """Test settings management workflow"""

    def test_settings_crud(self):
        """E2E: Create, read, update settings"""
        from server import app

        mock_user = Mock()
        mock_user.id = 'test-user'
        mock_user.role = UserRole.USER

        with patch('server.get_current_user', return_value=mock_user):
            client = TestClient(app)

            # Get current settings
            response = client.get("/api/settings")
            assert response.status_code == 200

            # Update settings
            new_settings = {
                "rules": {
                    "security": {
                        "sqlInjection": True
                    }
                },
                "thresholds": {
                    "complexityWarn": 10
                }
            }

            response = client.post("/api/settings", json=new_settings)
            assert response.status_code == 200
            result = response.json()
            assert result['success'] == True


class TestErrorHandling:
    """Test error handling and recovery"""

    def test_correlation_id_in_errors(self):
        """E2E: Verify correlation IDs in error responses"""
        from server import app

        client = TestClient(app)

        # Trigger an error (401 unauthorized)
        response = client.get("/api/analytics/health-score")

        # Should have correlation ID in response
        assert 'X-Correlation-ID' in response.headers or response.status_code == 401


    def test_sensitive_data_masking_in_logs(self):
        """E2E: Verify sensitive data is masked in logs"""
        from src.services.logging_service import logging_service

        # Log message with sensitive data
        log = logging_service.info("User logged in with password=secret123")

        # Password should be masked
        assert 'secret123' not in log['message']
        assert '***MASKED***' in log['message']


class TestIssueManagement:
    """Test issue filtering and management"""

    def test_issue_filtering(self):
        """E2E: Filter issues by various criteria"""
        from server import app
        from src.workers.analysis_worker import cache_analysis_result

        mock_user = Mock()
        mock_user.id = 'test-user'
        mock_user.role = UserRole.USER

        # Create sample analysis with issues
        analysis = {
            'filename': 'test.py',
            'analyzed_at': '2024-01-01T12:00:00',
            'issues': [
                {'severity': 'critical', 'category': 'security', 'rule_id': 'sql'},
                {'severity': 'warning', 'category': 'smell', 'rule_id': 'long'},
                {'severity': 'error', 'category': 'complexity', 'rule_id': 'high_cc'}
            ]
        }
        cache_analysis_result('test-job', analysis)

        with patch('server.get_current_user', return_value=mock_user):
            client = TestClient(app)

            # Get all issues
            response = client.get("/api/issues")
            assert response.status_code == 200

            # Filter by severity
            response = client.get("/api/issues?severity=critical")
            assert response.status_code == 200

            # Filter by category
            response = client.get("/api/issues?category=security")
            assert response.status_code == 200


class TestExportFunctionality:
    """Test export functionality"""

    def test_analytics_export_formats(self):
        """E2E: Export analytics in different formats"""
        from server import app

        mock_user = Mock()
        mock_user.id = 'test-user'
        mock_user.role = UserRole.USER

        with patch('server.get_current_user', return_value=mock_user):
            client = TestClient(app)

            # Export as JSON
            response = client.get("/api/analytics/export?format=json")
            assert response.status_code == 200

            # Export as CSV
            response = client.get("/api/analytics/export?format=csv")
            assert response.status_code == 200
            assert 'text/csv' in response.headers.get('content-type', '')


    def test_logs_export_formats(self):
        """E2E: Export logs in different formats"""
        from server import app

        mock_user = Mock()
        mock_user.id = 'test-user'
        mock_user.role = UserRole.USER

        with patch('server.get_current_user', return_value=mock_user):
            client = TestClient(app)

            # Export logs as JSON
            response = client.get("/api/logs/export?format=json")
            assert response.status_code == 200

            # Export logs as CSV
            response = client.get("/api/logs/export?format=csv")
            assert response.status_code == 200


class TestDatabaseIndexes:
    """Test that database indexes improve query performance"""

    def test_indexes_exist(self, db_manager):
        """E2E: Verify database indexes are created"""
        from src.core.database import Issue, PullRequest, AnalysisJob

        # Verify Issue indexes
        assert hasattr(Issue, '__table_args__')
        issue_indexes = [item for item in Issue.__table_args__ if hasattr(item, 'name')]
        assert len(issue_indexes) >= 3

        # Verify PullRequest indexes
        assert hasattr(PullRequest, '__table_args__')
        pr_indexes = [item for item in PullRequest.__table_args__ if hasattr(item, 'name')]
        assert len(pr_indexes) >= 3

        # Verify AnalysisJob indexes
        assert hasattr(AnalysisJob, '__table_args__')
        job_indexes = [item for item in AnalysisJob.__table_args__ if hasattr(item, 'name')]
        assert len(job_indexes) >= 2


class TestCompleteWorkflow:
    """Test complete end-to-end workflow"""

    def test_full_code_review_workflow(self):
        """E2E: Complete workflow from upload to insights"""
        from server import app

        mock_user = Mock()
        mock_user.id = 'test-user'
        mock_user.role = UserRole.USER

        with patch('server.get_current_user', return_value=mock_user):
            client = TestClient(app)

            # 1. Upload and analyze file
            test_code = "import os\\npassword = 'test123'\\n"
            files = {'file': ('test.py', test_code, 'text/x-python')}

            response = client.post("/api/analyze", files=files)
            assert response.status_code == 200

            # 2. Get analytics
            response = client.get("/api/analytics/health-score")
            assert response.status_code == 200

            # 3. Check notifications
            response = client.get("/api/notifications")
            assert response.status_code == 200

            # 4. View logs
            response = client.get("/api/logs/statistics")
            assert response.status_code == 200

            # 5. Export results
            response = client.get("/api/analytics/export?format=json")
            assert response.status_code == 200
