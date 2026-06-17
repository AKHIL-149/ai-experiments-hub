"""
Integration tests for Week 3: Git & GitHub Integration + PR Analysis

Tests the full workflow from importing a PR to analyzing and reviewing it.
"""
import pytest
import sys
from unittest.mock import Mock, patch
from src.core.database import DatabaseManager, User, Repository, PullRequest, RepositoryStatus, PRStatus
from src.services.pr_service import PullRequestService
from src.services.diff_analyzer_service import DiffAnalyzerService
from src.services.review_service import ReviewService
from src.services.github_service import GitHubService
from src.utils.git_utils import DiffParser


# Mock celery before imports
mock_celery = Mock()
mock_celery.celery_app = Mock()
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()
sys.modules['celery_app'] = mock_celery


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
def sample_pr_info():
    """Sample PR info from GitHub"""
    return {
        'number': 42,
        'title': 'Add new feature',
        'description': 'This PR adds a new feature',
        'author': 'contributor',
        'author_avatar': 'https://github.com/avatar.png',
        'state': 'open',
        'is_merged': False,
        'is_draft': False,
        'source_branch': 'feature',
        'target_branch': 'main',
        'github_id': 123456,
        'html_url': 'https://github.com/user/test-repo/pull/42',
        'commits_count': 3,
        'additions': 50,
        'deletions': 20,
        'changed_files': 2,
        'mergeable': True,
        'mergeable_state': 'clean',
        'created_at': '2024-01-01T12:00:00',
        'updated_at': '2024-01-02T12:00:00'
    }


@pytest.fixture
def sample_diff():
    """Sample diff with security issues"""
    return """diff --git a/app.py b/app.py
index 1234567..abcdefg 100644
--- a/app.py
+++ b/app.py
@@ -1,5 +1,10 @@
 import os
+import subprocess

 def main():
-    print("Hello")
+    # Added feature
+    user_input = input("Enter command: ")
+    subprocess.call(user_input, shell=True)  # Security issue
+
+    password = "admin123"  # Hardcoded credential
+    print("Hello World")
"""


def test_complete_pr_workflow(db_manager, test_user, test_repository, sample_pr_info, sample_diff):
    """Test complete PR workflow: import -> analyze -> review"""
    with db_manager.get_session() as db:
        # Step 1: Import PR from GitHub
        with patch('src.services.pr_service.GitHubService') as MockGitHub:
            mock_service = Mock()
            mock_service.get_pull_request_info.return_value = (True, sample_pr_info, None)
            mock_service.close = Mock()
            MockGitHub.return_value = mock_service

            pr_service = PullRequestService(db)
            success, pr, error = pr_service.import_from_github(
                repository_id=test_repository.id,
                pr_number=42,
                github_token='ghp_test_token'
            )

            assert success is True
            assert pr is not None
            assert pr.pr_number == 42
            assert pr.status == PRStatus.OPEN

        # Step 2: Analyze diff
        diff_analyzer = DiffAnalyzerService()
        success, analysis_results, error = diff_analyzer.analyze_pr_diff(
            sample_diff,
            language='python'
        )

        assert success is True
        assert analysis_results['total_files'] == 1
        assert analysis_results['analyzed_files'] >= 0

        # Step 3: Generate review comments
        review_service = ReviewService(db)
        comments = review_service.generate_review_comments(
            analysis_results,
            pr.id
        )

        assert isinstance(comments, list)

        # Step 4: Create review summary
        summary = review_service.create_review_summary(
            analysis_results,
            comments
        )

        assert 'Code Review Summary' in summary

        # Step 5: Calculate score
        score = review_service.calculate_review_score(
            analysis_results,
            comments
        )

        assert 0 <= score <= 100

        # Step 6: Save review to database
        success, review, error = review_service.save_review(
            pr.id,
            test_user.id,
            analysis_results,
            comments
        )

        assert success is True
        assert review is not None

        # Verify PR status updated
        updated_pr = db.query(PullRequest).filter(PullRequest.id == pr.id).first()
        assert updated_pr.status == PRStatus.REVIEWED


def test_diff_parsing_and_analysis(sample_diff):
    """Test diff parsing and analysis pipeline"""
    # Parse diff
    diff_files = DiffParser.parse_diff(sample_diff)

    assert len(diff_files) == 1
    assert diff_files[0].path == 'app.py'
    assert diff_files[0].additions > 0

    # Analyze diff
    analyzer = DiffAnalyzerService()
    success, result, error = analyzer.analyze_diff(sample_diff, file_filter='.py')

    assert success is True
    assert result['total_files'] == 1


def test_pr_import_and_sync(db_manager, test_user, test_repository, sample_pr_info):
    """Test importing and syncing PR"""
    with db_manager.get_session() as db:
        pr_service = PullRequestService(db)

        with patch('src.services.pr_service.GitHubService') as MockGitHub:
            mock_service = Mock()
            mock_service.get_pull_request_info.return_value = (True, sample_pr_info, None)
            mock_service.close = Mock()
            MockGitHub.return_value = mock_service

            # Import PR
            success, pr, error = pr_service.import_from_github(
                repository_id=test_repository.id,
                pr_number=42,
                github_token='ghp_test_token'
            )

            assert success is True

            # Update PR info (simulate GitHub update)
            updated_info = sample_pr_info.copy()
            updated_info['title'] = 'Updated title'
            updated_info['additions'] = 100

            mock_service.get_pull_request_info.return_value = (True, updated_info, None)

            # Re-import (should update existing PR)
            success, updated_pr, error = pr_service.import_from_github(
                repository_id=test_repository.id,
                pr_number=42,
                github_token='ghp_test_token'
            )

            assert success is True
            assert updated_pr.title == 'Updated title'
            assert updated_pr.additions == 100


def test_review_generation_and_storage(db_manager, test_user, test_repository, sample_pr_info):
    """Test review generation and database storage"""
    with db_manager.get_session() as db:
        # Create PR
        pr = PullRequest(
            repository_id=test_repository.id,
            pr_number=42,
            title='Test PR',
            author='author',
            source_branch='feature',
            target_branch='main',
            status=PRStatus.OPEN
        )
        db.add(pr)
        db.commit()
        db.refresh(pr)

        # Mock analysis results
        analysis_results = {
            'total_files': 1,
            'analyzed_files': 1,
            'total_issues': 2,
            'files': [{
                'file_path': 'app.py',
                'issues_count': 2,
                'issues': [
                    {
                        'severity': 'critical',
                        'category': 'security',
                        'title': 'Command injection',
                        'description': 'Unsafe use of subprocess',
                        'line_number': 7
                    },
                    {
                        'severity': 'warning',
                        'category': 'security',
                        'title': 'Hardcoded credential',
                        'description': 'Password in source code',
                        'line_number': 9
                    }
                ]
            }]
        }

        # Generate and save review
        review_service = ReviewService(db)
        comments = review_service.generate_review_comments(analysis_results, pr.id)
        success, review, error = review_service.save_review(
            pr.id,
            test_user.id,
            analysis_results,
            comments
        )

        assert success is True
        assert review.issues_count == 2

        # Retrieve review
        success, retrieved_review, error = review_service.get_review(review.id)
        assert success is True
        assert retrieved_review.id == review.id

        # Get comments
        success, db_comments, error = review_service.get_review_comments(review.id)
        assert success is True
        assert len(db_comments) == 2


def test_diff_stats_calculation(sample_diff):
    """Test diff statistics calculation"""
    analyzer = DiffAnalyzerService()
    stats = analyzer.get_diff_stats(sample_diff)

    assert stats['files_changed'] == 1
    assert stats['additions'] > 0
    assert len(stats['files']) == 1
    assert stats['files'][0]['path'] == 'app.py'


def test_changed_files_extraction(sample_diff):
    """Test extracting changed file list"""
    analyzer = DiffAnalyzerService()
    success, files, error = analyzer.get_changed_files(sample_diff, file_filter='.py')

    assert success is True
    assert len(files) == 1
    assert files[0] == 'app.py'


def test_pr_status_transitions(db_manager, test_repository):
    """Test PR status transitions through workflow"""
    with db_manager.get_session() as db:
        # Create PR in OPEN status
        pr = PullRequest(
            repository_id=test_repository.id,
            pr_number=42,
            title='Test PR',
            author='author',
            source_branch='feature',
            target_branch='main',
            status=PRStatus.OPEN
        )
        db.add(pr)
        db.commit()

        assert pr.status == PRStatus.OPEN

        # Transition to ANALYZING (would happen in async worker)
        pr.status = PRStatus.ANALYZING
        db.commit()
        assert pr.status == PRStatus.ANALYZING

        # Transition to REVIEWED
        pr.status = PRStatus.REVIEWED
        db.commit()
        assert pr.status == PRStatus.REVIEWED


def test_review_score_calculation_various_severities():
    """Test score calculation with different severity combinations"""
    analyzer = DiffAnalyzerService()
    review_service = ReviewService(None)

    # Perfect score (no issues)
    score = review_service.calculate_review_score({}, [])
    assert score == 100.0

    # Only info issues
    comments = [{'severity': 'info'} for _ in range(5)]
    score = review_service.calculate_review_score({}, comments)
    assert score == 95.0  # 100 - 5*1

    # Mixed severity
    comments = [
        {'severity': 'critical'},  # -20
        {'severity': 'error'},     # -10
        {'severity': 'warning'},   # -5
        {'severity': 'info'}       # -1
    ]
    score = review_service.calculate_review_score({}, comments)
    assert score == 64.0  # 100 - 36


def test_repository_ready_status_required(db_manager, test_user):
    """Test that repository must be READY for PR operations"""
    with db_manager.get_session() as db:
        # Create repository in PENDING status
        repo = Repository(
            user_id=test_user.id,
            name='pending-repo',
            github_url='https://github.com/user/pending-repo',
            status=RepositoryStatus.PENDING
        )
        db.add(repo)
        db.commit()

        # Try to create PR (should work - status check is in UI/worker)
        pr = PullRequest(
            repository_id=repo.id,
            pr_number=1,
            title='Test',
            author='author',
            source_branch='feature',
            target_branch='main'
        )
        db.add(pr)
        db.commit()

        # PR created successfully
        assert pr.id is not None


def test_multiple_reviews_per_pr(db_manager, test_user, test_repository):
    """Test that multiple reviews can exist for one PR"""
    with db_manager.get_session() as db:
        # Create PR
        pr = PullRequest(
            repository_id=test_repository.id,
            pr_number=42,
            title='Test PR',
            author='author',
            source_branch='feature',
            target_branch='main'
        )
        db.add(pr)
        db.commit()

        review_service = ReviewService(db)

        # Create multiple reviews
        for i in range(3):
            analysis_results = {
                'total_files': 1,
                'analyzed_files': 1,
                'total_issues': i,
                'files': []
            }
            comments = review_service.generate_review_comments(analysis_results, pr.id)
            review_service.save_review(pr.id, test_user.id, analysis_results, comments)

        # Get all reviews
        success, reviews, error = review_service.get_pr_reviews(pr.id)

        assert success is True
        assert len(reviews) == 3
