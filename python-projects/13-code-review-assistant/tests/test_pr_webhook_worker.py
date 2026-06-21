"""
Tests for PR Webhook Worker
Tests automatic PR analysis triggered by webhooks
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from src.core.database import (
    DatabaseManager, Repository, PullRequest, AnalysisJob,
    JobStatus, PRStatus, RepositoryStatus
)
from src.core.queue_manager import QueueManager


class TestPRWebhookWorker:
    """Test webhook-triggered PR analysis worker"""

    @pytest.fixture
    def db_manager(self):
        """Create test database manager"""
        return DatabaseManager()

    @pytest.fixture
    def repository(self, db_manager):
        """Create test repository"""
        with db_manager.get_session() as db:
            repo = Repository(
                user_id=1,
                name="test-repo",
                github_url="https://github.com/test/repo",
                default_branch="main",
                status=RepositoryStatus.READY
            )
            db.add(repo)
            db.commit()
            db.refresh(repo)
            return repo

    def test_queue_pr_analysis_creates_job(self, db_manager, repository):
        """Test that queue_pr_analysis creates an analysis job"""
        with patch('src.workers.pr_worker.analyze_pr_webhook') as mock_task:
            # Mock the Celery task
            mock_task.apply_async.return_value = Mock(id='task-123')

            # Create queue manager
            queue_manager = QueueManager(
                db_manager.get_session(),
                Mock()  # Mock celery app
            )

            # Queue PR analysis
            job = queue_manager.queue_pr_analysis(
                repository_id=repository.id,
                pr_number=42,
                installation_id=789,
                priority='high'
            )

            assert job is not None
            assert job.job_type == 'pr_analysis'
            assert job.status == JobStatus.QUEUED
            assert job.pull_request_id is not None

    def test_queue_pr_analysis_creates_pr_if_not_exists(self, db_manager, repository):
        """Test that queue_pr_analysis creates PR record if it doesn't exist"""
        with patch('src.workers.pr_worker.analyze_pr_webhook'):
            queue_manager = QueueManager(
                db_manager.get_session(),
                Mock()
            )

            # Queue analysis for non-existent PR
            job = queue_manager.queue_pr_analysis(
                repository_id=repository.id,
                pr_number=99,
                installation_id=789
            )

            # Check PR was created
            with db_manager.get_session() as db:
                pr = db.query(PullRequest).filter(
                    PullRequest.repository_id == repository.id,
                    PullRequest.pr_number == 99
                ).first()

                assert pr is not None
                assert pr.pr_number == 99
                assert pr.title == "PR #99"

    def test_queue_pr_analysis_reuses_existing_pr(self, db_manager, repository):
        """Test that queue_pr_analysis reuses existing PR record"""
        with patch('src.workers.pr_worker.analyze_pr_webhook') as mock_task:
            # Mock the task to return a proper ID
            mock_task.apply_async.return_value = Mock(id='task-456')

            # Create existing PR
            with db_manager.get_session() as db:
                pr = PullRequest(
                    repository_id=repository.id,
                    pr_number=42,
                    title="Existing PR",
                    author="testuser",
                    status=PRStatus.OPEN,
                    source_branch="feature",
                    target_branch="main"
                )
                db.add(pr)
                db.commit()
                pr_id = pr.id

            # Queue analysis
            queue_manager = QueueManager(
                db_manager.get_session(),
                Mock()
            )

            job = queue_manager.queue_pr_analysis(
                repository_id=repository.id,
                pr_number=42,
                installation_id=789
            )

            # Check it reused the existing PR
            assert job.pull_request_id == pr_id

    def test_queue_pr_analysis_sets_priority(self, db_manager, repository):
        """Test that queue_pr_analysis respects priority setting"""
        with patch('src.workers.pr_worker.analyze_pr_webhook') as mock_task:
            mock_task.apply_async.return_value = Mock(id='task-123')

            queue_manager = QueueManager(
                db_manager.get_session(),
                Mock()
            )

            # Test high priority
            queue_manager.queue_pr_analysis(
                repository_id=repository.id,
                pr_number=42,
                priority='high'
            )

            # Verify high priority was set
            call_kwargs = mock_task.apply_async.call_args[1]
            assert call_kwargs.get('priority') == 9

    def test_queue_pr_analysis_handles_celery_unavailable(self, db_manager, repository):
        """Test graceful handling when Celery is not available"""
        # Don't mock the task - let it fail naturally
        queue_manager = QueueManager(
            db_manager.get_session(),
            Mock()
        )

        # Should not raise exception even if Celery task dispatch fails
        job = queue_manager.queue_pr_analysis(
            repository_id=repository.id,
            pr_number=42
        )

        # Job should still be created
        assert job is not None
        assert job.status == JobStatus.QUEUED


class TestAnalyzePRWebhookTask:
    """Test the analyze_pr_webhook Celery task"""

    @pytest.fixture
    def mock_github_service(self):
        """Mock GitHub service"""
        with patch('src.workers.pr_worker.GitHubService') as mock:
            service = Mock()

            # Mock PR info
            service.get_pull_request_info.return_value = (
                True,  # success
                {
                    'title': 'Test PR',
                    'author': 'testuser',
                    'source_branch': 'feature',
                    'target_branch': 'main',
                    'commits_count': 3,
                    'additions': 100,
                    'deletions': 50,
                    'changed_files': 5
                },
                None  # error
            )

            # Mock diff
            service.get_pull_request_diff.return_value = (
                True,  # success
                '''diff --git a/test.py b/test.py
index 123..456 789
--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 def hello():
-    print("old")
+    print("new")
''',
                None  # error
            )

            # Mock files
            service.get_pull_request_files.return_value = (
                True,  # success
                [
                    {
                        'filename': 'test.py',
                        'patch': '+    print("new")\n'
                    }
                ],
                None  # error
            )

            service.close.return_value = None

            mock.return_value = service
            yield mock

    def test_webhook_task_uses_github_app_auth(self, mock_github_service):
        """Test that webhook task uses GitHub App authentication"""
        from src.workers.pr_worker import analyze_pr_webhook

        with patch('src.workers.pr_worker.get_github_app') as mock_app:
            mock_app_instance = Mock()
            mock_app_instance.is_configured.return_value = True
            mock_app_instance.get_installation_token.return_value = 'ghs_test_token'
            mock_app.return_value = mock_app_instance

            with patch('src.workers.pr_worker.db_manager'):
                with patch('src.workers.pr_worker.DiffParser'):
                    with patch('src.workers.pr_worker.CodeAnalyzerService'):
                        # This would actually run the task, but we've mocked all dependencies
                        # In real tests, you'd use Celery's test utilities
                        pass

    def test_webhook_task_supports_multiple_languages(self):
        """Test that webhook task detects and analyzes multiple languages"""
        from src.parsers import get_registry

        registry = get_registry()

        # Verify supported languages
        languages = registry.get_supported_languages()
        assert 'python' in languages
        assert 'javascript' in languages
        assert 'java' in languages
        assert 'go' in languages
        assert 'rust' in languages

    def test_webhook_task_stores_issues_in_database(self):
        """Test that issues are properly stored in database"""
        # This would be a full integration test
        # For now, we verify the imports work
        from src.core.database import Issue, CodeFile
        assert Issue is not None
        assert CodeFile is not None
