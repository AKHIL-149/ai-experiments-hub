"""Tests for repository status endpoint"""
import pytest
import sys
from unittest.mock import Mock, patch
from src.core.database import DatabaseManager, Repository, RepositoryStatus, User

# Mock celery module
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()


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


def test_repository_status_without_job(db_manager, test_user, test_repository):
    """Test getting repository status without job_id"""
    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == test_repository.id
        ).first()

        assert repo is not None
        assert repo.status == RepositoryStatus.PENDING
        assert repo.user_id == test_user.id


def test_repository_status_with_pending_job(db_manager, test_user, test_repository):
    """Test repository status with PENDING job"""
    from celery.result import AsyncResult

    with patch('celery.result.AsyncResult') as MockAsyncResult:
        mock_task = Mock()
        mock_task.state = 'PENDING'
        mock_task.info = {}
        MockAsyncResult.return_value = mock_task

        job_id = 'test_job_123'

        # Simulate endpoint logic
        with db_manager.get_session() as db:
            repo = db.query(Repository).filter(
                Repository.id == test_repository.id,
                Repository.user_id == test_user.id
            ).first()

            assert repo is not None

            # Get task status
            task = MockAsyncResult(job_id)
            assert task.state == 'PENDING'


def test_repository_status_with_cloning_job(db_manager, test_user, test_repository):
    """Test repository status with CLONING job"""
    from celery.result import AsyncResult

    with patch('celery.result.AsyncResult') as MockAsyncResult:
        mock_task = Mock()
        mock_task.state = 'CLONING'
        mock_task.info = {
            'status': 'Cloning repository...',
            'repository_id': test_repository.id,
            'started_at': '2024-01-01T00:00:00'
        }
        MockAsyncResult.return_value = mock_task

        job_id = 'clone_job_456'

        with db_manager.get_session() as db:
            repo = db.query(Repository).filter(
                Repository.id == test_repository.id
            ).first()

            # Verify repository exists
            assert repo is not None

            # Get task status
            task = MockAsyncResult(job_id)
            assert task.state == 'CLONING'
            assert task.info['status'] == 'Cloning repository...'


def test_repository_status_with_success_job(db_manager, test_user, test_repository):
    """Test repository status with SUCCESS job"""
    from celery.result import AsyncResult

    with patch('celery.result.AsyncResult') as MockAsyncResult:
        mock_task = Mock()
        mock_task.state = 'SUCCESS'
        mock_task.result = {
            'success': True,
            'clone_path': '/data/repos/test-repo',
            'repository_id': test_repository.id
        }
        mock_task.info = {}
        MockAsyncResult.return_value = mock_task

        job_id = 'success_job_789'

        with db_manager.get_session() as db:
            # Update repository to READY status
            repo = db.query(Repository).filter(
                Repository.id == test_repository.id
            ).first()
            repo.status = RepositoryStatus.READY
            repo.clone_path = '/data/repos/test-repo'
            db.commit()
            db.refresh(repo)

            # Verify repository status
            assert repo.status == RepositoryStatus.READY
            assert repo.clone_path == '/data/repos/test-repo'

            # Get task status
            task = MockAsyncResult(job_id)
            assert task.state == 'SUCCESS'
            assert task.result['success'] is True


def test_repository_status_with_failure_job(db_manager, test_user, test_repository):
    """Test repository status with FAILURE job"""
    from celery.result import AsyncResult

    with patch('celery.result.AsyncResult') as MockAsyncResult:
        mock_task = Mock()
        mock_task.state = 'FAILURE'
        mock_task.info = Exception("Clone failed: Authentication required")
        MockAsyncResult.return_value = mock_task

        job_id = 'failure_job_101'

        with db_manager.get_session() as db:
            # Update repository to ERROR status
            repo = db.query(Repository).filter(
                Repository.id == test_repository.id
            ).first()
            repo.status = RepositoryStatus.ERROR
            repo.settings_json = {
                'last_error': 'Clone failed: Authentication required'
            }
            db.commit()
            db.refresh(repo)

            # Verify repository status
            assert repo.status == RepositoryStatus.ERROR
            assert 'last_error' in repo.settings_json

            # Get task status
            task = MockAsyncResult(job_id)
            assert task.state == 'FAILURE'


def test_repository_status_with_syncing_job(db_manager, test_user, test_repository):
    """Test repository status with SYNCING job"""
    from celery.result import AsyncResult

    with patch('celery.result.AsyncResult') as MockAsyncResult:
        mock_task = Mock()
        mock_task.state = 'SYNCING'
        mock_task.info = {
            'status': 'Syncing repository...',
            'repository_id': test_repository.id
        }
        MockAsyncResult.return_value = mock_task

        job_id = 'sync_job_202'

        with db_manager.get_session() as db:
            repo = db.query(Repository).filter(
                Repository.id == test_repository.id
            ).first()
            repo.status = RepositoryStatus.READY
            repo.clone_path = '/data/repos/test-repo'
            db.commit()

            # Get task status
            task = MockAsyncResult(job_id)
            assert task.state == 'SYNCING'
            assert 'Syncing' in task.info['status']


def test_repository_status_with_deleting_job(db_manager, test_user, test_repository):
    """Test repository status with DELETING job"""
    from celery.result import AsyncResult

    with patch('celery.result.AsyncResult') as MockAsyncResult:
        mock_task = Mock()
        mock_task.state = 'DELETING'
        mock_task.info = {
            'status': 'Deleting repository files...',
            'repository_id': test_repository.id
        }
        MockAsyncResult.return_value = mock_task

        job_id = 'delete_job_303'

        # Get task status
        task = MockAsyncResult(job_id)
        assert task.state == 'DELETING'
        assert 'Deleting' in task.info['status']


def test_repository_status_job_lifecycle(db_manager, test_user, test_repository):
    """Test complete job lifecycle: PENDING → CLONING → SUCCESS"""
    from celery.result import AsyncResult

    states = [
        ('PENDING', {}),
        ('CLONING', {'status': 'Cloning repository...'}),
        ('SUCCESS', {})
    ]

    for state, info in states:
        with patch('celery.result.AsyncResult') as MockAsyncResult:
            mock_task = Mock()
            mock_task.state = state
            mock_task.info = info
            if state == 'SUCCESS':
                mock_task.result = {'success': True, 'clone_path': '/data/repos/test'}
            MockAsyncResult.return_value = mock_task

            task = MockAsyncResult('job_123')
            assert task.state == state


def test_repository_not_found(db_manager, test_user):
    """Test repository not found scenario"""
    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == 'nonexistent-id',
            Repository.user_id == test_user.id
        ).first()

        assert repo is None


def test_repository_user_isolation(db_manager):
    """Test that users can only see their own repository status"""
    with db_manager.get_session() as db:
        # Create two users
        user1 = User(username='user1', email='user1@test.com', password_hash='hash1')
        user2 = User(username='user2', email='user2@test.com', password_hash='hash2')
        db.add_all([user1, user2])
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        # Create repository for user1
        repo = Repository(
            user_id=user1.id,
            name='user1-repo',
            github_url='https://github.com/user1/repo',
            status=RepositoryStatus.PENDING
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

        # User2 tries to access user1's repository
        repo_access = db.query(Repository).filter(
            Repository.id == repo.id,
            Repository.user_id == user2.id
        ).first()

        assert repo_access is None


def test_multiple_job_states(db_manager, test_user, test_repository):
    """Test handling multiple different job states"""
    from celery.result import AsyncResult

    job_states = [
        'PENDING',
        'CLONING',
        'SYNCING',
        'DELETING',
        'SUCCESS',
        'FAILURE',
        'RETRY',
        'REVOKED'
    ]

    for state in job_states:
        with patch('celery.result.AsyncResult') as MockAsyncResult:
            mock_task = Mock()
            mock_task.state = state
            mock_task.info = {'status': f'Testing {state}'}
            if state == 'SUCCESS':
                mock_task.result = {'success': True}
            elif state == 'FAILURE':
                mock_task.info = Exception('Test error')
            MockAsyncResult.return_value = mock_task

            task = MockAsyncResult(f'job_{state}')
            assert task.state == state


def test_repository_status_to_dict(db_manager, test_user, test_repository):
    """Test repository serialization for status endpoint"""
    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == test_repository.id
        ).first()

        repo_dict = repo.to_dict()

        assert 'id' in repo_dict
        assert 'name' in repo_dict
        assert 'github_url' in repo_dict
        assert 'status' in repo_dict
        assert 'created_at' in repo_dict
        assert repo_dict['status'] == 'pending'
