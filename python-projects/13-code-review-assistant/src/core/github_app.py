"""
GitHub App Authentication and Management
Handles GitHub App installation tokens and authentication
"""

import time
import jwt
import requests
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os


class GitHubApp:
    """
    Manages GitHub App authentication and installation tokens.

    Features:
    - JWT generation for GitHub App authentication
    - Installation token management with caching
    - Automatic token refresh
    - Multi-installation support
    """

    def __init__(self, app_id: Optional[str] = None, private_key: Optional[str] = None):
        """
        Initialize GitHub App client.

        Args:
            app_id: GitHub App ID (defaults to env var GITHUB_APP_ID)
            private_key: Path to private key file or PEM content (defaults to env var GITHUB_PRIVATE_KEY)
        """
        self.app_id = app_id or os.getenv('GITHUB_APP_ID')

        # Get private key from env or file
        private_key_input = private_key or os.getenv('GITHUB_PRIVATE_KEY')

        if private_key_input and Path(private_key_input).exists():
            # It's a file path
            with open(private_key_input, 'r') as f:
                self.private_key = f.read()
        else:
            # It's the PEM content directly
            self.private_key = private_key_input

        # Cache for installation tokens
        self._installation_tokens: Dict[int, Dict] = {}

        # GitHub API base URL
        self.api_base = os.getenv('GITHUB_API_URL', 'https://api.github.com')

    def generate_jwt(self, expiration_seconds: int = 600) -> str:
        """
        Generate JWT for GitHub App authentication.

        Args:
            expiration_seconds: JWT expiration time (max 600 seconds)

        Returns:
            JWT token string
        """
        if not self.app_id or not self.private_key:
            raise ValueError("GitHub App ID and private key are required")

        # JWT payload
        now = int(time.time())
        payload = {
            'iat': now - 60,  # Issued at time (60 seconds in the past to allow for clock drift)
            'exp': now + min(expiration_seconds, 600),  # Expiration (max 10 minutes)
            'iss': self.app_id  # Issuer (GitHub App ID)
        }

        # Generate JWT
        token = jwt.encode(payload, self.private_key, algorithm='RS256')

        return token

    def get_installation_token(self, installation_id: int, force_refresh: bool = False) -> str:
        """
        Get installation access token for a specific installation.

        Args:
            installation_id: GitHub App installation ID
            force_refresh: Force token refresh even if cached token is valid

        Returns:
            Installation access token
        """
        # Check cache
        if not force_refresh and installation_id in self._installation_tokens:
            cached = self._installation_tokens[installation_id]
            expires_at = datetime.fromisoformat(cached['expires_at'].replace('Z', '+00:00'))

            # Return cached token if still valid (with 5-minute buffer)
            if datetime.now(timezone.utc) < expires_at - timedelta(minutes=5):
                return cached['token']

        # Generate new installation token
        jwt_token = self.generate_jwt()

        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28'
        }

        url = f'{self.api_base}/app/installations/{installation_id}/access_tokens'

        response = requests.post(url, headers=headers)
        response.raise_for_status()

        token_data = response.json()

        # Cache the token
        self._installation_tokens[installation_id] = {
            'token': token_data['token'],
            'expires_at': token_data['expires_at']
        }

        return token_data['token']

    def get_installation_id(self, owner: str, repo: str) -> Optional[int]:
        """
        Get installation ID for a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Installation ID or None if not found
        """
        jwt_token = self.generate_jwt()

        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28'
        }

        url = f'{self.api_base}/repos/{owner}/{repo}/installation'

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()['id']
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def create_authenticated_client(self, installation_id: int):
        """
        Create an authenticated GitHub client for an installation.

        Args:
            installation_id: GitHub App installation ID

        Returns:
            Authenticated requests session
        """
        token = self.get_installation_token(installation_id)

        session = requests.Session()
        session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28'
        })

        return session

    def list_installations(self) -> list:
        """
        List all installations of this GitHub App.

        Returns:
            List of installation objects
        """
        jwt_token = self.generate_jwt()

        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28'
        }

        url = f'{self.api_base}/app/installations'

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        return response.json()

    def revoke_installation_token(self, installation_id: int):
        """
        Revoke cached installation token.

        Args:
            installation_id: GitHub App installation ID
        """
        if installation_id in self._installation_tokens:
            del self._installation_tokens[installation_id]

    def is_configured(self) -> bool:
        """
        Check if GitHub App is properly configured.

        Returns:
            True if app_id and private_key are set
        """
        return bool(self.app_id and self.private_key)


# Global GitHub App instance
_github_app: Optional[GitHubApp] = None


def get_github_app() -> GitHubApp:
    """
    Get the global GitHub App instance.

    Returns:
        GitHubApp instance
    """
    global _github_app

    if _github_app is None:
        _github_app = GitHubApp()

    return _github_app
