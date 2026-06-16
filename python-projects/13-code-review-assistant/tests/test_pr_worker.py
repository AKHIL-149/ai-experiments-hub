"""Tests for pull request worker tasks"""
import pytest
import sys
from unittest.mock import Mock, patch
from datetime import datetime
from src.core.database import DatabaseManager, User, Repository, PullRequest, PRStatus, RepositoryStatus

# Mock celery_app module before importing worker
mock_celery = Mock()
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery_app'] = mock_celery

from src.workers.pr_worker import (
    analyze_pr_task,
    sync_pr_task
)


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
            status=RepositoryStatus.READY,
            clone_path='/tmp/test-repo'
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
            author='contributor',
            source_branch='feature',
            target_branch='main',
            status=PRStatus.OPEN
        )
        db.add(pr)
        db.commit()
        db.refresh(pr)
        return pr


@pytest.fixture
def mock_github_diff():
    """Mock GitHub diff"""
    return """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
+import os
 def hello():
     print("Hello")

"""


@pytest.fixture
def mock_github_files():
    """Mock GitHub files info"""
    return [
        {
            'filename': 'test.py',
            'status': 'modified',
            'additions': 1,
            'deletions': 0,
            'patch': """@@ -1,3 +1,4 @@
+import os
 def hello():
     print("Hello")
"""
        }
    ]


def test_analyze_pr_task_pr_not_found(db_manager):
    """Test analyzing non-existent PR"""
    with patch('src.workers.pr_worker.db_manager', db_manager):
        # Create mock task
        mock_task = Mock()
        mock_task.request.id = 'job123'
        mock_task.update_state = Mock()

        result = analyze_pr_task(mock_task, 'nonexistent-pr-id', 'token')

        assert result['success'] is False
        assert 'not found' in result['error'].lower()


def test_analyze_pr_task_success(db_manager, test_pr, mock_github_diff, mock_github_files):
    """Test successful PR analysis"""
    with patch('src.workers.pr_worker.db_manager', db_manager):
        with patch('src.workers.pr_worker.GitHubService') as MockGitHub:
            # Mock GitHub service
            mock_service = Mock()
            mock_service.get_pull_request_diff.return_value = (True, mock_github_diff, None)
            mock_service.get_pull_request_files.return_value = (True, mock_github_files, None)
            MockGitHub.return_value = mock_service

            # Mock analyzer
            with patch('src.workers.pr_worker.CodeAnalyzerService') as MockAnalyzer:
                mock_analyzer = Mock()
                mock_analyzer.analyze_code.return_value = {
                    'success': True,
                    'report': {
                        'total_issues': 5,
                        'issues': []
                    }
                }
                MockAnalyzer.return_value = mock_analyzer

                # Create mock task
                mock_task = Mock()
                mock_task.request.id = 'job123'
                mock_task.update_state = Mock()

                result = analyze_pr_task(mock_task, test_pr.id, 'test_token')

                assert result['success'] is True
                assert result['files_analyzed'] >= 0


def test_analyze_pr_task_no_python_files(db_manager, test_pr):
    """Test PR analysis with no Python files"""
    # Mock diff with no Python files
    diff_no_python = """diff --git a/README.md b/README.md
index 1234567..abcdefg 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Test
+Updated
"""

    with patch('src.workers.pr_worker.db_manager', db_manager):
        with patch('src.workers.pr_worker.GitHubService') as MockGitHub:
            mock_service = Mock()
            mock_service.get_pull_request_diff.return_value = (True, diff_no_python, None)
            MockGitHub.return_value = mock_service

            mock_task = Mock()
            mock_task.request.id = 'job123'
            mock_task.update_state = Mock()

            result = analyze_pr_task(mock_task, test_pr.id, 'test_token')

            assert result['success'] is True
            assert result['files_analyzed'] == 0


def test_analyze_pr_task_github_error(db_manager, test_pr):
    """Test PR analysis when GitHub API fails"""
    with patch('src.workers.pr_worker.db_manager', db_manager):
        with patch('src.workers.pr_worker.GitHubService') as MockGitHub:
            mock_service = Mock()
            mock_service.get_pull_request_diff.return_value = (False, None, "API error")
            MockGitHub.return_value = mock_service

            mock_task = Mock()
            mock_task.request.id = 'job123'
            mock_task.update_state = Mock()

            result = analyze_pr_task(mock_task, test_pr.id, 'test_token')

            assert result['success'] is False
            assert 'API error' in result['error']


def test_analyze_pr_task_updates_status(db_manager, test_pr, mock_github_diff, mock_github_files):
    """Test that PR status is updated during analysis"""
    with patch('src.workers.pr_worker.db_manager', db_manager):
        with patch('src.workers.pr_worker.GitHubService') as MockGitHub:
            mock_service = Mock()
            mock_service.get_pull_request_diff.return_value = (True, mock_github_diff, None)
            mock_service.get_pull_request_files.return_value = (True, mock_github_files, None)
            MockGitHub.return_value = mock_service

            with patch('src.workers.pr_worker.CodeAnalyzerService') as MockAnalyzer:
                mock_analyzer = Mock()
                mock_analyzer.analyze_code.return_value = {
                    'success': True,
                    'report': {
                        'total_issues': 0,
                        'issues': []
                    }
                }
                MockAnalyzer.return_value = mock_analyzer

                mock_task = Mock()
                mock_task.request.id = 'job123'
                mock_task.update_state = Mock()

                analyze_pr_task(mock_task, test_pr.id, 'test_token')

                # Check that PR status was updated
                with db_manager.get_session() as db:
                    pr = db.query(PullRequest).filter(PullRequest.id == test_pr.id).first()
                    assert pr.status == PRStatus.REVIEWED
                    assert pr.reviewed_at is not None


def test_sync_pr_task_success(db_manager, test_pr):
    """Test successful PR sync"""
    mock_pr_info = {
        'title': 'Updated Title',
        'description': 'Updated description',
        'is_draft': False,
        'is_merged': False,
        'commits_count': 10,
        'additions': 200,
        'deletions': 100,
        'changed_files': 5,
        'mergeable': True,
        'mergeable_state': 'clean',
        'updated_at': '2024-01-02T12:00:00',
        'state': 'open'
    }

    with patch('src.workers.pr_worker.db_manager', db_manager):
        with patch('src.workers.pr_worker.GitHubService') as MockGitHub:
            mock_service = Mock()
            mock_service.get_pull_request_info.return_value = (True, mock_pr_info, None)
            MockGitHub.return_value = mock_service

            mock_task = Mock()
            mock_task.update_state = Mock()

            result = sync_pr_task(mock_task, test_pr.id, 'test_token')

            assert result['success'] is True
            assert result['pr_id'] == test_pr.id

            # Verify PR was updated
            with db_manager.get_session() as db:
                pr = db.query(PullRequest).filter(PullRequest.id == test_pr.id).first()
                assert pr.title == 'Updated Title'
                assert pr.commits_count == 10


def test_sync_pr_task_pr_not_found(db_manager):
    """Test syncing non-existent PR"""
    with patch('src.workers.pr_worker.db_manager', db_manager):
        mock_task = Mock()
        mock_task.update_state = Mock()

        result = sync_pr_task(mock_task, 'nonexistent-pr-id', 'token')

        assert result['success'] is False
        assert 'not found' in result['error'].lower()


def test_sync_pr_task_github_error(db_manager, test_pr):
    """Test PR sync when GitHub API fails"""
    with patch('src.workers.pr_worker.db_manager', db_manager):
        with patch('src.workers.pr_worker.GitHubService') as MockGitHub:
            mock_service = Mock()
            mock_service.get_pull_request_info.return_value = (False, None, "API error")
            MockGitHub.return_value = mock_service

            mock_task = Mock()
            mock_task.update_state = Mock()

            result = sync_pr_task(mock_task, test_pr.id, 'test_token')

            assert result['success'] is False
            assert 'API error' in result['error']


def test_sync_pr_task_updates_merged_status(db_manager, test_pr):
    """Test that sync updates PR status to MERGED"""
    mock_pr_info = {
        'title': 'Test PR',
        'description': 'Description',
        'is_draft': False,
        'is_merged': True,
        'commits_count': 5,
        'additions': 100,
        'deletions': 50,
        'changed_files': 3,
        'mergeable': None,
        'mergeable_state': 'merged',
        'updated_at': '2024-01-02T12:00:00',
        'state': 'closed'
    }

    with patch('src.workers.pr_worker.db_manager', db_manager):
        with patch('src.workers.pr_worker.GitHubService') as MockGitHub:
            mock_service = Mock()
            mock_service.get_pull_request_info.return_value = (True, mock_pr_info, None)
            MockGitHub.return_value = mock_service

            mock_task = Mock()
            mock_task.update_state = Mock()

            sync_pr_task(mock_task, test_pr.id, 'test_token')

            # Verify status updated to MERGED
            with db_manager.get_session() as db:
                pr = db.query(PullRequest).filter(PullRequest.id == test_pr.id).first()
                assert pr.status == PRStatus.MERGED
                assert pr.is_merged is True
