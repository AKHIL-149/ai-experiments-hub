"""
GitHub API service for repository and pull request operations
"""

import os
from typing import Optional, List, Dict, Any, Tuple
from github import Github, GithubException, Auth
from github.Repository import Repository
from github.PullRequest import PullRequest as GithubPR
from github.PullRequestComment import PullRequestComment
from github.GithubException import UnknownObjectException, BadCredentialsException


class GitHubService:
    """
    Service for interacting with GitHub API using PyGithub.

    Provides high-level interface for:
    - Repository access
    - Pull request fetching
    - Diff retrieval
    - Review comment posting
    """

    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize GitHub service.

        Args:
            github_token: GitHub personal access token.
                        If not provided, will check GITHUB_TOKEN env var.
        """
        self.token = github_token or os.getenv('GITHUB_TOKEN')

        if not self.token:
            raise ValueError(
                "GitHub token is required. Provide it via constructor or GITHUB_TOKEN env var."
            )

        # Initialize GitHub client
        auth = Auth.Token(self.token)
        self.client = Github(auth=auth)

        # Verify authentication
        try:
            self.user = self.client.get_user()
            self.user.login  # Force API call to verify token
        except BadCredentialsException:
            raise ValueError("Invalid GitHub token")
        except Exception as e:
            raise ValueError(f"Failed to authenticate with GitHub: {str(e)}")

    def get_repository(
        self,
        repo_url: str
    ) -> Tuple[bool, Optional[Repository], Optional[str]]:
        """
        Get repository from GitHub URL.

        Args:
            repo_url: GitHub repository URL (e.g., https://github.com/user/repo)

        Returns:
            Tuple of (success, repository_object, error_message)
        """
        try:
            # Extract owner and repo name from URL
            owner, repo_name = self._parse_repo_url(repo_url)

            # Get repository
            repo = self.client.get_repo(f"{owner}/{repo_name}")

            return True, repo, None

        except UnknownObjectException:
            return False, None, f"Repository not found: {repo_url}"
        except GithubException as e:
            return False, None, f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def get_pull_request(
        self,
        repo_url: str,
        pr_number: int
    ) -> Tuple[bool, Optional[GithubPR], Optional[str]]:
        """
        Get pull request from repository.

        Args:
            repo_url: GitHub repository URL
            pr_number: Pull request number

        Returns:
            Tuple of (success, pull_request_object, error_message)
        """
        try:
            # Get repository
            success, repo, error = self.get_repository(repo_url)
            if not success:
                return False, None, error

            # Get pull request
            pr = repo.get_pull(pr_number)

            return True, pr, None

        except UnknownObjectException:
            return False, None, f"Pull request #{pr_number} not found"
        except GithubException as e:
            return False, None, f"GitHub API error: {e.data.get('message', str(e))}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def get_pull_request_info(
        self,
        repo_url: str,
        pr_number: int
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get detailed pull request information.

        Args:
            repo_url: GitHub repository URL
            pr_number: Pull request number

        Returns:
            Tuple of (success, pr_info_dict, error_message)
        """
        try:
            # Get pull request
            success, pr, error = self.get_pull_request(repo_url, pr_number)
            if not success:
                return False, None, error

            # Build info dict
            info = {
                'number': pr.number,
                'title': pr.title,
                'description': pr.body or "",
                'author': pr.user.login,
                'author_avatar': pr.user.avatar_url,
                'state': pr.state,
                'is_merged': pr.merged,
                'is_draft': pr.draft,
                'source_branch': pr.head.ref,
                'target_branch': pr.base.ref,
                'commits_count': pr.commits,
                'additions': pr.additions,
                'deletions': pr.deletions,
                'changed_files': pr.changed_files,
                'created_at': pr.created_at.isoformat(),
                'updated_at': pr.updated_at.isoformat(),
                'mergeable': pr.mergeable,
                'mergeable_state': pr.mergeable_state,
                'github_id': pr.id,
                'html_url': pr.html_url
            }

            return True, info, None

        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def get_pull_request_diff(
        self,
        repo_url: str,
        pr_number: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Get unified diff for a pull request.

        Args:
            repo_url: GitHub repository URL
            pr_number: Pull request number

        Returns:
            Tuple of (success, diff_text, error_message)
        """
        try:
            # Get pull request
            success, pr, error = self.get_pull_request(repo_url, pr_number)
            if not success:
                return False, None, error

            # Get diff
            # Note: PyGithub doesn't have a direct method for getting diff
            # We need to use raw API call
            diff_url = pr.diff_url

            # Make raw request to get diff
            import requests
            headers = {
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github.v3.diff'
            }

            response = requests.get(diff_url, headers=headers)
            response.raise_for_status()

            diff_text = response.text

            return True, diff_text, None

        except requests.RequestException as e:
            return False, None, f"Failed to fetch diff: {str(e)}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def get_pull_request_files(
        self,
        repo_url: str,
        pr_number: int
    ) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Get list of files changed in a pull request.

        Args:
            repo_url: GitHub repository URL
            pr_number: Pull request number

        Returns:
            Tuple of (success, files_list, error_message)
        """
        try:
            # Get pull request
            success, pr, error = self.get_pull_request(repo_url, pr_number)
            if not success:
                return False, None, error

            # Get files
            files = []
            for file in pr.get_files():
                files.append({
                    'filename': file.filename,
                    'status': file.status,  # added, removed, modified, renamed
                    'additions': file.additions,
                    'deletions': file.deletions,
                    'changes': file.changes,
                    'patch': file.patch if hasattr(file, 'patch') else None,
                    'blob_url': file.blob_url,
                    'raw_url': file.raw_url,
                    'previous_filename': file.previous_filename if hasattr(file, 'previous_filename') else None
                })

            return True, files, None

        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def post_review_comment(
        self,
        repo_url: str,
        pr_number: int,
        comment_body: str,
        commit_sha: str,
        file_path: str,
        line_number: int
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Post a review comment on a pull request.

        Args:
            repo_url: GitHub repository URL
            pr_number: Pull request number
            comment_body: Comment text
            commit_sha: Commit SHA to comment on
            file_path: File path to comment on
            line_number: Line number to comment on

        Returns:
            Tuple of (success, comment_id, error_message)
        """
        try:
            # Get pull request
            success, pr, error = self.get_pull_request(repo_url, pr_number)
            if not success:
                return False, None, error

            # Create review comment
            comment = pr.create_review_comment(
                body=comment_body,
                commit=pr.get_commits()[pr.commits - 1],  # Latest commit
                path=file_path,
                line=line_number
            )

            return True, comment.id, None

        except GithubException as e:
            return False, None, f"Failed to post comment: {e.data.get('message', str(e))}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def post_review(
        self,
        repo_url: str,
        pr_number: int,
        review_body: str,
        event: str = "COMMENT",
        comments: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Post a review on a pull request.

        Args:
            repo_url: GitHub repository URL
            pr_number: Pull request number
            review_body: Review summary text
            event: Review event type (COMMENT, APPROVE, REQUEST_CHANGES)
            comments: Optional list of inline comments:
                [{'path': str, 'line': int, 'body': str}, ...]

        Returns:
            Tuple of (success, review_id, error_message)
        """
        try:
            # Validate event
            valid_events = ['COMMENT', 'APPROVE', 'REQUEST_CHANGES']
            if event not in valid_events:
                return False, None, f"Invalid event: {event}. Must be one of {valid_events}"

            # Get pull request
            success, pr, error = self.get_pull_request(repo_url, pr_number)
            if not success:
                return False, None, error

            # Get latest commit
            latest_commit = pr.get_commits()[pr.commits - 1]

            # Prepare review comments
            review_comments = []
            if comments:
                for comment in comments:
                    review_comments.append({
                        'path': comment['path'],
                        'line': comment['line'],
                        'body': comment['body']
                    })

            # Create review
            if review_comments:
                review = pr.create_review(
                    body=review_body,
                    event=event,
                    comments=review_comments,
                    commit=latest_commit
                )
            else:
                review = pr.create_review(
                    body=review_body,
                    event=event,
                    commit=latest_commit
                )

            return True, review.id, None

        except GithubException as e:
            return False, None, f"Failed to post review: {e.data.get('message', str(e))}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def check_repository_access(
        self,
        repo_url: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if the authenticated user has access to a repository.

        Args:
            repo_url: GitHub repository URL

        Returns:
            Tuple of (has_access, error_message)
        """
        try:
            success, repo, error = self.get_repository(repo_url)
            if not success:
                return False, error

            # Try to get permissions
            permissions = repo.permissions

            return True, None

        except Exception as e:
            return False, f"Error checking access: {str(e)}"

    def _parse_repo_url(self, repo_url: str) -> Tuple[str, str]:
        """
        Parse GitHub repository URL to extract owner and repo name.

        Args:
            repo_url: GitHub repository URL

        Returns:
            Tuple of (owner, repo_name)

        Raises:
            ValueError: If URL format is invalid
        """
        # Remove trailing slashes and .git
        url = repo_url.rstrip('/').rstrip('.git')

        # Handle different URL formats
        if 'github.com/' in url:
            # HTTPS: https://github.com/owner/repo
            parts = url.split('github.com/')[-1].split('/')
        elif 'github.com:' in url:
            # SSH: git@github.com:owner/repo
            parts = url.split('github.com:')[-1].split('/')
        else:
            raise ValueError(f"Invalid GitHub URL format: {repo_url}")

        if len(parts) < 2:
            raise ValueError(f"Invalid GitHub URL format: {repo_url}")

        owner = parts[0]
        repo_name = parts[1]

        return owner, repo_name

    def get_authenticated_user(self) -> Dict[str, Any]:
        """
        Get information about the authenticated user.

        Returns:
            Dictionary with user information
        """
        return {
            'login': self.user.login,
            'name': self.user.name,
            'email': self.user.email,
            'avatar_url': self.user.avatar_url,
            'html_url': self.user.html_url
        }

    def post_review_comments(
        self,
        repo_url: str,
        pr_number: int,
        comments: List[Dict[str, Any]],
        summary: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Post review comments to a GitHub pull request.

        Args:
            repo_url: GitHub repository URL
            pr_number: Pull request number
            comments: List of comment dictionaries (from ReviewService)
            summary: Optional review summary

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get pull request
            success, pr, error = self.get_pull_request(repo_url, pr_number)
            if not success:
                return False, error

            # Post review summary as a comment if provided
            if summary:
                pr.create_issue_comment(summary)

            # Post inline comments
            # Get latest commit
            commits = list(pr.get_commits())
            if not commits:
                return False, "No commits found in PR"

            latest_commit = commits[-1]

            # Group comments by file for efficiency
            for comment_data in comments:
                try:
                    # Create review comment
                    body = comment_data.get('comment_text', '')
                    path = comment_data.get('file_path', '')
                    line = comment_data.get('line_number')

                    if not path or not body:
                        continue

                    # Post comment
                    if line:
                        pr.create_review_comment(
                            body=body,
                            commit=latest_commit,
                            path=path,
                            line=line
                        )
                    else:
                        # File-level comment (no specific line)
                        # Post as issue comment with file mention
                        pr.create_issue_comment(f"**{path}**\n\n{body}")

                except Exception as e:
                    # Continue with other comments if one fails
                    print(f"Failed to post comment on {path}: {e}")
                    continue

            return True, None

        except Exception as e:
            return False, f"Failed to post review: {str(e)}"

    def create_pr_review(
        self,
        repo_url: str,
        pr_number: int,
        event: str,
        body: Optional[str] = None,
        comments: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Create a full PR review with comments.

        Args:
            repo_url: GitHub repository URL
            pr_number: Pull request number
            event: Review event (APPROVE, REQUEST_CHANGES, COMMENT)
            body: Review body text
            comments: List of review comments with path, line, body

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get pull request
            success, pr, error = self.get_pull_request(repo_url, pr_number)
            if not success:
                return False, error

            # Get latest commit
            commits = list(pr.get_commits())
            if not commits:
                return False, "No commits found in PR"

            latest_commit = commits[-1]

            # Format comments for GitHub review API
            review_comments = []
            if comments:
                for comment in comments:
                    if comment.get('file_path') and comment.get('comment_text'):
                        review_comment = {
                            'path': comment['file_path'],
                            'body': comment['comment_text']
                        }

                        # Add line number if available
                        if comment.get('line_number'):
                            review_comment['line'] = comment['line_number']
                            review_comment['side'] = 'RIGHT'

                        review_comments.append(review_comment)

            # Create review
            pr.create_review(
                commit=latest_commit,
                body=body,
                event=event,
                comments=review_comments if review_comments else None
            )

            return True, None

        except Exception as e:
            return False, f"Failed to create review: {str(e)}"

    def create_issue(
        self,
        repo_url: str,
        title: str,
        body: str,
        labels: Optional[List[str]] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Create an issue in a GitHub repository.

        Args:
            repo_url: GitHub repository URL
            title: Issue title
            body: Issue description
            labels: Optional list of label names

        Returns:
            Tuple of (success, issue_dict, error_message)
        """
        try:
            # Get repository
            success, repo, error = self.get_repository(repo_url)
            if not success:
                return False, None, error

            # Create issue
            if labels:
                issue = repo.create_issue(title=title, body=body, labels=labels)
            else:
                issue = repo.create_issue(title=title, body=body)

            # Return issue info
            issue_info = {
                'number': issue.number,
                'title': issue.title,
                'body': issue.body,
                'state': issue.state,
                'html_url': issue.html_url,
                'created_at': issue.created_at.isoformat(),
                'github_id': issue.id
            }

            return True, issue_info, None

        except GithubException as e:
            return False, None, f"Failed to create issue: {e.data.get('message', str(e))}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def close(self):
        """Close the GitHub client connection."""
        if hasattr(self, 'client'):
            self.client.close()
