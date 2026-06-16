"""Tests for repository worker tasks"""
import pytest
import os
import sys
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from src.core.database import DatabaseManager, Repository, RepositoryStatus, User

# Mock celery_app module before importing worker
mock_celery = Mock()
# Make the task decorator a pass-through
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery_app'] = mock_celery

from src.workers.repository_worker import (
    clone_repository_task,
    sync_repository_task,
    delete_repository_task
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
            github_url='https://github.com/test/repo',
            status=RepositoryStatus.PENDING
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return repo


@pytest.fixture
def temp_clone_dir():
    """Create temporary directory for cloning"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


def test_clone_repository_task_success(db_manager, test_repository, temp_clone_dir):
    """Test successful repository cloning"""
    with patch('src.workers.repository_worker.git_client') as mock_git_client, \
         patch('src.workers.repository_worker.db_manager', db_manager):

        # Mock successful clone
        clone_path = os.path.join(temp_clone_dir, test_repository.id)
        mock_git_client.clone_repository.return_value = (True, clone_path, None)

        # Create mock task
        mock_self = Mock()
        mock_self.request.id = 'test_job_123'
        mock_self.update_state = Mock()

        # Execute task
        result = clone_repository_task(
            mock_self,
            repository_id=test_repository.id,
            github_url=test_repository.github_url,
            branch='main',
            depth=1
        )

        # Verify result
        assert result['success'] is True
        assert result['clone_path'] == clone_path
        assert result['repository_id'] == test_repository.id

        # Verify git_client was called correctly
        mock_git_client.clone_repository.assert_called_once_with(
            repo_url=test_repository.github_url,
            repo_name=test_repository.id,
            branch='main',
            depth=1
        )

        # Verify state updates
        assert mock_self.update_state.called


def test_clone_repository_task_failure(db_manager, test_repository):
    """Test repository cloning failure"""
    with patch('src.workers.repository_worker.git_client') as mock_git_client, \
         patch('src.workers.repository_worker.db_manager', db_manager):

        # Mock clone failure
        error_msg = "Clone failed: Authentication required"
        mock_git_client.clone_repository.return_value = (False, None, error_msg)

        # Create mock task
        mock_self = Mock()
        mock_self.request.id = 'test_job_456'
        mock_self.update_state = Mock()

        # Execute task
        result = clone_repository_task(
            mock_self,
            repository_id=test_repository.id,
            github_url=test_repository.github_url
        )

        # Verify result
        assert result['success'] is False
        assert result['error'] == error_msg
        assert result['repository_id'] == test_repository.id

        # Verify repository status was updated to ERROR
        with db_manager.get_session() as db:
            repo = db.query(Repository).filter(
                Repository.id == test_repository.id
            ).first()
            assert repo.status == RepositoryStatus.ERROR


def test_clone_repository_updates_status(db_manager, test_repository, temp_clone_dir):
    """Test that clone task updates repository status correctly"""
    with patch('src.workers.repository_worker.git_client') as mock_git_client, \
         patch('src.workers.repository_worker.db_manager', db_manager):

        clone_path = os.path.join(temp_clone_dir, test_repository.id)
        mock_git_client.clone_repository.return_value = (True, clone_path, None)

        mock_self = Mock()
        mock_self.request.id = 'test_job_789'
        mock_self.update_state = Mock()

        # Execute task
        clone_repository_task(
            mock_self,
            repository_id=test_repository.id,
            github_url=test_repository.github_url
        )

        # Verify status progression: PENDING -> CLONING -> READY
        with db_manager.get_session() as db:
            repo = db.query(Repository).filter(
                Repository.id == test_repository.id
            ).first()
            assert repo.status == RepositoryStatus.READY
            assert repo.clone_path == clone_path
            assert repo.last_synced_at is not None


def test_sync_repository_task_success(db_manager, test_repository, temp_clone_dir):
    """Test successful repository sync"""
    # Set up repository as already cloned
    clone_path = os.path.join(temp_clone_dir, test_repository.id)
    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == test_repository.id
        ).first()
        repo.clone_path = clone_path
        repo.status = RepositoryStatus.READY
        db.commit()

    with patch('src.workers.repository_worker.git_client') as mock_git_client, \
         patch('src.workers.repository_worker.db_manager', db_manager):

        # Mock successful operations
        mock_git_client.repository_exists.return_value = True
        mock_git_client.fetch_repository.return_value = (True, None)
        mock_git_client.pull_repository.return_value = (True, None)

        # Create mock task
        mock_self = Mock()
        mock_self.request.id = 'sync_job_123'
        mock_self.update_state = Mock()

        # Execute task
        result = sync_repository_task(
            mock_self,
            repository_id=test_repository.id,
            clone_path=clone_path
        )

        # Verify result
        assert result['success'] is True
        assert result['repository_id'] == test_repository.id

        # Verify git operations were called
        mock_git_client.repository_exists.assert_called_once_with(clone_path)
        mock_git_client.fetch_repository.assert_called_once_with(clone_path)
        mock_git_client.pull_repository.assert_called_once_with(clone_path)


def test_sync_repository_not_cloned(db_manager, test_repository):
    """Test sync when repository is not cloned locally"""
    fake_path = '/nonexistent/path'

    with patch('src.workers.repository_worker.git_client') as mock_git_client, \
         patch('src.workers.repository_worker.db_manager', db_manager):

        # Mock repository not existing
        mock_git_client.repository_exists.return_value = False

        mock_self = Mock()
        mock_self.request.id = 'sync_job_456'
        mock_self.update_state = Mock()

        # Execute task
        result = sync_repository_task(
            mock_self,
            repository_id=test_repository.id,
            clone_path=fake_path
        )

        # Verify result
        assert result['success'] is False
        assert 'not found locally' in result['error']


def test_sync_repository_fetch_failure(db_manager, test_repository, temp_clone_dir):
    """Test sync when fetch fails"""
    clone_path = os.path.join(temp_clone_dir, test_repository.id)

    with patch('src.workers.repository_worker.git_client') as mock_git_client, \
         patch('src.workers.repository_worker.db_manager', db_manager):

        mock_git_client.repository_exists.return_value = True
        mock_git_client.fetch_repository.return_value = (False, "Network error")

        mock_self = Mock()
        mock_self.request.id = 'sync_job_789'
        mock_self.update_state = Mock()

        # Execute task
        result = sync_repository_task(
            mock_self,
            repository_id=test_repository.id,
            clone_path=clone_path
        )

        # Verify result
        assert result['success'] is False
        assert 'Fetch failed' in result['error']


def test_sync_repository_pull_failure(db_manager, test_repository, temp_clone_dir):
    """Test sync when pull fails"""
    clone_path = os.path.join(temp_clone_dir, test_repository.id)

    with patch('src.workers.repository_worker.git_client') as mock_git_client, \
         patch('src.workers.repository_worker.db_manager', db_manager):

        mock_git_client.repository_exists.return_value = True
        mock_git_client.fetch_repository.return_value = (True, None)
        mock_git_client.pull_repository.return_value = (False, "Merge conflict")

        mock_self = Mock()
        mock_self.request.id = 'sync_job_101'
        mock_self.update_state = Mock()

        # Execute task
        result = sync_repository_task(
            mock_self,
            repository_id=test_repository.id,
            clone_path=clone_path
        )

        # Verify result
        assert result['success'] is False
        assert 'Pull failed' in result['error']


def test_delete_repository_task_success(test_repository, temp_clone_dir):
    """Test successful repository deletion"""
    # Create a fake clone directory
    clone_path = os.path.join(temp_clone_dir, test_repository.id)
    os.makedirs(clone_path)

    # Create some files in it
    test_file = os.path.join(clone_path, 'test.txt')
    with open(test_file, 'w') as f:
        f.write('test content')

    assert os.path.exists(clone_path)

    with patch('src.workers.repository_worker.git_client') as mock_git_client:
        # Mock successful deletion
        mock_git_client.delete_repository.return_value = (True, None)

        mock_self = Mock()
        mock_self.request.id = 'delete_job_123'
        mock_self.update_state = Mock()

        # Execute task
        result = delete_repository_task(
            mock_self,
            repository_id=test_repository.id,
            clone_path=clone_path
        )

        # Verify result
        assert result['success'] is True
        assert result['repository_id'] == test_repository.id

        # Verify git_client was called
        mock_git_client.delete_repository.assert_called_once_with(clone_path)


def test_delete_repository_nonexistent_path(test_repository):
    """Test deleting repository with nonexistent path"""
    fake_path = '/nonexistent/path'

    with patch('src.workers.repository_worker.git_client') as mock_git_client:
        # Mock that path doesn't exist
        mock_git_client.delete_repository.return_value = (True, None)

        mock_self = Mock()
        mock_self.request.id = 'delete_job_456'
        mock_self.update_state = Mock()

        # Execute task
        result = delete_repository_task(
            mock_self,
            repository_id=test_repository.id,
            clone_path=fake_path
        )

        # Should still succeed (nothing to delete)
        assert result['success'] is True


def test_delete_repository_task_failure(test_repository, temp_clone_dir):
    """Test repository deletion failure"""
    clone_path = os.path.join(temp_clone_dir, test_repository.id)
    os.makedirs(clone_path)

    with patch('src.workers.repository_worker.git_client') as mock_git_client:
        # Mock deletion failure
        error_msg = "Permission denied"
        mock_git_client.delete_repository.return_value = (False, error_msg)

        mock_self = Mock()
        mock_self.request.id = 'delete_job_789'
        mock_self.update_state = Mock()

        # Execute task
        result = delete_repository_task(
            mock_self,
            repository_id=test_repository.id,
            clone_path=clone_path
        )

        # Verify result
        assert result['success'] is False
        assert result['error'] == error_msg


def test_clone_task_exception_handling(db_manager, test_repository):
    """Test exception handling in clone task"""
    with patch('src.workers.repository_worker.git_client') as mock_git_client, \
         patch('src.workers.repository_worker.db_manager', db_manager):

        # Mock exception
        mock_git_client.clone_repository.side_effect = Exception("Unexpected error")

        mock_self = Mock()
        mock_self.request.id = 'error_job_123'
        mock_self.update_state = Mock()

        # Execute task
        result = clone_repository_task(
            mock_self,
            repository_id=test_repository.id,
            github_url=test_repository.github_url
        )

        # Verify error handling
        assert result['success'] is False
        assert 'Unexpected error' in result['error']

        # Verify repository marked as error
        with db_manager.get_session() as db:
            repo = db.query(Repository).filter(
                Repository.id == test_repository.id
            ).first()
            assert repo.status == RepositoryStatus.ERROR


def test_sync_task_exception_handling(test_repository, temp_clone_dir):
    """Test exception handling in sync task"""
    clone_path = os.path.join(temp_clone_dir, test_repository.id)

    with patch('src.workers.repository_worker.git_client') as mock_git_client:
        # Mock exception
        mock_git_client.repository_exists.side_effect = Exception("Unexpected error")

        mock_self = Mock()
        mock_self.request.id = 'error_job_456'
        mock_self.update_state = Mock()

        # Execute task
        result = sync_repository_task(
            mock_self,
            repository_id=test_repository.id,
            clone_path=clone_path
        )

        # Verify error handling
        assert result['success'] is False
        assert 'Unexpected error' in result['error']


def test_delete_task_exception_handling(test_repository, temp_clone_dir):
    """Test exception handling in delete task"""
    clone_path = os.path.join(temp_clone_dir, test_repository.id)

    with patch('src.workers.repository_worker.git_client') as mock_git_client:
        # Mock exception
        mock_git_client.delete_repository.side_effect = Exception("Unexpected error")

        mock_self = Mock()
        mock_self.request.id = 'error_job_789'
        mock_self.update_state = Mock()

        # Execute task with path that exists
        os.makedirs(clone_path, exist_ok=True)

        result = delete_repository_task(
            mock_self,
            repository_id=test_repository.id,
            clone_path=clone_path
        )

        # Verify error handling
        assert result['success'] is False
        assert 'Unexpected error' in result['error']
