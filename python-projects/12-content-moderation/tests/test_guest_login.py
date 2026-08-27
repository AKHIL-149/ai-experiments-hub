"""
Tests for guest account creation - AuthManager.create_guest_user() and
the /api/auth/guest endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from server import app
from src.core.database import DatabaseManager, User
from src.core.auth_manager import AuthManager


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_manager():
    """Bare DatabaseManager() - conftest.py redirects this to the same
    isolated temp-file DB server.py's own singleton resolves to, so a
    row created here is visible to routes hit through TestClient."""
    db = DatabaseManager()
    db.create_tables()
    return db


def test_create_guest_user_generates_unique_account(db_manager):
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, 30)
        success, user, error = auth_manager.create_guest_user()

        assert success is True
        assert error is None
        assert user.is_guest is True
        assert user.username.startswith('guest_')
        assert user.email.endswith('@guest.local')
        assert user.role.value == 'user'
        assert user.is_active is True


def test_create_guest_user_twice_gives_different_accounts(db_manager):
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, 30)
        _, user1, _ = auth_manager.create_guest_user()
        _, user2, _ = auth_manager.create_guest_user()

        assert user1.username != user2.username
        assert user1.id != user2.id


def test_regular_register_defaults_is_guest_false(db_manager):
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, 30)
        success, user, error = auth_manager.register_user(
            'realuser01', 'realuser01@example.com', 'RealPass123!'
        )

        assert success is True
        assert user.is_guest is False


def test_guest_login_endpoint_creates_session(client):
    response = client.post('/api/auth/guest')

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['user']['is_guest'] is True
    assert data['user']['username'].startswith('guest_')
    assert 'session_token' in response.cookies


def test_guest_login_endpoint_logs_in_immediately(client):
    guest_response = client.post('/api/auth/guest')
    assert guest_response.status_code == 200

    me_response = client.get(
        '/api/auth/me',
        cookies={'session_token': guest_response.cookies.get('session_token')}
    )

    assert me_response.status_code == 200
    assert me_response.json()['is_guest'] is True


def test_guest_can_submit_content(client):
    guest_response = client.post('/api/auth/guest')
    session_token = guest_response.cookies.get('session_token')

    response = client.post(
        '/api/content',
        data={'content_type': 'text', 'text_content': 'Hello from a guest'},
        cookies={'session_token': session_token}
    )

    assert response.status_code == 200
