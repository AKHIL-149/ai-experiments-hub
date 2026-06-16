"""Integration tests for repository database operations"""
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
def second_user(db_manager):
    """Create a second test user"""
    with db_manager.get_session() as db:
        user = User(
            username='seconduser',
            email='second@example.com',
            password_hash='hashed_password'
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def test_repository_creation_integration(db_manager, test_user):
    """Test complete repository creation workflow"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, error = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/test-repo',
            name='Test Repo'
        )

        assert success is True
        assert repo is not None
        assert error is None

        # Verify in database
        db_repo = db.query(Repository).filter(
            Repository.id == repo.id
        ).first()

        assert db_repo is not None
        assert db_repo.name == 'Test Repo'
        assert db_repo.user_id == test_user.id
        assert db_repo.status == RepositoryStatus.PENDING


def test_repository_update_integration(db_manager, test_user):
    """Test complete repository update workflow"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/repo'
        )

        repo_id = repo.id

        # Update repository
        success, updated_repo, error = service.update_repository(
            repository_id=repo_id,
            user_id=test_user.id,
            name='Updated Name',
            default_branch='develop'
        )

        assert success is True
        assert updated_repo.name == 'Updated Name'
        assert updated_repo.default_branch == 'develop'

        # Verify in database
        db_repo = db.query(Repository).filter(
            Repository.id == repo_id
        ).first()

        assert db_repo.name == 'Updated Name'
        assert db_repo.default_branch == 'develop'


def test_repository_status_workflow(db_manager, test_user):
    """Test repository status transitions"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository (PENDING)
        success, repo, _ = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/repo'
        )
        assert repo.status == RepositoryStatus.PENDING

        # Mark as CLONING
        success, repo, _ = service.mark_as_cloning(repo.id)
        assert success is True
        assert repo.status == RepositoryStatus.CLONING

        # Mark as READY
        success, repo, _ = service.mark_as_ready(
            repo.id,
            clone_path='/tmp/repos/repo'
        )
        assert success is True
        assert repo.status == RepositoryStatus.READY
        assert repo.clone_path == '/tmp/repos/repo'
        assert repo.last_synced_at is not None

        # Verify status persisted
        db_repo = db.query(Repository).filter(
            Repository.id == repo.id
        ).first()
        assert db_repo.status == RepositoryStatus.READY


def test_repository_error_handling(db_manager, test_user):
    """Test repository error status handling"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/repo'
        )

        # Mark as error
        error_msg = "Clone failed: Authentication required"
        success, error_repo, _ = service.mark_as_error(repo.id, error_msg)

        assert success is True
        assert error_repo.status == RepositoryStatus.ERROR
        assert error_repo.settings_json is not None
        assert 'last_error' in error_repo.settings_json
        assert error_repo.settings_json['last_error'] == error_msg
        assert 'error_at' in error_repo.settings_json


def test_repository_deletion_integration(db_manager, test_user):
    """Test complete repository deletion workflow"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/repo'
        )
        repo_id = repo.id

        # Verify exists
        assert service.get_repository(repo_id, test_user.id) is not None

        # Delete repository
        success, error = service.delete_repository(repo_id, test_user.id)
        assert success is True
        assert error is None

        # Verify deleted
        assert service.get_repository(repo_id, test_user.id) is None


def test_repository_listing_integration(db_manager, test_user):
    """Test repository listing with filters"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create multiple repositories
        service.create_repository(test_user.id, 'https://github.com/user/repo1')
        success, repo2, _ = service.create_repository(test_user.id, 'https://github.com/user/repo2')
        service.create_repository(test_user.id, 'https://github.com/user/repo3')

        # Mark one as ready
        service.mark_as_ready(repo2.id)

        # List all repositories
        all_repos = service.list_repositories(test_user.id)
        assert len(all_repos) == 3

        # List only ready repositories
        ready_repos = service.list_repositories(
            test_user.id,
            status=RepositoryStatus.READY
        )
        assert len(ready_repos) == 1
        assert ready_repos[0].status == RepositoryStatus.READY

        # List with pagination
        page1 = service.list_repositories(test_user.id, limit=2, offset=0)
        assert len(page1) == 2

        page2 = service.list_repositories(test_user.id, limit=2, offset=2)
        assert len(page2) == 1


def test_repository_user_isolation(db_manager, test_user, second_user):
    """Test that users can only access their own repositories"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # User 1 creates repository
        success, repo1, _ = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user1/repo'
        )

        # User 2 creates repository
        success, repo2, _ = service.create_repository(
            user_id=second_user.id,
            github_url='https://github.com/user2/repo'
        )

        # User 1 can only see their repository
        user1_repos = service.list_repositories(test_user.id)
        assert len(user1_repos) == 1
        assert user1_repos[0].id == repo1.id

        # User 2 can only see their repository
        user2_repos = service.list_repositories(second_user.id)
        assert len(user2_repos) == 1
        assert user2_repos[0].id == repo2.id

        # User 1 cannot access user 2's repository
        accessed_repo = service.get_repository(repo2.id, test_user.id)
        assert accessed_repo is None

        # User 2 cannot update user 1's repository
        success, _, error = service.update_repository(
            repo1.id,
            second_user.id,
            name='Hacked Name'
        )
        assert success is False
        assert 'not found' in error.lower()


def test_repository_duplicate_prevention(db_manager, test_user):
    """Test that duplicate repositories are prevented"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        github_url = 'https://github.com/user/repo'

        # Create first repository
        success1, repo1, _ = service.create_repository(
            test_user.id,
            github_url
        )
        assert success1 is True

        # Try to create duplicate
        success2, repo2, error2 = service.create_repository(
            test_user.id,
            github_url
        )
        assert success2 is False
        assert repo2 is None
        assert 'already exists' in error2.lower()


def test_repository_counting(db_manager, test_user):
    """Test repository counting functionality"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Initially no repositories
        assert service.count_repositories(test_user.id) == 0

        # Create repositories
        success, repo1, _ = service.create_repository(test_user.id, 'https://github.com/user/repo1')
        success, repo2, _ = service.create_repository(test_user.id, 'https://github.com/user/repo2')
        success, repo3, _ = service.create_repository(test_user.id, 'https://github.com/user/repo3')

        # Mark one as ready
        service.mark_as_ready(repo1.id)

        # Count all
        assert service.count_repositories(test_user.id) == 3

        # Count by status
        assert service.count_repositories(test_user.id, RepositoryStatus.READY) == 1
        assert service.count_repositories(test_user.id, RepositoryStatus.PENDING) == 2


def test_repository_statistics(db_manager, test_user):
    """Test repository statistics retrieval"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/awesome-repo',
            name='Awesome Repo'
        )

        # Get statistics
        stats = service.get_repository_stats(repo.id, test_user.id)

        assert stats is not None
        assert stats['repository_id'] == repo.id
        assert stats['name'] == 'Awesome Repo'
        assert stats['status'] == 'pending'
        assert stats['pull_requests_count'] == 0
        assert stats['total_issues'] == 0


def test_repository_settings_persistence(db_manager, test_user):
    """Test that repository settings are persisted correctly"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository with settings
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        # Update settings
        custom_settings = {
            'auto_review': True,
            'min_approvals': 2,
            'ignore_patterns': ['*.md', 'docs/*'],
            'notify_on_issues': True
        }

        success, updated_repo, _ = service.update_repository(
            repo.id,
            test_user.id,
            settings=custom_settings
        )

        assert success is True
        assert updated_repo.settings_json == custom_settings

        # Verify settings persisted across sessions
        retrieved_repo = service.get_repository(repo.id, test_user.id)
        assert retrieved_repo.settings_json == custom_settings
        assert retrieved_repo.settings_json['auto_review'] is True
        assert retrieved_repo.settings_json['min_approvals'] == 2


def test_repository_url_variations(db_manager, test_user):
    """Test that different URL variations are handled correctly"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Test HTTPS URL
        success, repo1, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo1'
        )
        assert success is True
        assert repo1.name == 'repo1'

        # Test HTTPS URL with .git
        success, repo2, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo2.git'
        )
        assert success is True
        assert repo2.name == 'repo2'

        # Test SSH URL
        success, repo3, _ = service.create_repository(
            test_user.id,
            'git@github.com:user/repo3.git'
        )
        assert success is True
        assert repo3.name == 'repo3'


def test_repository_relationship_with_user(db_manager, test_user):
    """Test repository-user relationship integrity"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create repository
        success, repo, _ = service.create_repository(
            test_user.id,
            'https://github.com/user/repo'
        )

        # Verify relationship through direct query
        db_repo = db.query(Repository).filter(
            Repository.id == repo.id
        ).first()

        assert db_repo.user is not None
        assert db_repo.user.id == test_user.id
        assert db_repo.user.username == test_user.username
        assert db_repo.user.email == test_user.email


def test_complete_repository_lifecycle(db_manager, test_user):
    """Test complete repository lifecycle from creation to deletion"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # 1. Create repository
        success, repo, error = service.create_repository(
            user_id=test_user.id,
            github_url='https://github.com/user/lifecycle-test',
            name='Lifecycle Test'
        )
        assert success is True
        assert repo.status == RepositoryStatus.PENDING

        repo_id = repo.id

        # 2. Mark as cloning
        success, repo, _ = service.mark_as_cloning(repo_id)
        assert success is True
        assert repo.status == RepositoryStatus.CLONING

        # 3. Mark as ready
        success, repo, _ = service.mark_as_ready(
            repo_id,
            clone_path='/tmp/repos/lifecycle-test'
        )
        assert success is True
        assert repo.status == RepositoryStatus.READY

        # 4. Update repository settings
        success, repo, _ = service.update_repository(
            repo_id,
            test_user.id,
            settings={'auto_review': True}
        )
        assert success is True

        # 5. Get repository stats
        stats = service.get_repository_stats(repo_id, test_user.id)
        assert stats is not None

        # 6. Verify in list
        repos = service.list_repositories(test_user.id)
        assert any(r.id == repo_id for r in repos)

        # 7. Delete repository
        success, error = service.delete_repository(repo_id, test_user.id)
        assert success is True

        # 8. Verify deletion
        deleted_repo = service.get_repository(repo_id, test_user.id)
        assert deleted_repo is None


def test_concurrent_repository_operations(db_manager, test_user):
    """Test multiple concurrent repository operations"""
    with db_manager.get_session() as db:
        service = RepositoryService(db)

        # Create multiple repositories rapidly
        repos = []
        for i in range(10):
            success, repo, _ = service.create_repository(
                test_user.id,
                f'https://github.com/user/repo{i}',
                name=f'Repo {i}'
            )
            assert success is True
            repos.append(repo)

        # Verify all created
        assert len(repos) == 10

        # Update multiple repositories
        for i, repo in enumerate(repos[:5]):
            success, _, _ = service.update_repository(
                repo.id,
                test_user.id,
                name=f'Updated Repo {i}'
            )
            assert success is True

        # Mark some as ready
        for repo in repos[5:]:
            service.mark_as_ready(repo.id)

        # Verify counts
        assert service.count_repositories(test_user.id) == 10
        assert service.count_repositories(test_user.id, RepositoryStatus.READY) == 5
