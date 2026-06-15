"""Tests for repository service"""
import pytest
from src.core.database import DatabaseManager, Repository, RepositoryStatus, User
from src.services.repository_service import RepositoryService


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
def service(db_manager):
    """Create repository service with database session"""
    with db_manager.get_session() as db:
        yield RepositoryService(db)


def test_validate_github_url_https_valid(service):
    """Test validation of valid HTTPS GitHub URLs"""
    valid_urls = [
        'https://github.com/user/repo',
        'https://github.com/user/repo/',
        'https://github.com/user/repo.git',
        'https://github.com/user-name/repo-name',
        'https://github.com/user.name/repo.name',
    ]

    for url in valid_urls:
        is_valid, error = service.validate_github_url(url)
        assert is_valid, f"URL {url} should be valid, got error: {error}"
        assert error is None


def test_validate_github_url_ssh_valid(service):
    """Test validation of valid SSH GitHub URLs"""
    valid_urls = [
        'git@github.com:user/repo.git',
        'git@github.com:user-name/repo-name.git',
        'git@github.com:user.name/repo.name.git',
    ]

    for url in valid_urls:
        is_valid, error = service.validate_github_url(url)
        assert is_valid, f"URL {url} should be valid, got error: {error}"
        assert error is None


def test_validate_github_url_invalid(service):
    """Test validation of invalid GitHub URLs"""
    invalid_urls = [
        '',
        'https://gitlab.com/user/repo',
        'https://bitbucket.org/user/repo',
        'http://github.com/user/repo',
        'github.com/user/repo',
        'not-a-url',
    ]

    for url in invalid_urls:
        is_valid, error = service.validate_github_url(url)
        assert not is_valid, f"URL {url} should be invalid"
        assert error is not None


def test_extract_repo_info_https(service):
    """Test extracting repository info from HTTPS URL"""
    url = 'https://github.com/octocat/Hello-World'
    info = service.extract_repo_info(url)

    assert info['owner'] == 'octocat'
    assert info['repo'] == 'Hello-World'
    assert info['name'] == 'Hello-World'


def test_extract_repo_info_ssh(service):
    """Test extracting repository info from SSH URL"""
    url = 'git@github.com:octocat/Hello-World.git'
    info = service.extract_repo_info(url)

    assert info['owner'] == 'octocat'
    assert info['repo'] == 'Hello-World'
    assert info['name'] == 'Hello-World'


def test_create_repository_success(db_manager, test_user):
    """Test creating a repository successfully"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        success, repo, error = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/test-repo'
        )

        assert success is True
        assert repo is not None
        assert error is None
        assert repo.name == 'test-repo'
        assert repo.status == RepositoryStatus.PENDING
        assert repo.user_id == test_user.id


def test_create_repository_custom_name(db_manager, test_user):
    """Test creating a repository with custom name"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        success, repo, error = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/repo',
            name='CustomName'
        )

        assert success is True
        assert repo.name == 'CustomName'


def test_create_repository_invalid_url(db_manager, test_user):
    """Test creating repository with invalid URL"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        success, repo, error = service.create_repository(
            user_id=test_user.id,
            github_url='https://gitlab.com/user/repo'
        )

        assert success is False
        assert repo is None
        assert error is not None
        assert 'github.com' in error.lower()


def test_create_repository_duplicate(db_manager, test_user):
    """Test creating duplicate repository"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create first repository
        success1, repo1, error1 = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/repo'
        )

        assert success1 is True

        # Try to create duplicate
        success2, repo2, error2 = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/repo'
        )

        assert success2 is False
        assert repo2 is None
        assert 'already exists' in error2.lower()


def test_get_repository_success(db_manager, test_user):
    """Test getting a repository"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, error = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/repo'
        )

        repo_id = repo.id

        # Get repository
        found_repo = service.get_repository(repo_id, test_user.id)

        assert found_repo is not None
        assert found_repo.id == repo_id
        assert found_repo.name == 'repo'


def test_get_repository_not_found(db_manager, test_user):
    """Test getting non-existent repository"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        found_repo = service.get_repository('non-existent-id', test_user.id)

        assert found_repo is None


def test_list_repositories(db_manager, test_user):
    """Test listing repositories"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create multiple repositories
        service.create_repository(test_user.id, 'https://github.com/user/repo1')
        service.create_repository(test_user.id, 'https://github.com/user/repo2')
        service.create_repository(test_user.id, 'https://github.com/user/repo3')

        # List repositories
        repos = service.list_repositories(test_user.id)

        assert len(repos) == 3
        assert all(r.user_id == test_user.id for r in repos)


def test_list_repositories_with_status_filter(db_manager, test_user):
    """Test listing repositories filtered by status"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repositories
        success1, repo1, _ = service.create_repository(test_user.id, 'https://github.com/user/repo1')
        success2, repo2, _ = service.create_repository(test_user.id, 'https://github.com/user/repo2')

        # Mark one as ready
        service.mark_as_ready(repo1.id)

        # List only ready repositories
        ready_repos = service.list_repositories(test_user.id, status=RepositoryStatus.READY)

        assert len(ready_repos) == 1
        assert ready_repos[0].status == RepositoryStatus.READY


def test_list_repositories_pagination(db_manager, test_user):
    """Test repository pagination"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create 5 repositories
        for i in range(5):
            service.create_repository(test_user.id, f'https://github.com/user/repo{i}')

        # Get first page
        page1 = service.list_repositories(test_user.id, limit=2, offset=0)
        assert len(page1) == 2

        # Get second page
        page2 = service.list_repositories(test_user.id, limit=2, offset=2)
        assert len(page2) == 2

        # Get third page
        page3 = service.list_repositories(test_user.id, limit=2, offset=4)
        assert len(page3) == 1


def test_update_repository_name(db_manager, test_user):
    """Test updating repository name"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        # Update name
        success, updated_repo, error = service.update_repository(
            repo.id,
            test_user.id,
            name='NewName'
        )

        assert success is True
        assert updated_repo.name == 'NewName'
        assert error is None


def test_update_repository_default_branch(db_manager, test_user):
    """Test updating default branch"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        # Update default branch
        success, updated_repo, error = service.update_repository(
            repo.id,
            test_user.id,
            default_branch='develop'
        )

        assert success is True
        assert updated_repo.default_branch == 'develop'


def test_update_repository_settings(db_manager, test_user):
    """Test updating repository settings"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        # Update settings
        settings = {'auto_review': True, 'min_approvals': 2}
        success, updated_repo, error = service.update_repository(
            repo.id,
            test_user.id,
            settings=settings
        )

        assert success is True
        assert updated_repo.settings_json == settings


def test_update_repository_not_found(db_manager, test_user):
    """Test updating non-existent repository"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        success, repo, error = service.update_repository(
            'non-existent-id',
            test_user.id,
            name='NewName'
        )

        assert success is False
        assert repo is None
        assert 'not found' in error.lower()


def test_update_status(db_manager, test_user):
    """Test updating repository status"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        # Update status to cloning
        success, updated_repo, error = service.update_status(
            repo.id,
            RepositoryStatus.CLONING
        )

        assert success is True
        assert updated_repo.status == RepositoryStatus.CLONING


def test_mark_as_ready(db_manager, test_user):
    """Test marking repository as ready"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        # Mark as ready
        success, updated_repo, error = service.mark_as_ready(
            repo.id,
            clone_path='/path/to/clone'
        )

        assert success is True
        assert updated_repo.status == RepositoryStatus.READY
        assert updated_repo.clone_path == '/path/to/clone'
        assert updated_repo.last_synced_at is not None


def test_mark_as_cloning(db_manager, test_user):
    """Test marking repository as cloning"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        # Mark as cloning
        success, updated_repo, error = service.mark_as_cloning(repo.id)

        assert success is True
        assert updated_repo.status == RepositoryStatus.CLONING


def test_mark_as_error(db_manager, test_user):
    """Test marking repository as error"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        # Mark as error
        error_msg = "Failed to clone repository"
        success, updated_repo, error = service.mark_as_error(repo.id, error_msg)

        assert success is True
        assert updated_repo.status == RepositoryStatus.ERROR
        assert updated_repo.settings_json['last_error'] == error_msg
        assert 'error_at' in updated_repo.settings_json


def test_delete_repository(db_manager, test_user):
    """Test deleting a repository"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        repo_id = repo.id

        # Delete repository
        success, error = service.delete_repository(repo_id, test_user.id)

        assert success is True
        assert error is None

        # Verify deletion
        found_repo = service.get_repository(repo_id, test_user.id)
        assert found_repo is None


def test_delete_repository_not_found(db_manager, test_user):
    """Test deleting non-existent repository"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        success, error = service.delete_repository('non-existent-id', test_user.id)

        assert success is False
        assert 'not found' in error.lower()


def test_get_repository_stats(db_manager, test_user):
    """Test getting repository statistics"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        # Get stats
        stats = service.get_repository_stats(repo.id, test_user.id)

        assert stats is not None
        assert stats['repository_id'] == repo.id
        assert stats['name'] == 'repo'
        assert stats['status'] == 'pending'
        assert stats['pull_requests_count'] == 0
        assert stats['total_issues'] == 0


def test_count_repositories(db_manager, test_user):
    """Test counting repositories"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repositories
        service.create_repository(test_user.id, 'https://github.com/user/repo1')
        service.create_repository(test_user.id, 'https://github.com/user/repo2')
        service.create_repository(test_user.id, 'https://github.com/user/repo3')

        # Count all repositories
        count = service.count_repositories(test_user.id)

        assert count == 3


def test_count_repositories_by_status(db_manager, test_user):
    """Test counting repositories filtered by status"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repositories
        success1, repo1, _ = service.create_repository(test_user.id, 'https://github.com/user/repo1')
        success2, repo2, _ = service.create_repository(test_user.id, 'https://github.com/user/repo2')

        # Mark one as ready
        service.mark_as_ready(repo1.id)

        # Count pending repositories
        pending_count = service.count_repositories(test_user.id, status=RepositoryStatus.PENDING)
        assert pending_count == 1

        # Count ready repositories
        ready_count = service.count_repositories(test_user.id, status=RepositoryStatus.READY)
        assert ready_count == 1
