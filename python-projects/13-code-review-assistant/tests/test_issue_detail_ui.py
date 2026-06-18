"""Tests for Issue Detail UI"""
import pytest
import sys
from unittest.mock import Mock
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
    UserRole,
    IssueCategory,
    IssueSeverity
)


@pytest.fixture(scope='function')
def test_db():
    """Create a test database"""
    db_manager = DatabaseManager('sqlite:///:memory:')
    yield db_manager


@pytest.fixture
def mock_user():
    """Create a mock user for authentication"""
    user = Mock()
    user.id = 'test-user-id'
    user.username = 'testuser'
    user.email = 'test@test.com'
    user.role = UserRole.USER
    user.is_active = True
    return user


@pytest.fixture
def test_data(test_db, mock_user):
    """Create test data with real database objects"""
    with test_db.get_session() as db:
        # Create repository
        repo = Repository(
            user_id=mock_user.id,
            name='test-repo',
            github_url='https://github.com/user/repo',
            status=RepositoryStatus.READY
        )
        db.add(repo)
        db.commit()
        repo_id = repo.id

        # Create PR
        pr = PullRequest(
            repository_id=repo_id,
            pr_number=1,
            title='Test PR',
            author='author',
            source_branch='feature',
            target_branch='main',
            status=PRStatus.OPEN
        )
        db.add(pr)
        db.commit()
        pr_id = pr.id

        # Create code file
        code_file = CodeFile(
            pull_request_id=pr_id,
            file_path='app.py',
            file_hash='abc123',
            language='python',
            lines_of_code=100
        )
        db.add(code_file)
        db.commit()
        code_file_id = code_file.id

        # Create issue
        issue = Issue(
            code_file_id=code_file_id,
            category=IssueCategory.SECURITY,
            severity=IssueSeverity.CRITICAL,
            rule_id='sql_injection',
            title='SQL Injection Vulnerability',
            description='String concatenation in SQL query',
            line_number=42,
            code_snippet='query = "SELECT * FROM users WHERE id = " + user_id',
            ai_explanation='This code is vulnerable to SQL injection attacks...',
            fix_suggestion='Use parameterized queries instead',
            fix_confidence=0.95,
            can_auto_apply=True
        )
        db.add(issue)
        db.commit()
        issue_id = issue.id

        # Create refactoring
        refactoring = Refactoring(
            issue_id=issue_id,
            code_file_id=code_file_id,
            refactoring_type='security_fix',
            original_code='query = "SELECT * FROM users WHERE id = " + user_id',
            refactored_code='query = "SELECT * FROM users WHERE id = %s"\ncursor.execute(query, (user_id,))',
            diff='--- original\n+++ refactored',
            explanation='Use parameterized queries to prevent SQL injection',
            confidence=0.95,
            status=RefactoringStatus.SUGGESTED
        )
        db.add(refactoring)
        db.commit()

        # Store IDs for access outside session
        return {
            'repo_id': repo_id,
            'pr_id': pr_id,
            'code_file_id': code_file_id,
            'issue_id': issue_id
        }


def test_issue_detail_requires_auth():
    """Test that issue detail page requires authentication"""
    from server import app
    client = TestClient(app)
    response = client.get("/issues/test-issue-id")

    # Should redirect to login when not authenticated
    assert response.status_code in [302, 307]


def test_issue_detail_not_found_returns_404(test_db, mock_user):
    """Test 404 for non-existent issue"""
    # Temporarily replace db_manager
    import server
    original_db = server.db_manager
    server.db_manager = test_db

    try:
        from unittest.mock import patch
        with patch('server.get_current_user_optional', return_value=mock_user):
            client = TestClient(server.app)
            response = client.get("/issues/nonexistent-id")
            assert response.status_code == 404
    finally:
        server.db_manager = original_db


def test_issue_detail_page_renders_successfully(test_db, test_data, mock_user):
    """Test that issue detail page renders successfully"""
    # Temporarily replace db_manager
    import server
    original_db = server.db_manager
    server.db_manager = test_db

    try:
        from unittest.mock import patch
        with patch('server.get_current_user_optional', return_value=mock_user):
            client = TestClient(server.app)
            response = client.get(f"/issues/{test_data['issue_id']}")

            assert response.status_code == 200
            assert b"Issue Detail" in response.content
    finally:
        server.db_manager = original_db


def test_issue_detail_shows_code_snippet(test_db, test_data, mock_user):
    """Test that code snippet is displayed"""
    import server
    original_db = server.db_manager
    server.db_manager = test_db

    try:
        from unittest.mock import patch
        with patch('server.get_current_user_optional', return_value=mock_user):
            client = TestClient(server.app)
            response = client.get(f"/issues/{test_data['issue_id']}")

            assert response.status_code == 200
            assert b'query = "SELECT * FROM users WHERE id = " + user_id' in response.content
    finally:
        server.db_manager = original_db


def test_issue_detail_shows_ai_explanation(test_db, test_data, mock_user):
    """Test that AI explanation is displayed"""
    import server
    original_db = server.db_manager
    server.db_manager = test_db

    try:
        from unittest.mock import patch
        with patch('server.get_current_user_optional', return_value=mock_user):
            client = TestClient(server.app)
            response = client.get(f"/issues/{test_data['issue_id']}")

            assert response.status_code == 200
            assert b"AI Explanation" in response.content
            assert b"This code is vulnerable to SQL injection attacks" in response.content
    finally:
        server.db_manager = original_db


def test_issue_detail_shows_refactoring_suggestion(test_db, test_data, mock_user):
    """Test that refactoring suggestion is displayed"""
    import server
    original_db = server.db_manager
    server.db_manager = test_db

    try:
        from unittest.mock import patch
        with patch('server.get_current_user_optional', return_value=mock_user):
            client = TestClient(server.app)
            response = client.get(f"/issues/{test_data['issue_id']}")

            assert response.status_code == 200
            assert b"Refactoring Suggestion" in response.content
            assert b"Use parameterized queries to prevent SQL injection" in response.content
    finally:
        server.db_manager = original_db
