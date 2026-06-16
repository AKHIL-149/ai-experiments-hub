"""
Service for managing pull requests
"""

from typing import Optional, Tuple, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from src.core.database import PullRequest, Repository, PRStatus
from src.services.github_service import GitHubService


class PullRequestService:
    """Service for managing pull requests."""

    def __init__(self, db: Session):
        """
        Initialize PR service.

        Args:
            db: Database session
        """
        self.db = db

    def import_from_github(
        self,
        repository_id: str,
        pr_number: int,
        github_token: str
    ) -> Tuple[bool, Optional[PullRequest], Optional[str]]:
        """
        Import a pull request from GitHub.

        Args:
            repository_id: Repository ID
            pr_number: PR number
            github_token: GitHub personal access token

        Returns:
            Tuple of (success, pull_request, error_message)
        """
        try:
            # Get repository
            repository = self.db.query(Repository).filter(
                Repository.id == repository_id
            ).first()

            if not repository:
                return False, None, "Repository not found"

            # Check if PR already exists
            existing_pr = self.db.query(PullRequest).filter(
                PullRequest.repository_id == repository_id,
                PullRequest.pr_number == pr_number
            ).first()

            if existing_pr:
                # Update existing PR
                return self._update_from_github(existing_pr, github_token)

            # Fetch PR from GitHub
            github_service = GitHubService(github_token=github_token)
            success, pr_info, error = github_service.get_pull_request_info(
                repository.github_url,
                pr_number
            )
            github_service.close()

            if not success:
                return False, None, error

            # Create PR record
            pr = PullRequest(
                repository_id=repository_id,
                pr_number=pr_info['number'],
                title=pr_info['title'],
                description=pr_info['description'],
                author=pr_info['author'],
                author_avatar=pr_info.get('author_avatar'),
                status=self._map_github_status(pr_info['state'], pr_info['is_merged']),
                source_branch=pr_info['source_branch'],
                target_branch=pr_info['target_branch'],
                github_id=str(pr_info['github_id']),
                github_url=pr_info['html_url'],
                is_draft=pr_info.get('is_draft', False),
                is_merged=pr_info['is_merged'],
                commits_count=pr_info.get('commits_count', 0),
                additions=pr_info.get('additions', 0),
                deletions=pr_info.get('deletions', 0),
                changed_files=pr_info.get('changed_files', 0),
                mergeable=pr_info.get('mergeable'),
                mergeable_state=pr_info.get('mergeable_state'),
                updated_at=datetime.fromisoformat(pr_info['updated_at'])
            )

            self.db.add(pr)
            self.db.commit()
            self.db.refresh(pr)

            return True, pr, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to import PR: {str(e)}"

    def _update_from_github(
        self,
        pr: PullRequest,
        github_token: str
    ) -> Tuple[bool, Optional[PullRequest], Optional[str]]:
        """
        Update existing PR from GitHub.

        Args:
            pr: Existing PR record
            github_token: GitHub personal access token

        Returns:
            Tuple of (success, pull_request, error_message)
        """
        try:
            # Get repository
            repository = self.db.query(Repository).filter(
                Repository.id == pr.repository_id
            ).first()

            if not repository:
                return False, None, "Repository not found"

            # Fetch latest PR info from GitHub
            github_service = GitHubService(github_token=github_token)
            success, pr_info, error = github_service.get_pull_request_info(
                repository.github_url,
                pr.pr_number
            )
            github_service.close()

            if not success:
                return False, None, error

            # Update PR fields
            pr.title = pr_info['title']
            pr.description = pr_info['description']
            pr.status = self._map_github_status(pr_info['state'], pr_info['is_merged'])
            pr.is_draft = pr_info.get('is_draft', False)
            pr.is_merged = pr_info['is_merged']
            pr.commits_count = pr_info.get('commits_count', 0)
            pr.additions = pr_info.get('additions', 0)
            pr.deletions = pr_info.get('deletions', 0)
            pr.changed_files = pr_info.get('changed_files', 0)
            pr.mergeable = pr_info.get('mergeable')
            pr.mergeable_state = pr_info.get('mergeable_state')
            pr.updated_at = datetime.fromisoformat(pr_info['updated_at'])

            self.db.commit()
            self.db.refresh(pr)

            return True, pr, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to update PR: {str(e)}"

    def get_pr(
        self,
        pr_id: str,
        user_id: Optional[str] = None
    ) -> Tuple[bool, Optional[PullRequest], Optional[str]]:
        """
        Get pull request by ID.

        Args:
            pr_id: PR ID
            user_id: Optional user ID for authorization

        Returns:
            Tuple of (success, pull_request, error_message)
        """
        try:
            query = self.db.query(PullRequest).filter(PullRequest.id == pr_id)

            # If user_id provided, ensure user owns the repository
            if user_id:
                query = query.join(Repository).filter(Repository.user_id == user_id)

            pr = query.first()

            if not pr:
                return False, None, "Pull request not found"

            return True, pr, None

        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def get_pr_by_number(
        self,
        repository_id: str,
        pr_number: int
    ) -> Tuple[bool, Optional[PullRequest], Optional[str]]:
        """
        Get pull request by repository and PR number.

        Args:
            repository_id: Repository ID
            pr_number: PR number

        Returns:
            Tuple of (success, pull_request, error_message)
        """
        try:
            pr = self.db.query(PullRequest).filter(
                PullRequest.repository_id == repository_id,
                PullRequest.pr_number == pr_number
            ).first()

            if not pr:
                return False, None, f"PR #{pr_number} not found in repository"

            return True, pr, None

        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def list_prs(
        self,
        repository_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[PRStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[bool, list, Optional[str]]:
        """
        List pull requests with filters.

        Args:
            repository_id: Filter by repository
            user_id: Filter by user's repositories
            status: Filter by PR status
            limit: Max results
            offset: Results offset

        Returns:
            Tuple of (success, pr_list, error_message)
        """
        try:
            query = self.db.query(PullRequest)

            if repository_id:
                query = query.filter(PullRequest.repository_id == repository_id)

            if user_id:
                query = query.join(Repository).filter(Repository.user_id == user_id)

            if status:
                query = query.filter(PullRequest.status == status)

            # Order by created date descending
            query = query.order_by(PullRequest.created_at.desc())

            # Apply pagination
            prs = query.limit(limit).offset(offset).all()

            return True, prs, None

        except Exception as e:
            return False, [], f"Error: {str(e)}"

    def update_status(
        self,
        pr_id: str,
        status: PRStatus
    ) -> Tuple[bool, Optional[str]]:
        """
        Update PR status.

        Args:
            pr_id: PR ID
            status: New status

        Returns:
            Tuple of (success, error_message)
        """
        try:
            pr = self.db.query(PullRequest).filter(PullRequest.id == pr_id).first()

            if not pr:
                return False, "Pull request not found"

            pr.status = status

            # Update reviewed_at if status is REVIEWED
            if status == PRStatus.REVIEWED:
                pr.reviewed_at = datetime.utcnow()

            self.db.commit()

            return True, None

        except Exception as e:
            self.db.rollback()
            return False, f"Error: {str(e)}"

    def delete_pr(
        self,
        pr_id: str,
        user_id: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Delete a pull request.

        Args:
            pr_id: PR ID
            user_id: Optional user ID for authorization

        Returns:
            Tuple of (success, error_message)
        """
        try:
            query = self.db.query(PullRequest).filter(PullRequest.id == pr_id)

            # If user_id provided, ensure user owns the repository
            if user_id:
                query = query.join(Repository).filter(Repository.user_id == user_id)

            pr = query.first()

            if not pr:
                return False, "Pull request not found"

            self.db.delete(pr)
            self.db.commit()

            return True, None

        except Exception as e:
            self.db.rollback()
            return False, f"Error: {str(e)}"

    def _map_github_status(self, state: str, is_merged: bool) -> PRStatus:
        """
        Map GitHub PR state to our PRStatus enum.

        Args:
            state: GitHub state (open/closed)
            is_merged: Whether PR is merged

        Returns:
            PRStatus enum value
        """
        if is_merged:
            return PRStatus.MERGED
        elif state.lower() == 'open':
            return PRStatus.OPEN
        else:
            return PRStatus.CLOSED
