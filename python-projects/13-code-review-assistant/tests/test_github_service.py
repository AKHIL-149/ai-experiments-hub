"""Tests for GitHub service"""
import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from src.services.github_service import GitHubService


@pytest.fixture
def mock_github_token():
    """Mock GitHub token"""
    return "ghp_mock_token_12345"


@pytest.fixture
def mock_github_client():
    """Create mock GitHub client"""
    with patch('src.services.github_service.Github') as mock_github:
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"
        mock_user.avatar_url = "https://github.com/avatar.png"
        mock_user.html_url = "https://github.com/testuser"

        mock_client = Mock()
        mock_client.get_user.return_value = mock_user

        mock_github.return_value = mock_client

        yield mock_github, mock_client, mock_user


def test_github_service_initialization_with_token(mock_github_client):
    """Test GitHubService initialization with token"""
    mock_github, mock_client, mock_user = mock_github_client

    service = GitHubService(github_token="test_token")

    assert service.token == "test_token"
    assert service.user.login == "testuser"


def test_github_service_initialization_with_env_var(mock_github_client):
    """Test GitHubService initialization with env var"""
    mock_github, mock_client, mock_user = mock_github_client

    with patch.dict(os.environ, {'GITHUB_TOKEN': 'env_token'}):
        service = GitHubService()
        assert service.token == "env_token"


def test_github_service_initialization_no_token():
    """Test GitHubService initialization without token"""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="GitHub token is required"):
            GitHubService()


def test_github_service_initialization_invalid_token():
    """Test GitHubService initialization with invalid token"""
    with patch('src.services.github_service.Github') as mock_github:
        from github import BadCredentialsException

        mock_client = Mock()
        mock_user = Mock()
        # Make the login property access raise the exception
        type(mock_user).login = property(lambda self: (_ for _ in ()).throw(BadCredentialsException(401, "Bad credentials")))
        mock_client.get_user.return_value = mock_user
        mock_github.return_value = mock_client

        with pytest.raises(ValueError, match="Invalid GitHub token"):
            GitHubService(github_token="bad_token")


def test_parse_repo_url_https(mock_github_client):
    """Test parsing HTTPS repository URL"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    owner, repo = service._parse_repo_url("https://github.com/user/repo")
    assert owner == "user"
    assert repo == "repo"


def test_parse_repo_url_https_with_git(mock_github_client):
    """Test parsing HTTPS URL with .git"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    owner, repo = service._parse_repo_url("https://github.com/user/repo.git")
    assert owner == "user"
    assert repo == "repo"


def test_parse_repo_url_ssh(mock_github_client):
    """Test parsing SSH repository URL"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    owner, repo = service._parse_repo_url("git@github.com:user/repo.git")
    assert owner == "user"
    assert repo == "repo"


def test_parse_repo_url_invalid(mock_github_client):
    """Test parsing invalid URL"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    with pytest.raises(ValueError, match="Invalid GitHub URL format"):
        service._parse_repo_url("https://gitlab.com/user/repo")


def test_get_repository_success(mock_github_client):
    """Test getting repository successfully"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    mock_repo = Mock()
    mock_repo.name = "test-repo"
    mock_client.get_repo.return_value = mock_repo

    success, repo, error = service.get_repository("https://github.com/user/test-repo")

    assert success is True
    assert repo == mock_repo
    assert error is None
    mock_client.get_repo.assert_called_with("user/test-repo")


def test_get_repository_not_found(mock_github_client):
    """Test getting non-existent repository"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    from github import UnknownObjectException
    mock_client.get_repo.side_effect = UnknownObjectException(404, "Not Found")

    success, repo, error = service.get_repository("https://github.com/user/nonexistent")

    assert success is False
    assert repo is None
    assert "not found" in error.lower()


def test_get_pull_request_success(mock_github_client):
    """Test getting pull request successfully"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    mock_repo = Mock()
    mock_pr = Mock()
    mock_pr.number = 42
    mock_pr.title = "Test PR"

    mock_repo.get_pull.return_value = mock_pr
    mock_client.get_repo.return_value = mock_repo

    success, pr, error = service.get_pull_request("https://github.com/user/repo", 42)

    assert success is True
    assert pr == mock_pr
    assert error is None
    mock_repo.get_pull.assert_called_with(42)


def test_get_pull_request_not_found(mock_github_client):
    """Test getting non-existent pull request"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    from github import UnknownObjectException

    mock_repo = Mock()
    mock_repo.get_pull.side_effect = UnknownObjectException(404, "Not Found")
    mock_client.get_repo.return_value = mock_repo

    success, pr, error = service.get_pull_request("https://github.com/user/repo", 999)

    assert success is False
    assert pr is None
    assert "not found" in error.lower()


def test_get_pull_request_info(mock_github_client):
    """Test getting pull request information"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    from datetime import datetime

    mock_pr_user = Mock()
    mock_pr_user.login = "pr_author"
    mock_pr_user.avatar_url = "https://github.com/avatar.png"

    mock_head = Mock()
    mock_head.ref = "feature-branch"

    mock_base = Mock()
    mock_base.ref = "main"

    mock_pr = Mock()
    mock_pr.number = 42
    mock_pr.title = "Add new feature"
    mock_pr.body = "This PR adds a new feature"
    mock_pr.user = mock_pr_user
    mock_pr.state = "open"
    mock_pr.merged = False
    mock_pr.draft = False
    mock_pr.head = mock_head
    mock_pr.base = mock_base
    mock_pr.commits = 5
    mock_pr.additions = 100
    mock_pr.deletions = 50
    mock_pr.changed_files = 3
    mock_pr.created_at = datetime(2024, 1, 1, 12, 0, 0)
    mock_pr.updated_at = datetime(2024, 1, 2, 12, 0, 0)
    mock_pr.mergeable = True
    mock_pr.mergeable_state = "clean"
    mock_pr.id = 123456
    mock_pr.html_url = "https://github.com/user/repo/pull/42"

    mock_repo = Mock()
    mock_repo.get_pull.return_value = mock_pr
    mock_client.get_repo.return_value = mock_repo

    success, info, error = service.get_pull_request_info("https://github.com/user/repo", 42)

    assert success is True
    assert error is None
    assert info['number'] == 42
    assert info['title'] == "Add new feature"
    assert info['author'] == "pr_author"
    assert info['state'] == "open"
    assert info['source_branch'] == "feature-branch"
    assert info['target_branch'] == "main"
    assert info['commits_count'] == 5
    assert info['additions'] == 100
    assert info['deletions'] == 50


def test_get_pull_request_diff(mock_github_client):
    """Test getting pull request diff"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    mock_pr = Mock()
    mock_pr.diff_url = "https://github.com/user/repo/pull/42.diff"

    mock_repo = Mock()
    mock_repo.get_pull.return_value = mock_pr
    mock_client.get_repo.return_value = mock_repo

    diff_content = """diff --git a/file.py b/file.py
index 123..456 100644
--- a/file.py
+++ b/file.py
@@ -1 +1 @@
-old
+new
"""

    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.text = diff_content
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        success, diff, error = service.get_pull_request_diff("https://github.com/user/repo", 42)

        assert success is True
        assert error is None
        assert diff == diff_content


def test_get_pull_request_files(mock_github_client):
    """Test getting pull request files"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    mock_file1 = Mock()
    mock_file1.filename = "file1.py"
    mock_file1.status = "modified"
    mock_file1.additions = 10
    mock_file1.deletions = 5
    mock_file1.changes = 15
    mock_file1.patch = "+added line"
    mock_file1.blob_url = "https://github.com/blob/file1.py"
    mock_file1.raw_url = "https://raw.github.com/file1.py"

    mock_file2 = Mock()
    mock_file2.filename = "file2.py"
    mock_file2.status = "added"
    mock_file2.additions = 20
    mock_file2.deletions = 0
    mock_file2.changes = 20
    mock_file2.patch = "+new file"
    mock_file2.blob_url = "https://github.com/blob/file2.py"
    mock_file2.raw_url = "https://raw.github.com/file2.py"

    mock_pr = Mock()
    mock_pr.get_files.return_value = [mock_file1, mock_file2]

    mock_repo = Mock()
    mock_repo.get_pull.return_value = mock_pr
    mock_client.get_repo.return_value = mock_repo

    success, files, error = service.get_pull_request_files("https://github.com/user/repo", 42)

    assert success is True
    assert error is None
    assert len(files) == 2
    assert files[0]['filename'] == "file1.py"
    assert files[0]['status'] == "modified"
    assert files[1]['filename'] == "file2.py"
    assert files[1]['status'] == "added"


def test_post_review_comment(mock_github_client):
    """Test posting a review comment"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    mock_comment = Mock()
    mock_comment.id = 789

    mock_commit = Mock()

    mock_pr = Mock()
    mock_pr.commits = 1
    mock_pr.get_commits.return_value = [mock_commit]
    mock_pr.create_review_comment.return_value = mock_comment

    mock_repo = Mock()
    mock_repo.get_pull.return_value = mock_pr
    mock_client.get_repo.return_value = mock_repo

    success, comment_id, error = service.post_review_comment(
        "https://github.com/user/repo",
        42,
        "This needs improvement",
        "abc123",
        "file.py",
        10
    )

    assert success is True
    assert comment_id == 789
    assert error is None


def test_post_review(mock_github_client):
    """Test posting a review"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    mock_review = Mock()
    mock_review.id = 999

    mock_commit = Mock()

    mock_pr = Mock()
    mock_pr.commits = 1
    mock_pr.get_commits.return_value = [mock_commit]
    mock_pr.create_review.return_value = mock_review

    mock_repo = Mock()
    mock_repo.get_pull.return_value = mock_pr
    mock_client.get_repo.return_value = mock_repo

    comments = [
        {'path': 'file1.py', 'line': 10, 'body': 'Issue here'},
        {'path': 'file2.py', 'line': 20, 'body': 'Problem here'}
    ]

    success, review_id, error = service.post_review(
        "https://github.com/user/repo",
        42,
        "Overall looks good",
        "APPROVE",
        comments
    )

    assert success is True
    assert review_id == 999
    assert error is None


def test_post_review_invalid_event(mock_github_client):
    """Test posting review with invalid event"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    success, review_id, error = service.post_review(
        "https://github.com/user/repo",
        42,
        "Review",
        "INVALID_EVENT"
    )

    assert success is False
    assert review_id is None
    assert "Invalid event" in error


def test_check_repository_access(mock_github_client):
    """Test checking repository access"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    mock_repo = Mock()
    mock_repo.permissions = Mock()
    mock_client.get_repo.return_value = mock_repo

    has_access, error = service.check_repository_access("https://github.com/user/repo")

    assert has_access is True
    assert error is None


def test_get_authenticated_user(mock_github_client):
    """Test getting authenticated user info"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    user_info = service.get_authenticated_user()

    assert user_info['login'] == "testuser"
    assert user_info['name'] == "Test User"
    assert user_info['email'] == "test@example.com"


def test_close_connection(mock_github_client):
    """Test closing GitHub client connection"""
    mock_github, mock_client, mock_user = mock_github_client
    service = GitHubService(github_token="test_token")

    service.close()

    mock_client.close.assert_called_once()
