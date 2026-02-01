"""
Unit tests for Phase 4 - Web Interface

Tests FastAPI endpoints, authentication, and research operations.
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import app, db_manager
from src.core.database import DatabaseManager, User

# Clean up test users before running tests
@pytest.fixture(scope="session", autouse=True)
def cleanup_database():
    """Clean up test users before running tests."""
    with db_manager.get_session() as db_session:
        # Delete test users from previous runs
        test_usernames = [
            'testuser_phase4',
            'duplicate_user',
            'logintest',
            'currentuser',
            'logoutuser',
            'researcher'
        ]
        db_session.query(User).filter(User.username.in_(test_usernames)).delete(synchronize_session=False)
        db_session.commit()
    yield

# Test client
client = TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health(self):
        """Test health check."""
        response = client.get("/api/health")
        assert response.status_code == 200

        data = response.json()
        assert data['status'] == 'ok'
        assert 'database' in data
        assert 'cache_enabled' in data


class TestAuthenticationEndpoints:
    """Test authentication endpoints."""

    def test_register_success(self):
        """Test successful user registration."""
        response = client.post("/api/auth/register", json={
            "username": "testuser_phase4",
            "email": "test_phase4@example.com",
            "password": "testpassword123"
        })

        assert response.status_code == 200
        data = response.json()
        assert 'user_id' in data
        assert data['username'] == "testuser_phase4"
        assert data['email'] == "test_phase4@example.com"

    def test_register_duplicate_username(self):
        """Test registration with duplicate username."""
        # First registration
        client.post("/api/auth/register", json={
            "username": "duplicate_user",
            "email": "dup1@example.com",
            "password": "password123"
        })

        # Duplicate registration
        response = client.post("/api/auth/register", json={
            "username": "duplicate_user",
            "email": "dup2@example.com",
            "password": "password123"
        })

        assert response.status_code == 400

    def test_login_success(self):
        """Test successful login."""
        # Register first
        client.post("/api/auth/register", json={
            "username": "logintest",
            "email": "login@example.com",
            "password": "password123"
        })

        # Login
        response = client.post("/api/auth/login", json={
            "username": "logintest",
            "password": "password123"
        })

        assert response.status_code == 200
        data = response.json()
        assert data['username'] == "logintest"

        # Check cookie is set
        assert 'session_token' in response.cookies

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        response = client.post("/api/auth/login", json={
            "username": "nonexistent",
            "password": "wrongpassword"
        })

        assert response.status_code == 401

    def test_get_current_user(self):
        """Test getting current user info."""
        # Register and login
        client.post("/api/auth/register", json={
            "username": "currentuser",
            "email": "current@example.com",
            "password": "password123"
        })

        login_response = client.post("/api/auth/login", json={
            "username": "currentuser",
            "password": "password123"
        })

        cookies = login_response.cookies

        # Get current user
        response = client.get("/api/auth/me", cookies=cookies)

        assert response.status_code == 200
        data = response.json()
        assert data['username'] == "currentuser"
        assert 'created_at' in data

    def test_logout(self):
        """Test logout."""
        # Register and login
        client.post("/api/auth/register", json={
            "username": "logoutuser",
            "email": "logout@example.com",
            "password": "password123"
        })

        login_response = client.post("/api/auth/login", json={
            "username": "logoutuser",
            "password": "password123"
        })

        cookies = login_response.cookies

        # Logout
        response = client.post("/api/auth/logout", cookies=cookies)

        assert response.status_code == 200
        assert response.json()['success'] is True


class TestResearchEndpoints:
    """Test research API endpoints."""

    @pytest.fixture
    def authenticated_client(self):
        """Create authenticated client."""
        # Register and login
        client.post("/api/auth/register", json={
            "username": "researcher",
            "email": "researcher@example.com",
            "password": "password123"
        })

        login_response = client.post("/api/auth/login", json={
            "username": "researcher",
            "password": "password123"
        })

        return login_response.cookies

    def test_list_research_empty(self, authenticated_client):
        """Test listing research queries when empty."""
        response = client.get("/api/research", cookies=authenticated_client)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data['queries'], list)

    def test_list_research_unauthenticated(self):
        """Test listing research without authentication."""
        # Use fresh client to ensure no cookies from previous tests
        fresh_client = TestClient(app)
        response = fresh_client.get("/api/research")

        assert response.status_code == 401


class TestStaticFiles:
    """Test static file serving."""

    def test_index_page(self):
        """Test index page loads."""
        response = client.get("/")

        assert response.status_code == 200
        assert 'text/html' in response.headers['content-type']

    def test_css_file(self):
        """Test CSS file is accessible."""
        response = client.get("/static/styles.css")

        assert response.status_code == 200
        assert 'text/css' in response.headers['content-type']

    def test_js_file(self):
        """Test JavaScript file is accessible."""
        response = client.get("/static/app.js")

        assert response.status_code == 200
