"""Tests for Refactoring API Endpoints"""
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

from src.core.database import (
    DatabaseManager,
    Repository,
    PullRequest,
    CodeFile,
    Issue,
    Refactoring,
    RefactoringStatus,
    RepositoryStatus,
    PRStatus,
    UserRole
)


@pytest.fixture
def mock_user():
    """Create a mock user"""
    user = Mock()
    user.id = 'test-user-id'
    user.username = 'testuser'
    user.email = 'test@test.com'
    user.role = UserRole.USER
    user.is_active = True
    return user


@pytest.fixture
def client(mock_user):
    """Create test client with mocked authentication"""
    with patch('server.get_current_user', return_value=mock_user):
        from server import app
        return TestClient(app)


@pytest.fixture
def db_manager():
    """Create test database manager"""
    return DatabaseManager('sqlite:///:memory:')


@pytest.fixture
def test_repo(db_manager, mock_user):
    """Create test repository"""
    with db_manager.get_session() as db:
        repo = Repository(
            user_id=mock_user.id,
            name='test-repo',
            github_url='https://github.com/user/repo',
            status=RepositoryStatus.READY
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return repo


@pytest.fixture
def test_pr(db_manager, test_repo):
    """Create test PR"""
    with db_manager.get_session() as db:
        pr = PullRequest(
            repository_id=test_repo.id,
            pr_number=1,
            title='Test PR',
            author='author',
            source_branch='feature',
            target_branch='main',
            status=PRStatus.OPEN
        )
        db.add(pr)
        db.commit()
        db.refresh(pr)
        return pr


@pytest.fixture
def test_code_file(db_manager, test_pr):
    """Create test code file"""
    with db_manager.get_session() as db:
        code_file = CodeFile(
            pull_request_id=test_pr.id,
            file_path='app.py',
            file_hash='abc123',
            language='python',
            lines_of_code=100
        )
        db.add(code_file)
        db.commit()
        db.refresh(code_file)
        return code_file


@pytest.fixture
def test_issue(db_manager, test_code_file):
    """Create test issue"""
    with db_manager.get_session() as db:
        issue = Issue(
            code_file_id=test_code_file.id,
            category='complexity',
            severity='warning',
            rule_id='complexity_high',
            title='High complexity',
            description='Function is too complex',
            line_number=10
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)
        return issue


@pytest.fixture
def test_refactoring(db_manager, test_issue, test_code_file):
    """Create test refactoring"""
    with db_manager.get_session() as db:
        refactoring = Refactoring(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            refactoring_type='simplify',
            original_code='def foo(): pass',
            refactored_code='def foo(): return None',
            diff='--- original\n+++ refactored',
            explanation='More explicit',
            confidence=0.8,
            status=RefactoringStatus.SUGGESTED
        )
        db.add(refactoring)
        db.commit()
        db.refresh(refactoring)
        return refactoring


def test_list_refactorings_empty(client):
    """Test listing refactorings when none exist"""
    response = client.get("/api/refactorings")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total"] == 0
    assert len(data["refactorings"]) == 0


def test_list_refactorings(client, test_refactoring):
    """Test listing refactorings"""
    response = client.get("/api/refactorings")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total"] >= 1


def test_list_refactorings_with_status_filter(client, test_refactoring):
    """Test listing refactorings with status filter"""
    response = client.get("/api/refactorings?status=suggested")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["filters"]["status"] == "suggested"


def test_list_refactorings_with_invalid_status(client):
    """Test listing refactorings with invalid status"""
    response = client.get("/api/refactorings?status=invalid")

    assert response.status_code == 400


def test_list_refactorings_pagination(client, test_refactoring):
    """Test refactoring pagination"""
    response = client.get("/api/refactorings?limit=10&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0


def test_get_refactoring(client, test_refactoring):
    """Test getting a specific refactoring"""
    response = client.get(f"/api/refactorings/{test_refactoring.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["refactoring"]["id"] == test_refactoring.id
    assert data["refactoring"]["refactoring_type"] == "simplify"


def test_get_refactoring_not_found(client):
    """Test getting non-existent refactoring"""
    response = client.get("/api/refactorings/nonexistent")

    assert response.status_code == 404


def test_create_refactoring(client, test_issue, test_code_file):
    """Test creating a refactoring"""
    refactoring_data = {
        "issue_id": test_issue.id,
        "code_file_id": test_code_file.id,
        "refactoring_type": "extract_method",
        "original_code": "def long_method(): ...",
        "refactored_code": "def method1(): ...\ndef method2(): ...",
        "explanation": "Extracted into smaller methods",
        "benefits": "Better readability",
        "confidence": 0.9
    }

    response = client.post("/api/refactorings", json=refactoring_data)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["refactoring"]["refactoring_type"] == "extract_method"
    assert data["refactoring"]["confidence"] == 0.9


def test_create_refactoring_missing_fields(client):
    """Test creating refactoring with missing fields"""
    response = client.post("/api/refactorings", json={"issue_id": "123"})

    assert response.status_code == 400


def test_accept_refactoring(client, test_refactoring):
    """Test accepting a refactoring"""
    response = client.post(f"/api/refactorings/{test_refactoring.id}/accept")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["refactoring"]["status"] == "accepted"


def test_reject_refactoring(client, test_refactoring):
    """Test rejecting a refactoring"""
    response = client.post(f"/api/refactorings/{test_refactoring.id}/reject")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["refactoring"]["status"] == "rejected"


def test_mark_refactoring_applied(client, test_refactoring):
    """Test marking refactoring as applied"""
    response = client.post(f"/api/refactorings/{test_refactoring.id}/apply")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["refactoring"]["status"] == "applied"


def test_get_refactoring_stats(client, test_refactoring):
    """Test getting refactoring statistics"""
    response = client.get("/api/refactorings/stats/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "total" in data
    assert "suggested" in data
    assert "accepted" in data
    assert "rejected" in data
    assert "applied" in data
    assert "acceptance_rate" in data
    assert "application_rate" in data


def test_refactoring_endpoints_require_auth():
    """Test that refactoring endpoints require authentication"""
    # Create client without mocked auth
    from server import app
    client_no_auth = TestClient(app)

    # List
    response = client_no_auth.get("/api/refactorings")
    assert response.status_code == 401

    # Get
    response = client_no_auth.get("/api/refactorings/123")
    assert response.status_code == 401

    # Create
    response = client_no_auth.post("/api/refactorings", json={})
    assert response.status_code == 401

    # Accept
    response = client_no_auth.post("/api/refactorings/123/accept")
    assert response.status_code == 401

    # Reject
    response = client_no_auth.post("/api/refactorings/123/reject")
    assert response.status_code == 401

    # Apply
    response = client_no_auth.post("/api/refactorings/123/apply")
    assert response.status_code == 401

    # Stats
    response = client_no_auth.get("/api/refactorings/stats/summary")
    assert response.status_code == 401
