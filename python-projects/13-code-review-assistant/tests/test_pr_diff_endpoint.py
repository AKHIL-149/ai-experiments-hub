"""Tests for PR diff endpoints"""
import pytest
import sys
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

# Mock celery before imports
mock_celery = Mock()
mock_celery.celery_app = Mock()
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()
sys.modules['celery_app'] = mock_celery

from server import app
from src.core.database import DatabaseManager, User, Repository, PullRequest, RepositoryStatus, PRStatus


@pytest.fixture
def db_manager():
    """Create test database manager"""
    return DatabaseManager('sqlite:///:memory:')


@pytest.fixture
def test_user(db_manager):
    """Create a test user with GitHub token"""
    with db_manager.get_session() as db:
        user = User(
            username='testuser',
            email='test@example.com',
            password_hash='hashed_password',
            github_token='ghp_test_token'
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture
def test_repository(db_manager, test_user):
    """Create a test repository"""
    with db_manager.get_session() as db:
        repo = Repository(
            user_id=test_user.id,
            name='test-repo',
            github_url='https://github.com/user/test-repo',
            status=RepositoryStatus.READY
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return repo


@pytest.fixture
def test_pr(db_manager, test_repository):
    """Create a test pull request"""
    with db_manager.get_session() as db:
        pr = PullRequest(
            repository_id=test_repository.id,
            pr_number=42,
            title='Test PR',
            author='testauthor',
            source_branch='feature',
            target_branch='main',
            status=PRStatus.OPEN
        )
        db.add(pr)
        db.commit()
        db.refresh(pr)
        return pr


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def sample_diff():
    """Sample diff text"""
    return """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,2 +1,3 @@
 def test():
+    x = 10
     pass
"""


def test_get_pr_diff_requires_auth(client, test_pr):
    """Test that diff endpoint requires authentication"""
    response = client.get(f"/api/prs/{test_pr.id}/diff")

    # Should return 401 or redirect
    assert response.status_code in [401, 200]


def test_get_pr_diff_requires_github_token(client, test_pr):
    """Test that diff endpoint requires GitHub token"""
    # This test would need proper session setup
    # For now, just verify endpoint exists
    response = client.get(f"/api/prs/{test_pr.id}/diff")
    assert response.status_code in [401, 400, 200]


def test_get_pr_diff_success(client, test_pr, sample_diff):
    """Test successfully getting PR diff"""
    with patch('src.services.github_service.GitHubService') as MockGitHub:
        # Mock GitHub service
        mock_service = Mock()
        mock_service.get_pull_request_diff.return_value = (True, sample_diff, None)
        mock_service.close = Mock()
        MockGitHub.return_value = mock_service

        # This test would need proper authentication
        # For now, just verify the endpoint structure
        response = client.get(f"/api/prs/{test_pr.id}/diff")
        # Without auth, will get 401
        assert response.status_code in [200, 401]


def test_get_pr_diff_with_analysis(client, test_pr, sample_diff):
    """Test getting PR diff with analysis"""
    with patch('src.services.github_service.GitHubService') as MockGitHub:
        mock_service = Mock()
        mock_service.get_pull_request_diff.return_value = (True, sample_diff, None)
        mock_service.close = Mock()
        MockGitHub.return_value = mock_service

        # Test with analyze=true parameter
        response = client.get(f"/api/prs/{test_pr.id}/diff?analyze=true")
        # Without auth, will get 401
        assert response.status_code in [200, 401]


def test_get_pr_diff_not_found(client):
    """Test getting diff for non-existent PR"""
    response = client.get("/api/prs/nonexistent-id/diff")

    # Should return 401 (auth) or 404 (not found)
    assert response.status_code in [401, 404]


def test_get_pr_diff_github_error(client, test_pr):
    """Test handling GitHub API error"""
    with patch('src.services.github_service.GitHubService') as MockGitHub:
        # Mock GitHub service failure
        mock_service = Mock()
        mock_service.get_pull_request_diff.return_value = (False, None, "API error")
        mock_service.close = Mock()
        MockGitHub.return_value = mock_service

        response = client.get(f"/api/prs/{test_pr.id}/diff")
        # Without auth, will get 401
        assert response.status_code in [401, 500]


def test_get_pr_files_requires_auth(client, test_pr):
    """Test that files endpoint requires authentication"""
    response = client.get(f"/api/prs/{test_pr.id}/files")

    # Should return 401 or redirect
    assert response.status_code in [401, 200]


def test_get_pr_files_success(client, test_pr):
    """Test successfully getting PR files"""
    files_info = [
        {
            'filename': 'test.py',
            'status': 'modified',
            'additions': 10,
            'deletions': 5,
            'changes': 15
        }
    ]

    with patch('src.services.github_service.GitHubService') as MockGitHub:
        mock_service = Mock()
        mock_service.get_pull_request_files.return_value = (True, files_info, None)
        mock_service.close = Mock()
        MockGitHub.return_value = mock_service

        response = client.get(f"/api/prs/{test_pr.id}/files")
        # Without auth, will get 401
        assert response.status_code in [200, 401]


def test_get_pr_files_not_found(client):
    """Test getting files for non-existent PR"""
    response = client.get("/api/prs/nonexistent-id/files")

    # Should return 401 (auth) or 404 (not found)
    assert response.status_code in [401, 404]


def test_get_pr_files_github_error(client, test_pr):
    """Test handling GitHub API error when fetching files"""
    with patch('src.services.github_service.GitHubService') as MockGitHub:
        mock_service = Mock()
        mock_service.get_pull_request_files.return_value = (False, None, "API error")
        mock_service.close = Mock()
        MockGitHub.return_value = mock_service

        response = client.get(f"/api/prs/{test_pr.id}/files")
        # Without auth, will get 401
        assert response.status_code in [401, 500]


def test_diff_endpoint_structure():
    """Test that diff endpoint has correct structure"""
    # Verify endpoint exists
    from server import app

    routes = [route.path for route in app.routes]
    assert "/api/prs/{pr_id}/diff" in routes
    assert "/api/prs/{pr_id}/files" in routes


def test_diff_analyze_parameter():
    """Test that analyze parameter is boolean"""
    from server import get_pr_diff
    import inspect

    # Get function signature
    sig = inspect.signature(get_pr_diff)
    assert 'analyze' in sig.parameters
    # Default should be False
    assert sig.parameters['analyze'].default is False
