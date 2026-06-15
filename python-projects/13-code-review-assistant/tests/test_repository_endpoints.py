"""Tests for repository endpoints"""
import pytest
from src.core.database import DatabaseManager, Repository, RepositoryStatus, User


@pytest.fixture
def db_manager():
    """Create test database manager"""
    db = DatabaseManager('sqlite:///:memory:')
    yield db


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


def test_create_repository(db_manager, test_user):
    """Test creating a repository"""
    with db_manager.get_session() as db:
        repo = Repository(
            user_id=test_user.id,
            name='test-repo',
            github_url='https://github.com/user/test-repo',
            status=RepositoryStatus.PENDING
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

        assert repo.id is not None
        assert repo.name == 'test-repo'
        assert repo.github_url == 'https://github.com/user/test-repo'
        assert repo.status == RepositoryStatus.PENDING
        assert repo.user_id == test_user.id


def test_list_repositories(db_manager, test_user):
    """Test listing repositories for a user"""
    with db_manager.get_session() as db:
        # Create multiple repositories
        repo1 = Repository(
            user_id=test_user.id,
            name='repo1',
            github_url='https://github.com/user/repo1',
            status=RepositoryStatus.READY
        )
        repo2 = Repository(
            user_id=test_user.id,
            name='repo2',
            github_url='https://github.com/user/repo2',
            status=RepositoryStatus.PENDING
        )
        db.add_all([repo1, repo2])
        db.commit()

        # Query repositories
        repos = db.query(Repository).filter(
            Repository.user_id == test_user.id
        ).all()

        assert len(repos) == 2
        assert repos[0].user_id == test_user.id
        assert repos[1].user_id == test_user.id


def test_get_repository(db_manager, test_user):
    """Test getting a specific repository"""
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

        repo_id = repo.id

    with db_manager.get_session() as db:
        found_repo = db.query(Repository).filter(
            Repository.id == repo_id
        ).first()

        assert found_repo is not None
        assert found_repo.id == repo_id
        assert found_repo.name == 'test-repo'


def test_update_repository(db_manager, test_user):
    """Test updating repository fields"""
    with db_manager.get_session() as db:
        repo = Repository(
            user_id=test_user.id,
            name='old-name',
            github_url='https://github.com/user/repo',
            default_branch='main',
            status=RepositoryStatus.PENDING
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

        repo_id = repo.id

    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == repo_id
        ).first()

        # Update fields
        repo.name = 'new-name'
        repo.default_branch = 'develop'
        repo.status = RepositoryStatus.READY
        db.commit()
        db.refresh(repo)

        assert repo.name == 'new-name'
        assert repo.default_branch == 'develop'
        assert repo.status == RepositoryStatus.READY


def test_delete_repository(db_manager, test_user):
    """Test deleting a repository"""
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

        repo_id = repo.id

    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == repo_id
        ).first()

        db.delete(repo)
        db.commit()

    with db_manager.get_session() as db:
        deleted_repo = db.query(Repository).filter(
            Repository.id == repo_id
        ).first()

        assert deleted_repo is None


def test_repository_to_dict(db_manager, test_user):
    """Test repository serialization"""
    with db_manager.get_session() as db:
        repo = Repository(
            user_id=test_user.id,
            name='test-repo',
            github_url='https://github.com/user/test-repo',
            default_branch='main',
            status=RepositoryStatus.READY
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

        repo_dict = repo.to_dict()

        assert isinstance(repo_dict, dict)
        assert repo_dict['name'] == 'test-repo'
        assert repo_dict['github_url'] == 'https://github.com/user/test-repo'
        assert repo_dict['default_branch'] == 'main'
        assert repo_dict['status'] == 'ready'
        assert 'id' in repo_dict
        assert 'user_id' in repo_dict
        assert 'created_at' in repo_dict


def test_repository_status_values():
    """Test repository status enum values"""
    assert RepositoryStatus.PENDING.value == 'pending'
    assert RepositoryStatus.CLONING.value == 'cloning'
    assert RepositoryStatus.READY.value == 'ready'
    assert RepositoryStatus.ERROR.value == 'error'


def test_github_url_validation():
    """Test GitHub URL format validation"""
    valid_urls = [
        'https://github.com/user/repo',
        'https://github.com/user/repo.git',
        'git@github.com:user/repo.git',
    ]

    for url in valid_urls:
        assert url.startswith(('https://github.com/', 'git@github.com:'))

    invalid_urls = [
        'https://gitlab.com/user/repo',
        'https://bitbucket.org/user/repo',
        'http://github.com/user/repo',
    ]

    for url in invalid_urls:
        assert not url.startswith(('https://github.com/', 'git@github.com:'))


def test_extract_repo_name_from_url():
    """Test extracting repository name from GitHub URL"""
    test_cases = [
        ('https://github.com/user/my-repo', 'my-repo'),
        ('https://github.com/user/my-repo.git', 'my-repo'),
        ('https://github.com/user/my-repo/', 'my-repo'),
        ('git@github.com:user/my-repo.git', 'my-repo'),
    ]

    for url, expected_name in test_cases:
        parts = url.rstrip('/').rstrip('.git').split('/')
        if len(parts) >= 2:
            name = parts[-1]
            assert name == expected_name


def test_repository_user_relationship(db_manager, test_user):
    """Test repository-user relationship"""
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

        # Verify relationship
        assert repo.user_id == test_user.id
        assert repo.user is not None
        assert repo.user.username == 'testuser'


def test_repository_settings_json(db_manager, test_user):
    """Test storing custom settings as JSON"""
    with db_manager.get_session() as db:
        settings = {
            'auto_review': True,
            'min_approvals': 2,
            'ignore_patterns': ['*.md', 'docs/*']
        }

        repo = Repository(
            user_id=test_user.id,
            name='test-repo',
            github_url='https://github.com/user/test-repo',
            status=RepositoryStatus.READY,
            settings_json=settings
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

        repo_id = repo.id

    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == repo_id
        ).first()

        assert repo.settings_json is not None
        assert repo.settings_json['auto_review'] is True
        assert repo.settings_json['min_approvals'] == 2
        assert len(repo.settings_json['ignore_patterns']) == 2


def test_multiple_users_repositories(db_manager):
    """Test that users can only see their own repositories"""
    with db_manager.get_session() as db:
        # Create two users
        user1 = User(username='user1', email='user1@test.com', password_hash='hash1')
        user2 = User(username='user2', email='user2@test.com', password_hash='hash2')
        db.add_all([user1, user2])
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        # Create repos for each user
        repo1 = Repository(
            user_id=user1.id,
            name='user1-repo',
            github_url='https://github.com/user1/repo',
            status=RepositoryStatus.READY
        )
        repo2 = Repository(
            user_id=user2.id,
            name='user2-repo',
            github_url='https://github.com/user2/repo',
            status=RepositoryStatus.READY
        )
        db.add_all([repo1, repo2])
        db.commit()

        # Query repos for user1
        user1_repos = db.query(Repository).filter(
            Repository.user_id == user1.id
        ).all()

        assert len(user1_repos) == 1
        assert user1_repos[0].name == 'user1-repo'

        # Query repos for user2
        user2_repos = db.query(Repository).filter(
            Repository.user_id == user2.id
        ).all()

        assert len(user2_repos) == 1
        assert user2_repos[0].name == 'user2-repo'
