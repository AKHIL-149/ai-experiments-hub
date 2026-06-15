"""Service for managing repositories"""
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from src.core.database import Repository, RepositoryStatus, User


class RepositoryService:
    """Service for repository operations with business logic"""

    # GitHub URL patterns
    HTTPS_PATTERN = r'^https://github\.com/[\w\-\.]+/[\w\-\.]+/?$'
    SSH_PATTERN = r'^git@github\.com:[\w\-\.]+/[\w\-\.]+\.git$'

    def __init__(self, db: Session):
        """
        Initialize repository service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def validate_github_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate GitHub URL format.

        Args:
            url: GitHub repository URL

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url:
            return False, "GitHub URL is required"

        # Remove trailing slashes and .git
        normalized_url = url.rstrip('/').rstrip('.git')

        # Check HTTPS format
        if url.startswith('https://github.com/'):
            if re.match(self.HTTPS_PATTERN, normalized_url + '/'):
                return True, None
            return False, "Invalid GitHub HTTPS URL format. Expected: https://github.com/user/repo"

        # Check SSH format
        if url.startswith('git@github.com:'):
            if re.match(self.SSH_PATTERN, url):
                return True, None
            return False, "Invalid GitHub SSH URL format. Expected: git@github.com:user/repo.git"

        return False, "URL must start with https://github.com/ or git@github.com:"

    def extract_repo_info(self, github_url: str) -> Dict[str, str]:
        """
        Extract repository information from GitHub URL.

        Args:
            github_url: GitHub repository URL

        Returns:
            Dictionary with owner, repo, and name
        """
        # Normalize URL
        url = github_url.rstrip('/').rstrip('.git')

        # Extract from HTTPS URL
        if url.startswith('https://github.com/'):
            parts = url.replace('https://github.com/', '').split('/')
            if len(parts) >= 2:
                return {
                    'owner': parts[0],
                    'repo': parts[1],
                    'name': parts[1]
                }

        # Extract from SSH URL
        if url.startswith('git@github.com:'):
            parts = url.replace('git@github.com:', '').replace('.git', '').split('/')
            if len(parts) >= 2:
                return {
                    'owner': parts[0],
                    'repo': parts[1],
                    'name': parts[1]
                }

        # Fallback
        parts = url.split('/')
        return {
            'owner': 'unknown',
            'repo': parts[-1] if parts else 'unknown',
            'name': parts[-1] if parts else 'unknown'
        }

    def create_repository(
        self,
        user_id: str,
        github_url: str,
        name: Optional[str] = None,
        default_branch: str = 'main'
    ) -> Tuple[bool, Optional[Repository], Optional[str]]:
        """
        Create a new repository.

        Args:
            user_id: User ID who owns the repository
            github_url: GitHub repository URL
            name: Optional custom name (defaults to extracted from URL)
            default_branch: Default branch name

        Returns:
            Tuple of (success, repository, error_message)
        """
        # Validate GitHub URL
        is_valid, error = self.validate_github_url(github_url)
        if not is_valid:
            return False, None, error

        # Extract repo info
        repo_info = self.extract_repo_info(github_url)

        # Use provided name or extracted name
        repo_name = name or repo_info['name']

        # Check for duplicate URL for this user
        existing = self.db.query(Repository).filter(
            Repository.user_id == user_id,
            Repository.github_url == github_url
        ).first()

        if existing:
            return False, None, "Repository with this GitHub URL already exists"

        # Create repository
        repository = Repository(
            user_id=user_id,
            name=repo_name,
            github_url=github_url,
            default_branch=default_branch,
            status=RepositoryStatus.PENDING
        )

        self.db.add(repository)
        self.db.commit()
        self.db.refresh(repository)

        return True, repository, None

    def get_repository(
        self,
        repository_id: str,
        user_id: str
    ) -> Optional[Repository]:
        """
        Get repository by ID for specific user.

        Args:
            repository_id: Repository ID
            user_id: User ID (for ownership verification)

        Returns:
            Repository or None if not found
        """
        return self.db.query(Repository).filter(
            Repository.id == repository_id,
            Repository.user_id == user_id
        ).first()

    def list_repositories(
        self,
        user_id: str,
        status: Optional[RepositoryStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Repository]:
        """
        List repositories for a user.

        Args:
            user_id: User ID
            status: Optional filter by status
            limit: Maximum number of repositories to return
            offset: Number of repositories to skip

        Returns:
            List of repositories
        """
        query = self.db.query(Repository).filter(
            Repository.user_id == user_id
        )

        if status:
            query = query.filter(Repository.status == status)

        return query.order_by(
            Repository.created_at.desc()
        ).limit(limit).offset(offset).all()

    def update_repository(
        self,
        repository_id: str,
        user_id: str,
        name: Optional[str] = None,
        default_branch: Optional[str] = None,
        settings: Optional[Dict] = None
    ) -> Tuple[bool, Optional[Repository], Optional[str]]:
        """
        Update repository fields.

        Args:
            repository_id: Repository ID
            user_id: User ID (for ownership verification)
            name: Optional new name
            default_branch: Optional new default branch
            settings: Optional settings dictionary

        Returns:
            Tuple of (success, repository, error_message)
        """
        repository = self.get_repository(repository_id, user_id)

        if not repository:
            return False, None, "Repository not found"

        # Update fields if provided
        if name is not None:
            repository.name = name

        if default_branch is not None:
            repository.default_branch = default_branch

        if settings is not None:
            repository.settings_json = settings

        self.db.commit()
        self.db.refresh(repository)

        return True, repository, None

    def update_status(
        self,
        repository_id: str,
        status: RepositoryStatus,
        error_message: Optional[str] = None
    ) -> Tuple[bool, Optional[Repository], Optional[str]]:
        """
        Update repository status.

        Args:
            repository_id: Repository ID
            status: New status
            error_message: Optional error message if status is ERROR

        Returns:
            Tuple of (success, repository, error_message)
        """
        repository = self.db.query(Repository).filter(
            Repository.id == repository_id
        ).first()

        if not repository:
            return False, None, "Repository not found"

        repository.status = status

        # Store error message in settings if provided
        if status == RepositoryStatus.ERROR and error_message:
            current_settings = repository.settings_json or {}
            current_settings['last_error'] = error_message
            current_settings['error_at'] = datetime.utcnow().isoformat()
            repository.settings_json = current_settings

        self.db.commit()
        self.db.refresh(repository)

        return True, repository, None

    def mark_as_ready(
        self,
        repository_id: str,
        clone_path: Optional[str] = None
    ) -> Tuple[bool, Optional[Repository], Optional[str]]:
        """
        Mark repository as ready after successful cloning.

        Args:
            repository_id: Repository ID
            clone_path: Optional path where repository was cloned

        Returns:
            Tuple of (success, repository, error_message)
        """
        repository = self.db.query(Repository).filter(
            Repository.id == repository_id
        ).first()

        if not repository:
            return False, None, "Repository not found"

        repository.status = RepositoryStatus.READY
        repository.last_synced_at = datetime.utcnow()

        if clone_path:
            repository.clone_path = clone_path

        self.db.commit()
        self.db.refresh(repository)

        return True, repository, None

    def mark_as_cloning(
        self,
        repository_id: str
    ) -> Tuple[bool, Optional[Repository], Optional[str]]:
        """
        Mark repository as cloning.

        Args:
            repository_id: Repository ID

        Returns:
            Tuple of (success, repository, error_message)
        """
        return self.update_status(repository_id, RepositoryStatus.CLONING)

    def mark_as_error(
        self,
        repository_id: str,
        error_message: str
    ) -> Tuple[bool, Optional[Repository], Optional[str]]:
        """
        Mark repository as error.

        Args:
            repository_id: Repository ID
            error_message: Error description

        Returns:
            Tuple of (success, repository, error_message)
        """
        return self.update_status(repository_id, RepositoryStatus.ERROR, error_message)

    def delete_repository(
        self,
        repository_id: str,
        user_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Delete repository and all associated data.

        Args:
            repository_id: Repository ID
            user_id: User ID (for ownership verification)

        Returns:
            Tuple of (success, error_message)
        """
        repository = self.get_repository(repository_id, user_id)

        if not repository:
            return False, "Repository not found"

        repo_name = repository.name

        # Delete will cascade to related records
        self.db.delete(repository)
        self.db.commit()

        return True, None

    def get_repository_stats(
        self,
        repository_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get repository statistics.

        Args:
            repository_id: Repository ID
            user_id: User ID (for ownership verification)

        Returns:
            Dictionary with repository stats or None
        """
        repository = self.get_repository(repository_id, user_id)

        if not repository:
            return None

        # Count related records
        pr_count = len(repository.pull_requests) if repository.pull_requests else 0

        # Count issues from pull requests
        total_issues = 0
        for pr in repository.pull_requests or []:
            for code_file in pr.code_files or []:
                total_issues += len(code_file.issues or [])

        return {
            'repository_id': repository.id,
            'name': repository.name,
            'status': repository.status.value,
            'pull_requests_count': pr_count,
            'total_issues': total_issues,
            'last_synced_at': repository.last_synced_at.isoformat() if repository.last_synced_at else None,
            'created_at': repository.created_at.isoformat() if repository.created_at else None
        }

    def count_repositories(
        self,
        user_id: str,
        status: Optional[RepositoryStatus] = None
    ) -> int:
        """
        Count repositories for a user.

        Args:
            user_id: User ID
            status: Optional filter by status

        Returns:
            Number of repositories
        """
        query = self.db.query(Repository).filter(
            Repository.user_id == user_id
        )

        if status:
            query = query.filter(Repository.status == status)

        return query.count()
