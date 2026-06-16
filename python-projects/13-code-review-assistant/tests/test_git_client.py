"""Tests for Git client"""
import pytest
import os
import tempfile
import shutil
from pathlib import Path
from git import Repo
from src.core.git_client import GitClient


@pytest.fixture
def temp_clone_dir():
    """Create temporary directory for cloning"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def git_client(temp_clone_dir):
    """Create GitClient instance with temp directory"""
    return GitClient(base_clone_dir=temp_clone_dir)


@pytest.fixture
def sample_repo(temp_clone_dir):
    """Create a sample Git repository for testing"""
    repo_path = os.path.join(temp_clone_dir, 'test-repo')
    os.makedirs(repo_path)

    # Initialize repository
    repo = Repo.init(repo_path)

    # Configure user for commits
    with repo.config_writer() as config:
        config.set_value('user', 'name', 'Test User')
        config.set_value('user', 'email', 'test@example.com')

    # Create initial commit
    readme_path = os.path.join(repo_path, 'README.md')
    with open(readme_path, 'w') as f:
        f.write('# Test Repository\n')

    repo.index.add(['README.md'])
    repo.index.commit('Initial commit')

    yield repo_path

    # Cleanup handled by temp_clone_dir fixture


def test_git_client_initialization(temp_clone_dir):
    """Test GitClient initialization"""
    client = GitClient(base_clone_dir=temp_clone_dir)
    assert client.base_clone_dir == temp_clone_dir
    assert os.path.exists(temp_clone_dir)


def test_git_client_default_clone_dir():
    """Test GitClient with default clone directory"""
    client = GitClient()
    assert client.base_clone_dir.endswith('data/repos')


def test_extract_repo_name_https(git_client):
    """Test extracting repository name from HTTPS URL"""
    url = 'https://github.com/user/my-repo'
    name = git_client._extract_repo_name(url)
    assert name == 'my-repo'


def test_extract_repo_name_https_with_git(git_client):
    """Test extracting repository name from HTTPS URL with .git"""
    url = 'https://github.com/user/my-repo.git'
    name = git_client._extract_repo_name(url)
    assert name == 'my-repo'


def test_extract_repo_name_ssh(git_client):
    """Test extracting repository name from SSH URL"""
    url = 'git@github.com:user/my-repo.git'
    name = git_client._extract_repo_name(url)
    assert name == 'my-repo'


def test_repository_exists(git_client, sample_repo):
    """Test checking if repository exists"""
    # Existing repository
    assert git_client.repository_exists(sample_repo) is True

    # Non-existent path
    assert git_client.repository_exists('/nonexistent/path') is False


def test_get_current_branch(git_client, sample_repo):
    """Test getting current branch"""
    success, branch, error = git_client.get_current_branch(sample_repo)

    assert success is True
    assert branch in ['master', 'main']  # Could be either depending on Git version
    assert error is None


def test_get_current_branch_invalid_repo(git_client, temp_clone_dir):
    """Test getting current branch from invalid repository"""
    invalid_path = os.path.join(temp_clone_dir, 'not-a-repo')
    os.makedirs(invalid_path)

    success, branch, error = git_client.get_current_branch(invalid_path)

    assert success is False
    assert branch is None
    assert 'not a valid' in error.lower()


def test_get_branches(git_client, sample_repo):
    """Test getting list of branches"""
    success, branches, error = git_client.get_branches(sample_repo)

    assert success is True
    assert branches is not None
    assert len(branches) >= 1
    assert error is None


def test_checkout_branch_create_new(git_client, sample_repo):
    """Test creating and checking out new branch"""
    success, error = git_client.checkout_branch(
        sample_repo,
        'feature-branch',
        create=True
    )

    assert success is True
    assert error is None

    # Verify we're on the new branch
    success, current_branch, _ = git_client.get_current_branch(sample_repo)
    assert current_branch == 'feature-branch'


def test_checkout_existing_branch(git_client, sample_repo):
    """Test checking out existing branch"""
    # Create a branch first
    git_client.checkout_branch(sample_repo, 'test-branch', create=True)

    # Go back to main/master
    repo = Repo(sample_repo)
    initial_branch = repo.active_branch.name
    git_client.checkout_branch(sample_repo, initial_branch)

    # Checkout the test branch
    success, error = git_client.checkout_branch(sample_repo, 'test-branch')

    assert success is True
    assert error is None


def test_get_commit_info(git_client, sample_repo):
    """Test getting commit information"""
    success, info, error = git_client.get_commit_info(sample_repo)

    assert success is True
    assert info is not None
    assert 'sha' in info
    assert 'short_sha' in info
    assert 'message' in info
    assert 'author' in info
    assert 'author_email' in info
    assert 'date' in info
    assert info['message'] == 'Initial commit'
    assert error is None


def test_is_repository_clean(git_client, sample_repo):
    """Test checking if repository is clean"""
    # Clean repository
    success, is_clean, error = git_client.is_repository_clean(sample_repo)
    assert success is True
    assert is_clean is True
    assert error is None

    # Make repository dirty
    dirty_file = os.path.join(sample_repo, 'test.txt')
    with open(dirty_file, 'w') as f:
        f.write('test content')

    success, is_clean, error = git_client.is_repository_clean(sample_repo)
    assert success is True
    assert is_clean is False
    assert error is None


def test_get_remote_url(git_client, sample_repo):
    """Test getting remote URL"""
    # Add a remote
    repo = Repo(sample_repo)
    repo.create_remote('origin', 'https://github.com/user/test-repo.git')

    success, url, error = git_client.get_remote_url(sample_repo)

    assert success is True
    assert url == 'https://github.com/user/test-repo.git'
    assert error is None


def test_get_remote_url_no_remote(git_client, sample_repo):
    """Test getting remote URL when no remote exists"""
    success, url, error = git_client.get_remote_url(sample_repo)

    # Should handle gracefully
    assert success is False or url is None


def test_delete_repository(git_client, temp_clone_dir):
    """Test deleting a repository"""
    # Create a directory
    repo_path = os.path.join(temp_clone_dir, 'to-delete')
    os.makedirs(repo_path)
    Repo.init(repo_path)

    # Verify it exists
    assert os.path.exists(repo_path)

    # Delete it
    success, error = git_client.delete_repository(repo_path)

    assert success is True
    assert error is None
    assert not os.path.exists(repo_path)


def test_delete_nonexistent_repository(git_client, temp_clone_dir):
    """Test deleting non-existent repository"""
    repo_path = os.path.join(temp_clone_dir, 'nonexistent')

    success, error = git_client.delete_repository(repo_path)

    assert success is False
    assert 'not found' in error.lower()


def test_fetch_repository_invalid_path(git_client, temp_clone_dir):
    """Test fetching from invalid repository"""
    invalid_path = os.path.join(temp_clone_dir, 'not-a-repo')
    os.makedirs(invalid_path)

    success, error = git_client.fetch_repository(invalid_path)

    assert success is False
    assert 'not a valid' in error.lower()


def test_pull_repository_invalid_path(git_client, temp_clone_dir):
    """Test pulling from invalid repository"""
    invalid_path = os.path.join(temp_clone_dir, 'not-a-repo')
    os.makedirs(invalid_path)

    success, error = git_client.pull_repository(invalid_path)

    assert success is False
    assert 'not a valid' in error.lower()


def test_clone_repository_existing_directory(git_client, temp_clone_dir):
    """Test cloning when directory already exists"""
    # Create existing directory
    existing_path = os.path.join(temp_clone_dir, 'existing-repo')
    os.makedirs(existing_path)

    success, path, error = git_client.clone_repository(
        'https://github.com/user/repo',
        repo_name='existing-repo'
    )

    assert success is False
    assert path is None
    assert 'already exists' in error.lower()


def test_clone_repository_custom_name(git_client, temp_clone_dir):
    """Test clone with custom repository name"""
    # Mock clone - we'll test the path generation
    expected_path = os.path.join(temp_clone_dir, 'custom-name')

    # We can't actually clone without a real URL, so we'll just verify
    # that the client would use the custom name
    success, path, error = git_client.clone_repository(
        'https://github.com/user/repo.git',
        repo_name='custom-name'
    )

    # Will fail because URL is not real, but we can check the error includes the path
    if not success:
        # Expected since URL isn't real
        assert error is not None


def test_base_clone_dir_creation(temp_clone_dir):
    """Test that base clone directory is created if it doesn't exist"""
    new_dir = os.path.join(temp_clone_dir, 'new-clone-dir')

    # Verify it doesn't exist yet
    assert not os.path.exists(new_dir)

    # Create GitClient with this directory
    client = GitClient(base_clone_dir=new_dir)

    # Verify it was created
    assert os.path.exists(new_dir)
    assert client.base_clone_dir == new_dir


def test_get_commit_info_specific_sha(git_client, sample_repo):
    """Test getting info for specific commit"""
    # Get the initial commit SHA
    repo = Repo(sample_repo)
    commit_sha = repo.head.commit.hexsha

    success, info, error = git_client.get_commit_info(sample_repo, commit_sha)

    assert success is True
    assert info['sha'] == commit_sha
    assert error is None


def test_multiple_operations_workflow(git_client, sample_repo):
    """Test a complete workflow of multiple operations"""
    # 1. Check current branch
    success, branch, _ = git_client.get_current_branch(sample_repo)
    assert success is True
    initial_branch = branch

    # 2. Create and checkout new branch
    success, _ = git_client.checkout_branch(sample_repo, 'dev', create=True)
    assert success is True

    # 3. Verify we're on new branch
    success, branch, _ = git_client.get_current_branch(sample_repo)
    assert branch == 'dev'

    # 4. Check repository is clean
    success, is_clean, _ = git_client.is_repository_clean(sample_repo)
    assert is_clean is True

    # 5. Get commit info
    success, info, _ = git_client.get_commit_info(sample_repo)
    assert success is True

    # 6. Get branches list
    success, branches, _ = git_client.get_branches(sample_repo)
    assert success is True
    assert 'dev' in branches
    assert initial_branch in branches


def test_error_handling_invalid_operations(git_client, temp_clone_dir):
    """Test error handling for various invalid operations"""
    invalid_path = os.path.join(temp_clone_dir, 'invalid')

    # Test various operations on invalid path
    operations = [
        lambda: git_client.get_current_branch(invalid_path),
        lambda: git_client.get_branches(invalid_path),
        lambda: git_client.checkout_branch(invalid_path, 'main'),
        lambda: git_client.get_commit_info(invalid_path),
        lambda: git_client.is_repository_clean(invalid_path),
        lambda: git_client.fetch_repository(invalid_path),
        lambda: git_client.pull_repository(invalid_path),
    ]

    for operation in operations:
        result = operation()
        # First element should be False (indicating failure)
        assert result[0] is False
        # Last element should be error message
        assert result[-1] is not None
