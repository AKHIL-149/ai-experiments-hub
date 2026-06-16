"""
Git client for repository operations using GitPython
"""

import os
import shutil
from typing import Optional, Tuple, List, Dict
from pathlib import Path
import git
from git import Repo, GitCommandError, InvalidGitRepositoryError, NoSuchPathError


class GitClient:
    """
    Git client wrapper for repository operations.

    Provides high-level interface for:
    - Cloning repositories
    - Fetching updates
    - Pulling changes
    - Getting branch information
    - Checking repository status
    """

    def __init__(self, base_clone_dir: Optional[str] = None):
        """
        Initialize Git client.

        Args:
            base_clone_dir: Base directory for cloning repositories.
                          Defaults to ./data/repos
        """
        self.base_clone_dir = base_clone_dir or os.path.join(
            os.getcwd(), 'data', 'repos'
        )

        # Create base directory if it doesn't exist
        os.makedirs(self.base_clone_dir, exist_ok=True)

    def clone_repository(
        self,
        repo_url: str,
        repo_name: Optional[str] = None,
        branch: Optional[str] = None,
        depth: Optional[int] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Clone a Git repository.

        Args:
            repo_url: GitHub repository URL (HTTPS or SSH)
            repo_name: Custom name for the cloned directory
            branch: Specific branch to clone (default: repository's default branch)
            depth: Clone depth for shallow clone (None for full clone)

        Returns:
            Tuple of (success, clone_path, error_message)
        """
        try:
            # Extract repository name from URL if not provided
            if not repo_name:
                repo_name = self._extract_repo_name(repo_url)

            # Determine clone path
            clone_path = os.path.join(self.base_clone_dir, repo_name)

            # Check if directory already exists
            if os.path.exists(clone_path):
                return False, None, f"Directory already exists: {clone_path}"

            # Prepare clone arguments
            clone_kwargs = {}
            if branch:
                clone_kwargs['branch'] = branch
            if depth:
                clone_kwargs['depth'] = depth

            # Clone repository
            Repo.clone_from(repo_url, clone_path, **clone_kwargs)

            return True, clone_path, None

        except GitCommandError as e:
            return False, None, f"Git command failed: {str(e)}"
        except Exception as e:
            return False, None, f"Clone failed: {str(e)}"

    def fetch_repository(
        self,
        repo_path: str,
        remote: str = 'origin'
    ) -> Tuple[bool, Optional[str]]:
        """
        Fetch updates from remote repository.

        Args:
            repo_path: Local path to the repository
            remote: Remote name (default: 'origin')

        Returns:
            Tuple of (success, error_message)
        """
        try:
            repo = self._get_repo(repo_path)

            # Get remote
            remote_obj = repo.remote(remote)

            # Fetch updates
            remote_obj.fetch()

            return True, None

        except InvalidGitRepositoryError:
            return False, f"Not a valid Git repository: {repo_path}"
        except GitCommandError as e:
            return False, f"Fetch failed: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def pull_repository(
        self,
        repo_path: str,
        remote: str = 'origin',
        branch: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Pull updates from remote repository.

        Args:
            repo_path: Local path to the repository
            remote: Remote name (default: 'origin')
            branch: Branch to pull (default: current branch)

        Returns:
            Tuple of (success, error_message)
        """
        try:
            repo = self._get_repo(repo_path)

            # Get remote
            remote_obj = repo.remote(remote)

            # Pull updates
            if branch:
                remote_obj.pull(branch)
            else:
                remote_obj.pull()

            return True, None

        except InvalidGitRepositoryError:
            return False, f"Not a valid Git repository: {repo_path}"
        except GitCommandError as e:
            return False, f"Pull failed: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def get_branches(
        self,
        repo_path: str,
        remote: bool = False
    ) -> Tuple[bool, Optional[List[str]], Optional[str]]:
        """
        Get list of branches in the repository.

        Args:
            repo_path: Local path to the repository
            remote: If True, return remote branches; if False, return local branches

        Returns:
            Tuple of (success, branch_list, error_message)
        """
        try:
            repo = self._get_repo(repo_path)

            if remote:
                # Get remote branches
                branches = [
                    ref.name.replace('origin/', '')
                    for ref in repo.remote().refs
                    if not ref.name.endswith('/HEAD')
                ]
            else:
                # Get local branches
                branches = [head.name for head in repo.heads]

            return True, branches, None

        except InvalidGitRepositoryError:
            return False, None, f"Not a valid Git repository: {repo_path}"
        except Exception as e:
            return False, None, f"Error getting branches: {str(e)}"

    def get_current_branch(
        self,
        repo_path: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Get the current active branch.

        Args:
            repo_path: Local path to the repository

        Returns:
            Tuple of (success, branch_name, error_message)
        """
        try:
            repo = self._get_repo(repo_path)

            if repo.head.is_detached:
                return True, None, "HEAD is detached"

            current_branch = repo.active_branch.name
            return True, current_branch, None

        except InvalidGitRepositoryError:
            return False, None, f"Not a valid Git repository: {repo_path}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def checkout_branch(
        self,
        repo_path: str,
        branch: str,
        create: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Checkout a branch.

        Args:
            repo_path: Local path to the repository
            branch: Branch name to checkout
            create: If True, create the branch if it doesn't exist

        Returns:
            Tuple of (success, error_message)
        """
        try:
            repo = self._get_repo(repo_path)

            if create and branch not in [head.name for head in repo.heads]:
                # Create new branch
                repo.git.checkout('-b', branch)
            else:
                # Checkout existing branch
                repo.git.checkout(branch)

            return True, None

        except InvalidGitRepositoryError:
            return False, f"Not a valid Git repository: {repo_path}"
        except GitCommandError as e:
            return False, f"Checkout failed: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def get_commit_info(
        self,
        repo_path: str,
        commit_sha: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Get information about a commit.

        Args:
            repo_path: Local path to the repository
            commit_sha: Commit SHA (default: HEAD)

        Returns:
            Tuple of (success, commit_info_dict, error_message)
        """
        try:
            repo = self._get_repo(repo_path)

            # Get commit
            if commit_sha:
                commit = repo.commit(commit_sha)
            else:
                commit = repo.head.commit

            # Build commit info
            info = {
                'sha': commit.hexsha,
                'short_sha': commit.hexsha[:7],
                'message': commit.message.strip(),
                'author': commit.author.name,
                'author_email': commit.author.email,
                'date': commit.committed_datetime.isoformat(),
                'parents': [p.hexsha for p in commit.parents]
            }

            return True, info, None

        except InvalidGitRepositoryError:
            return False, None, f"Not a valid Git repository: {repo_path}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def is_repository_clean(
        self,
        repo_path: str
    ) -> Tuple[bool, Optional[bool], Optional[str]]:
        """
        Check if repository has uncommitted changes.

        Args:
            repo_path: Local path to the repository

        Returns:
            Tuple of (success, is_clean, error_message)
        """
        try:
            repo = self._get_repo(repo_path)
            is_clean = not repo.is_dirty(untracked_files=True)
            return True, is_clean, None

        except InvalidGitRepositoryError:
            return False, None, f"Not a valid Git repository: {repo_path}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def get_remote_url(
        self,
        repo_path: str,
        remote: str = 'origin'
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Get remote URL.

        Args:
            repo_path: Local path to the repository
            remote: Remote name (default: 'origin')

        Returns:
            Tuple of (success, remote_url, error_message)
        """
        try:
            repo = self._get_repo(repo_path)
            remote_obj = repo.remote(remote)
            url = list(remote_obj.urls)[0] if remote_obj.urls else None
            return True, url, None

        except InvalidGitRepositoryError:
            return False, None, f"Not a valid Git repository: {repo_path}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def delete_repository(
        self,
        repo_path: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Delete a cloned repository.

        Args:
            repo_path: Local path to the repository

        Returns:
            Tuple of (success, error_message)
        """
        try:
            if not os.path.exists(repo_path):
                return False, f"Repository not found: {repo_path}"

            # Remove directory
            shutil.rmtree(repo_path)
            return True, None

        except Exception as e:
            return False, f"Delete failed: {str(e)}"

    def repository_exists(
        self,
        repo_path: str
    ) -> bool:
        """
        Check if repository exists at the given path.

        Args:
            repo_path: Local path to check

        Returns:
            True if valid repository exists, False otherwise
        """
        try:
            self._get_repo(repo_path)
            return True
        except (InvalidGitRepositoryError, NoSuchPathError):
            return False

    def _get_repo(self, repo_path: str) -> Repo:
        """
        Get Repo object for the given path.

        Args:
            repo_path: Local path to the repository

        Returns:
            Repo object

        Raises:
            InvalidGitRepositoryError: If path is not a valid Git repository
            NoSuchPathError: If path doesn't exist
        """
        return Repo(repo_path)

    def _extract_repo_name(self, repo_url: str) -> str:
        """
        Extract repository name from GitHub URL.

        Args:
            repo_url: GitHub repository URL

        Returns:
            Repository name
        """
        # Remove trailing slashes and .git
        url = repo_url.rstrip('/').rstrip('.git')

        # Extract name from URL
        # Handle both HTTPS and SSH URLs
        if 'github.com/' in url:
            # HTTPS: https://github.com/user/repo
            parts = url.split('github.com/')[-1].split('/')
        elif 'github.com:' in url:
            # SSH: git@github.com:user/repo
            parts = url.split('github.com:')[-1].split('/')
        else:
            # Fallback: use last part
            parts = url.split('/')

        # Return last part as repo name
        return parts[-1] if parts else 'repository'
