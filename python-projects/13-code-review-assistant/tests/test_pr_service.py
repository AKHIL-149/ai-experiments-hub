"""Tests for pull request service"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from src.core.database import DatabaseManager, User, Repository, PullRequest, PRStatus, RepositoryStatus
from src.services.pr_service import PullRequestService


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
            status=RepositoryStatus.READY
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return repo


@pytest.fixture
def mock_github_pr_info():
    """Mock GitHub PR info"""
    return {
        'number': 42,
        'title': 'Add new feature',
        'description': 'This PR adds a new feature',
        'author': 'contributor',
        'author_avatar': 'https://github.com/avatar.png',
        'state': 'open',
        'is_merged': False,
        'is_draft': False,
        'source_branch': 'feature-branch',
        'target_branch': 'main',
        'github_id': 123456,
        'html_url': 'https://github.com/user/test-repo/pull/42',
        'commits_count': 5,
        'additions': 100,
        'deletions': 50,
        'changed_files': 3,
        'mergeable': True,
        'mergeable_state': 'clean',
        'created_at': '2024-01-01T12:00:00',
        'updated_at': '2024-01-02T12:00:00'
    }


def test_import_pr_from_github_success(db_manager, test_repository, mock_github_pr_info):
    """Test successfully importing PR from GitHub"""
    with db_manager.get_session() as db:
        with patch('src.services.pr_service.GitHubService') as MockGitHub:
            # Mock GitHub service
            mock_service = Mock()
            mock_service.get_pull_request_info.return_value = (True, mock_github_pr_info, None)
            MockGitHub.return_value = mock_service

            # Import PR
            pr_service = PullRequestService(db)
            success, pr, error = pr_service.import_from_github(
                repository_id=test_repository.id,
                pr_number=42,
                github_token='test_token'
            )

            assert success is True
            assert error is None
            assert pr is not None
            assert pr.pr_number == 42
            assert pr.title == 'Add new feature'
            assert pr.author == 'contributor'
            assert pr.status == PRStatus.OPEN


def test_import_pr_repository_not_found(db_manager):
    """Test importing PR with invalid repository"""
    with db_manager.get_session() as db:
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.import_from_github(
            repository_id='nonexistent',
            pr_number=42,
            github_token='test_token'
        )

        assert success is False
        assert pr is None
        assert 'not found' in error.lower()


def test_import_pr_github_error(db_manager, test_repository):
    """Test importing PR when GitHub API fails"""
    with db_manager.get_session() as db:
        with patch('src.services.pr_service.GitHubService') as MockGitHub:
            # Mock GitHub service failure
            mock_service = Mock()
            mock_service.get_pull_request_info.return_value = (False, None, "API error")
            MockGitHub.return_value = mock_service

            pr_service = PullRequestService(db)
            success, pr, error = pr_service.import_from_github(
                repository_id=test_repository.id,
                pr_number=999,
                github_token='test_token'
            )

            assert success is False
            assert pr is None
            assert error == "API error"


def test_import_existing_pr_updates(db_manager, test_repository, mock_github_pr_info):
    """Test that importing existing PR updates it"""
    with db_manager.get_session() as db:
        # Create existing PR
        existing_pr = PullRequest(
            repository_id=test_repository.id,
            pr_number=42,
            title='Old Title',
            author='contributor',
            source_branch='feature',
            target_branch='main',
            status=PRStatus.OPEN
        )
        db.add(existing_pr)
        db.commit()

        with patch('src.services.pr_service.GitHubService') as MockGitHub:
            # Mock GitHub service with updated info
            updated_info = mock_github_pr_info.copy()
            updated_info['title'] = 'Updated Title'

            mock_service = Mock()
            mock_service.get_pull_request_info.return_value = (True, updated_info, None)
            MockGitHub.return_value = mock_service

            # Re-import PR
            pr_service = PullRequestService(db)
            success, pr, error = pr_service.import_from_github(
                repository_id=test_repository.id,
                pr_number=42,
                github_token='test_token'
            )

            assert success is True
            assert pr.title == 'Updated Title'


def test_get_pr_by_id(db_manager, test_repository):
    """Test getting PR by ID"""
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
        db.refresh(pr)

        # Get PR
        pr_service = PullRequestService(db)
        success, retrieved_pr, error = pr_service.get_pr(pr.id)

        assert success is True
        assert retrieved_pr.id == pr.id
        assert retrieved_pr.pr_number == 42


def test_get_pr_not_found(db_manager):
    """Test getting non-existent PR"""
    with db_manager.get_session() as db:
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.get_pr('nonexistent-id')

        assert success is False
        assert pr is None
        assert 'not found' in error.lower()


def test_get_pr_by_number(db_manager, test_repository):
    """Test getting PR by repository and PR number"""
    with db_manager.get_session() as db:
        pr = PullRequest(
            repository_id=test_repository.id,
            pr_number=123,
            title='Test PR',
            author='author',
            source_branch='feature',
            target_branch='main'
        )
        db.add(pr)
        db.commit()

        pr_service = PullRequestService(db)
        success, retrieved_pr, error = pr_service.get_pr_by_number(
            repository_id=test_repository.id,
            pr_number=123
        )

        assert success is True
        assert retrieved_pr.pr_number == 123


def test_list_prs(db_manager, test_repository):
    """Test listing pull requests"""
    with db_manager.get_session() as db:
        # Create multiple PRs
        for i in range(5):
            pr = PullRequest(
                repository_id=test_repository.id,
                pr_number=i + 1,
                title=f'PR {i + 1}',
                author='author',
                source_branch=f'feature-{i}',
                target_branch='main'
            )
            db.add(pr)
        db.commit()

        # List all PRs
        pr_service = PullRequestService(db)
        success, prs, error = pr_service.list_prs(repository_id=test_repository.id)

        assert success is True
        assert len(prs) == 5


def test_list_prs_with_status_filter(db_manager, test_repository):
    """Test listing PRs with status filter"""
    with db_manager.get_session() as db:
        # Create PRs with different statuses
        pr1 = PullRequest(
            repository_id=test_repository.id,
            pr_number=1,
            title='Open PR',
            author='author',
            source_branch='feature-1',
            target_branch='main',
            status=PRStatus.OPEN
        )
        pr2 = PullRequest(
            repository_id=test_repository.id,
            pr_number=2,
            title='Merged PR',
            author='author',
            source_branch='feature-2',
            target_branch='main',
            status=PRStatus.MERGED
        )
        db.add_all([pr1, pr2])
        db.commit()

        # List only open PRs
        pr_service = PullRequestService(db)
        success, prs, error = pr_service.list_prs(
            repository_id=test_repository.id,
            status=PRStatus.OPEN
        )

        assert success is True
        assert len(prs) == 1
        assert prs[0].status == PRStatus.OPEN


def test_list_prs_pagination(db_manager, test_repository):
    """Test PR listing pagination"""
    with db_manager.get_session() as db:
        # Create 10 PRs
        for i in range(10):
            pr = PullRequest(
                repository_id=test_repository.id,
                pr_number=i + 1,
                title=f'PR {i + 1}',
                author='author',
                source_branch=f'feature-{i}',
                target_branch='main'
            )
            db.add(pr)
        db.commit()

        pr_service = PullRequestService(db)

        # Get first page
        success, page1, error = pr_service.list_prs(
            repository_id=test_repository.id,
            limit=5,
            offset=0
        )

        # Get second page
        success, page2, error = pr_service.list_prs(
            repository_id=test_repository.id,
            limit=5,
            offset=5
        )

        assert len(page1) == 5
        assert len(page2) == 5
        assert page1[0].id != page2[0].id


def test_update_pr_status(db_manager, test_repository):
    """Test updating PR status"""
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
        pr_id = pr.id

        # Update status
        pr_service = PullRequestService(db)
        success, error = pr_service.update_status(pr_id, PRStatus.REVIEWED)

        assert success is True
        assert error is None

        # Verify update
        db.refresh(pr)
        assert pr.status == PRStatus.REVIEWED
        assert pr.reviewed_at is not None


def test_delete_pr(db_manager, test_repository):
    """Test deleting a pull request"""
    with db_manager.get_session() as db:
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
        pr_id = pr.id

        # Delete PR
        pr_service = PullRequestService(db)
        success, error = pr_service.delete_pr(pr_id)

        assert success is True
        assert error is None

        # Verify deletion
        deleted = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
        assert deleted is None


def test_map_github_status(db_manager):
    """Test GitHub status mapping"""
    with db_manager.get_session() as db:
        pr_service = PullRequestService(db)

        # Open PR
        assert pr_service._map_github_status('open', False) == PRStatus.OPEN

        # Closed PR
        assert pr_service._map_github_status('closed', False) == PRStatus.CLOSED

        # Merged PR
        assert pr_service._map_github_status('closed', True) == PRStatus.MERGED


def test_pr_to_dict(db_manager, test_repository):
    """Test PR to_dict() includes all fields"""
    with db_manager.get_session() as db:
        pr = PullRequest(
            repository_id=test_repository.id,
            pr_number=42,
            title='Test PR',
            description='Description',
            author='author',
            author_avatar='https://avatar.png',
            source_branch='feature',
            target_branch='main',
            is_draft=True,
            is_merged=False,
            commits_count=5,
            additions=100,
            deletions=50,
            changed_files=3,
            mergeable=True,
            mergeable_state='clean'
        )
        db.add(pr)
        db.commit()

        pr_dict = pr.to_dict()

        assert pr_dict['pr_number'] == 42
        assert pr_dict['is_draft'] is True
        assert pr_dict['commits_count'] == 5
        assert pr_dict['additions'] == 100
        assert pr_dict['deletions'] == 50
        assert pr_dict['mergeable'] is True
