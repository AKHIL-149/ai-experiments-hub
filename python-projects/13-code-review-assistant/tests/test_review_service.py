"""Tests for review service"""
import pytest
from src.core.database import DatabaseManager, User, Repository, PullRequest, Review, ReviewComment, RepositoryStatus, PRStatus
from src.services.review_service import ReviewService


@pytest.fixture
def db_manager():
    """Create test database manager"""
    return DatabaseManager('sqlite:///:memory:')


@pytest.fixture
def test_user(db_manager):
    """Create a test user"""
    with db_manager.get_session() as db:
        user = User(
            username='reviewer',
            email='reviewer@test.com',
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
def sample_analysis_results():
    """Sample analysis results"""
    return {
        'total_files': 2,
        'analyzed_files': 2,
        'total_issues': 3,
        'files': [
            {
                'file_path': 'app.py',
                'issues_count': 2,
                'issues': [
                    {
                        'severity': 'critical',
                        'category': 'security',
                        'title': 'SQL Injection Risk',
                        'description': 'Avoid string concatenation in SQL queries',
                        'line_number': 10
                    },
                    {
                        'severity': 'warning',
                        'category': 'style',
                        'title': 'Long method',
                        'description': 'Method exceeds 50 lines',
                        'line_number': 20
                    }
                ]
            },
            {
                'file_path': 'utils.py',
                'issues_count': 1,
                'issues': [
                    {
                        'severity': 'info',
                        'category': 'best-practice',
                        'title': 'Use type hints',
                        'description': 'Add type hints for better code clarity',
                        'line_number': 5
                    }
                ]
            }
        ]
    }


def test_generate_review_comments(db_manager, test_pr, sample_analysis_results):
    """Test generating review comments from analysis"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        comments = review_service.generate_review_comments(
            sample_analysis_results,
            test_pr.id
        )

        assert len(comments) == 3
        assert all('file_path' in c for c in comments)
        assert all('comment_text' in c for c in comments)
        assert all('severity' in c for c in comments)


def test_create_comment_from_issue(db_manager, test_pr):
    """Test creating comment from issue"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        issue = {
            'severity': 'error',
            'category': 'security',
            'title': 'Hardcoded password',
            'description': 'Password should not be hardcoded',
            'line_number': 15
        }

        comment = review_service._create_comment_from_issue(
            issue,
            'config.py',
            test_pr.id
        )

        assert comment['file_path'] == 'config.py'
        assert comment['line_number'] == 15
        assert comment['severity'] == 'error'
        assert 'Hardcoded password' in comment['comment_text']


def test_format_comment_text(db_manager):
    """Test formatting issue as comment text"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        issue = {
            'severity': 'warning',
            'category': 'complexity',
            'title': 'High cyclomatic complexity',
            'description': 'Function has complexity of 15',
            'suggestion': 'Break down into smaller functions'
        }

        text = review_service._format_comment_text(issue)

        assert 'WARNING' in text
        assert 'complexity' in text
        assert 'High cyclomatic complexity' in text
        assert 'Function has complexity of 15' in text
        assert 'Break down into smaller functions' in text


def test_create_review_summary(db_manager, sample_analysis_results):
    """Test creating review summary"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        comments = review_service.generate_review_comments(
            sample_analysis_results,
            'test-pr-id'
        )

        summary = review_service.create_review_summary(
            sample_analysis_results,
            comments
        )

        assert 'Code Review Summary' in summary
        assert 'Critical: 1' in summary
        assert 'Warnings: 1' in summary
        assert 'Info: 1' in summary


def test_calculate_review_score_perfect(db_manager):
    """Test calculating perfect score with no issues"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        score = review_service.calculate_review_score(
            {'total_issues': 0},
            []
        )

        assert score == 100.0


def test_calculate_review_score_with_issues(db_manager):
    """Test calculating score with various issues"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        comments = [
            {'severity': 'critical', 'comment_text': 'Critical issue'},
            {'severity': 'warning', 'comment_text': 'Warning'},
            {'severity': 'info', 'comment_text': 'Info'}
        ]

        score = review_service.calculate_review_score(
            {'total_issues': 3},
            comments
        )

        # critical (-20) + warning (-5) + info (-1) = -26
        # 100 - 26 = 74
        assert score == 74.0


def test_calculate_review_score_minimum(db_manager):
    """Test that score doesn't go below 0"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        # Many critical issues
        comments = [{'severity': 'critical', 'comment_text': 'Issue'} for _ in range(10)]

        score = review_service.calculate_review_score(
            {'total_issues': 10},
            comments
        )

        assert score == 0.0


def test_save_review(db_manager, test_pr, test_user, sample_analysis_results):
    """Test saving review to database"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        comments = review_service.generate_review_comments(
            sample_analysis_results,
            test_pr.id
        )

        success, review, error = review_service.save_review(
            test_pr.id,
            test_user.id,
            sample_analysis_results,
            comments
        )

        assert success is True
        assert error is None
        assert review is not None
        assert review.overall_score > 0
        assert review.issues_count == 3

        # Verify PR status updated (re-query to get fresh state)
        updated_pr = db.query(PullRequest).filter(PullRequest.id == test_pr.id).first()
        assert updated_pr.status == PRStatus.REVIEWED


def test_get_review(db_manager, test_pr, test_user, sample_analysis_results):
    """Test getting review by ID"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        # Create review
        comments = review_service.generate_review_comments(
            sample_analysis_results,
            test_pr.id
        )
        success, review, error = review_service.save_review(
            test_pr.id,
            test_user.id,
            sample_analysis_results,
            comments
        )

        # Get review
        success, retrieved_review, error = review_service.get_review(review.id)

        assert success is True
        assert retrieved_review.id == review.id


def test_get_review_not_found(db_manager):
    """Test getting non-existent review"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        success, review, error = review_service.get_review('nonexistent-id')

        assert success is False
        assert review is None
        assert 'not found' in error.lower()


def test_get_pr_reviews(db_manager, test_pr, test_user, sample_analysis_results):
    """Test getting all reviews for a PR"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        # Create multiple reviews
        for i in range(3):
            comments = review_service.generate_review_comments(
                sample_analysis_results,
                test_pr.id
            )
            review_service.save_review(
                test_pr.id,
                test_user.id,
                sample_analysis_results,
                comments
            )

        # Get all reviews
        success, reviews, error = review_service.get_pr_reviews(test_pr.id)

        assert success is True
        assert len(reviews) == 3


def test_get_review_comments(db_manager, test_pr, test_user, sample_analysis_results):
    """Test getting comments for a review"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        # Create review
        comments = review_service.generate_review_comments(
            sample_analysis_results,
            test_pr.id
        )
        success, review, error = review_service.save_review(
            test_pr.id,
            test_user.id,
            sample_analysis_results,
            comments
        )

        # Get comments
        success, retrieved_comments, error = review_service.get_review_comments(review.id)

        assert success is True
        assert len(retrieved_comments) == 3


def test_format_comments_for_github(db_manager):
    """Test formatting comments for GitHub API"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        comments = [
            {
                'file_path': 'app.py',
                'line_number': 10,
                'comment_text': 'Issue found',
                'severity': 'error'
            },
            {
                'file_path': 'utils.py',
                'line_number': 20,
                'comment_text': 'Another issue',
                'severity': 'warning'
            }
        ]

        github_comments = review_service.format_comments_for_github(
            comments,
            commit_id='abc123'
        )

        assert len(github_comments) == 2
        assert all('path' in c for c in github_comments)
        assert all('body' in c for c in github_comments)
        assert all('commit_id' in c for c in github_comments)
        assert all(c['commit_id'] == 'abc123' for c in github_comments)


def test_review_approval_threshold(db_manager, test_pr, test_user):
    """Test that reviews are auto-approved based on score"""
    with db_manager.get_session() as db:
        review_service = ReviewService(db)

        # Good score (only info issues)
        good_results = {
            'total_files': 1,
            'analyzed_files': 1,
            'total_issues': 1,
            'files': [{
                'file_path': 'app.py',
                'issues': [{'severity': 'info', 'title': 'Minor issue', 'line_number': 1}]
            }]
        }

        comments = review_service.generate_review_comments(good_results, test_pr.id)
        success, review, error = review_service.save_review(
            test_pr.id,
            test_user.id,
            good_results,
            comments
        )

        # Score should be 99 (100 - 1 for info)
        assert review.overall_score >= 80
        assert review.approved is True
