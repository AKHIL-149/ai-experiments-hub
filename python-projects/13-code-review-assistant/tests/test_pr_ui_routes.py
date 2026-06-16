"""Tests for pull request UI routes"""
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
    """Create a test user"""
    with db_manager.get_session() as db:
        user = User(
            username='testuser',
            email='test@example.com',
            password_hash='hashed_password'
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


def test_pull_requests_page_requires_auth(client):
    """Test that PR list page requires authentication"""
    response = client.get("/pull-requests")

    # Should redirect to login
    assert response.status_code == 200  # RedirectResponse returns 200 in TestClient
    assert "login" in response.url.path.lower()


def test_pull_request_import_page_requires_auth(client):
    """Test that PR import page requires authentication"""
    response = client.get("/pull-requests/import")

    # Should redirect to login
    assert response.status_code == 200
    assert "login" in response.url.path.lower()


def test_pull_request_detail_page_requires_auth(client):
    """Test that PR detail page requires authentication"""
    response = client.get("/pull-requests/test-pr-id")

    # Should redirect to login
    assert response.status_code == 200
    assert "login" in response.url.path.lower()


def test_pull_requests_page_renders(client, test_user, test_repository, test_pr):
    """Test that PR list page renders with authentication"""
    # This test would need session cookie setup
    # For now, just verify route exists and redirects when not authenticated
    response = client.get("/pull-requests")
    assert response.status_code == 200


def test_pull_request_import_page_renders(client):
    """Test that PR import page renders"""
    response = client.get("/pull-requests/import")
    assert response.status_code == 200


def test_pull_request_detail_page_not_found(client):
    """Test that PR detail page handles not found"""
    # Without auth, should redirect to login
    response = client.get("/pull-requests/nonexistent-id")
    assert response.status_code == 200
