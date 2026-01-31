"""
Unit tests for authentication manager.

Tests user registration, login, session management, and password updates.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.database import Base, User, UserSession
from src.core.auth_manager import AuthManager


@pytest.fixture
def db_session():
    """Create test database session."""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def auth_manager():
    """Create auth manager instance."""
    return AuthManager(session_ttl_days=30)


@pytest.fixture
def registered_user(db_session, auth_manager):
    """Create a registered user."""
    success, user, error = auth_manager.register_user(
        db_session,
        username='testuser',
        email='test@example.com',
        password='password123'
    )
    assert success
    return user


class TestRegistration:
    """Test user registration."""

    def test_register_user_success(self, db_session, auth_manager):
        """Test successful user registration."""
        success, user, error = auth_manager.register_user(
            db_session,
            username='johndoe',
            email='john@example.com',
            password='securepassword'
        )

        assert success is True
        assert user is not None
        assert user.username == 'johndoe'
        assert user.email == 'john@example.com'
        assert user.password_hash is not None
        assert user.password_hash != 'securepassword'  # Should be hashed
        assert error is None

    def test_register_username_too_short(self, db_session, auth_manager):
        """Test registration with username too short."""
        success, user, error = auth_manager.register_user(
            db_session,
            username='ab',  # Only 2 characters
            email='test@example.com',
            password='password123'
        )

        assert success is False
        assert user is None
        assert 'must be 3-50 characters' in error

    def test_register_username_too_long(self, db_session, auth_manager):
        """Test registration with username too long."""
        success, user, error = auth_manager.register_user(
            db_session,
            username='a' * 51,  # 51 characters
            email='test@example.com',
            password='password123'
        )

        assert success is False
        assert user is None
        assert 'must be 3-50 characters' in error

    def test_register_username_invalid_chars(self, db_session, auth_manager):
        """Test registration with invalid username characters."""
        success, user, error = auth_manager.register_user(
            db_session,
            username='user@name',  # Contains @
            email='test@example.com',
            password='password123'
        )

        assert success is False
        assert user is None
        assert 'letters, numbers, and underscores' in error

    def test_register_invalid_email(self, db_session, auth_manager):
        """Test registration with invalid email."""
        success, user, error = auth_manager.register_user(
            db_session,
            username='validuser',
            email='invalid-email',
            password='password123'
        )

        assert success is False
        assert user is None
        assert 'Invalid email' in error

    def test_register_password_too_short(self, db_session, auth_manager):
        """Test registration with password too short."""
        success, user, error = auth_manager.register_user(
            db_session,
            username='validuser',
            email='test@example.com',
            password='short'  # Only 5 characters
        )

        assert success is False
        assert user is None
        assert 'at least 8 characters' in error

    def test_register_duplicate_username(self, db_session, auth_manager, registered_user):
        """Test registration with duplicate username."""
        success, user, error = auth_manager.register_user(
            db_session,
            username='testuser',  # Same as registered_user
            email='different@example.com',
            password='password123'
        )

        assert success is False
        assert user is None
        assert 'already exists' in error

    def test_register_duplicate_email(self, db_session, auth_manager, registered_user):
        """Test registration with duplicate email."""
        success, user, error = auth_manager.register_user(
            db_session,
            username='differentuser',
            email='test@example.com',  # Same as registered_user
            password='password123'
        )

        assert success is False
        assert user is None
        assert 'already registered' in error

    def test_password_is_hashed(self, db_session, auth_manager):
        """Test that password is properly hashed with bcrypt."""
        success, user, error = auth_manager.register_user(
            db_session,
            username='user',
            email='user@example.com',
            password='mypassword'
        )

        assert success is True
        assert user.password_hash.startswith('$2b$')  # bcrypt hash format
        assert user.password_hash != 'mypassword'
        assert len(user.password_hash) == 60  # bcrypt hash length


class TestAuthentication:
    """Test user authentication."""

    def test_authenticate_success(self, db_session, auth_manager, registered_user):
        """Test successful authentication."""
        success, user, error = auth_manager.authenticate(
            db_session,
            username='testuser',
            password='password123'
        )

        assert success is True
        assert user is not None
        assert user.id == registered_user.id
        assert user.username == 'testuser'
        assert error is None

    def test_authenticate_wrong_password(self, db_session, auth_manager, registered_user):
        """Test authentication with wrong password."""
        success, user, error = auth_manager.authenticate(
            db_session,
            username='testuser',
            password='wrongpassword'
        )

        assert success is False
        assert user is None
        assert 'Invalid username or password' in error

    def test_authenticate_nonexistent_user(self, db_session, auth_manager):
        """Test authentication with non-existent username."""
        success, user, error = auth_manager.authenticate(
            db_session,
            username='nonexistent',
            password='password123'
        )

        assert success is False
        assert user is None
        assert 'Invalid username or password' in error

    def test_authenticate_case_sensitive(self, db_session, auth_manager, registered_user):
        """Test that username is case-sensitive."""
        success, user, error = auth_manager.authenticate(
            db_session,
            username='TestUser',  # Different case
            password='password123'
        )

        assert success is False
        assert user is None


class TestSessionManagement:
    """Test session creation and validation."""

    def test_create_session_success(self, db_session, auth_manager, registered_user):
        """Test successful session creation."""
        success, session, error = auth_manager.create_session(db_session, registered_user)

        assert success is True
        assert session is not None
        assert session.id is not None
        assert len(session.id) > 32  # Should be URL-safe base64
        assert session.user_id == registered_user.id
        assert session.expires_at > datetime.utcnow()
        assert error is None

    def test_session_ttl(self, db_session, registered_user):
        """Test session TTL configuration."""
        auth_manager = AuthManager(session_ttl_days=7)
        success, session, error = auth_manager.create_session(db_session, registered_user)

        assert success is True
        delta = session.expires_at - datetime.utcnow()
        assert delta.days == 6 or delta.days == 7  # Account for seconds

    def test_validate_session_success(self, db_session, auth_manager, registered_user):
        """Test successful session validation."""
        # Create session
        success, session, error = auth_manager.create_session(db_session, registered_user)
        assert success

        # Validate session
        valid, user, error = auth_manager.validate_session(db_session, session.id)

        assert valid is True
        assert user is not None
        assert user.id == registered_user.id
        assert error is None

    def test_validate_invalid_token(self, db_session, auth_manager):
        """Test validation with invalid token."""
        valid, user, error = auth_manager.validate_session(db_session, 'invalid_token')

        assert valid is False
        assert user is None
        assert 'Invalid session' in error

    def test_validate_expired_session(self, db_session, auth_manager, registered_user):
        """Test validation of expired session."""
        # Create expired session manually
        expired_session = UserSession(
            id='expired_token',
            user_id=registered_user.id,
            expires_at=datetime.utcnow() - timedelta(days=1)  # Expired yesterday
        )
        db_session.add(expired_session)
        db_session.commit()

        # Try to validate
        valid, user, error = auth_manager.validate_session(db_session, 'expired_token')

        assert valid is False
        assert user is None
        assert 'expired' in error.lower()

        # Verify session was deleted
        deleted = db_session.query(UserSession).filter(UserSession.id == 'expired_token').first()
        assert deleted is None

    def test_validate_session_updates_last_accessed(self, db_session, auth_manager, registered_user):
        """Test that validating session updates last_accessed."""
        # Create session
        success, session, error = auth_manager.create_session(db_session, registered_user)
        original_accessed = session.last_accessed

        # Wait a moment and validate
        import time
        time.sleep(0.1)

        valid, user, error = auth_manager.validate_session(db_session, session.id)
        assert valid

        # Refresh session from database
        db_session.refresh(session)
        assert session.last_accessed > original_accessed

    def test_delete_session_success(self, db_session, auth_manager, registered_user):
        """Test successful session deletion."""
        # Create session
        success, session, error = auth_manager.create_session(db_session, registered_user)
        token = session.id

        # Delete session
        success, error = auth_manager.delete_session(db_session, token)

        assert success is True
        assert error is None

        # Verify deleted
        deleted = db_session.query(UserSession).filter(UserSession.id == token).first()
        assert deleted is None

    def test_delete_nonexistent_session(self, db_session, auth_manager):
        """Test deleting non-existent session."""
        success, error = auth_manager.delete_session(db_session, 'nonexistent')

        assert success is False
        assert 'not found' in error


class TestSessionCleanup:
    """Test session cleanup operations."""

    def test_cleanup_expired_sessions(self, db_session, auth_manager, registered_user):
        """Test cleaning up expired sessions."""
        # Create valid session
        success, valid_session, _ = auth_manager.create_session(db_session, registered_user)

        # Create expired session
        expired = UserSession(
            id='expired1',
            user_id=registered_user.id,
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        db_session.add(expired)
        db_session.commit()

        # Cleanup
        count = auth_manager.cleanup_expired_sessions(db_session)

        assert count == 1

        # Verify expired session deleted, valid session remains
        remaining = db_session.query(UserSession).all()
        assert len(remaining) == 1
        assert remaining[0].id == valid_session.id

    def test_get_user_sessions(self, db_session, auth_manager, registered_user):
        """Test getting user sessions."""
        # Create multiple sessions
        success, session1, _ = auth_manager.create_session(db_session, registered_user)
        success, session2, _ = auth_manager.create_session(db_session, registered_user)

        # Get sessions
        sessions = auth_manager.get_user_sessions(db_session, registered_user.id)

        assert len(sessions) == 2

    def test_get_user_sessions_exclude_expired(self, db_session, auth_manager, registered_user):
        """Test getting user sessions excluding expired."""
        # Create valid session
        success, valid, _ = auth_manager.create_session(db_session, registered_user)

        # Create expired session
        expired = UserSession(
            id='expired',
            user_id=registered_user.id,
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        db_session.add(expired)
        db_session.commit()

        # Get sessions (excluding expired)
        sessions = auth_manager.get_user_sessions(db_session, registered_user.id, include_expired=False)

        assert len(sessions) == 1
        assert sessions[0].id == valid.id

    def test_revoke_all_user_sessions(self, db_session, auth_manager, registered_user):
        """Test revoking all sessions for a user."""
        # Create multiple sessions
        success, session1, _ = auth_manager.create_session(db_session, registered_user)
        success, session2, _ = auth_manager.create_session(db_session, registered_user)

        # Revoke all
        count = auth_manager.revoke_all_user_sessions(db_session, registered_user.id)

        assert count == 2

        # Verify all deleted
        remaining = db_session.query(UserSession).filter(
            UserSession.user_id == registered_user.id
        ).all()
        assert len(remaining) == 0


class TestPasswordUpdate:
    """Test password update functionality."""

    def test_update_password_success(self, db_session, auth_manager, registered_user):
        """Test successful password update."""
        success, error = auth_manager.update_password(
            db_session,
            registered_user,
            old_password='password123',
            new_password='newpassword456'
        )

        assert success is True
        assert error is None

        # Verify can login with new password
        auth_success, user, _ = auth_manager.authenticate(
            db_session,
            username='testuser',
            password='newpassword456'
        )
        assert auth_success is True

        # Verify cannot login with old password
        auth_success, user, _ = auth_manager.authenticate(
            db_session,
            username='testuser',
            password='password123'
        )
        assert auth_success is False

    def test_update_password_wrong_old_password(self, db_session, auth_manager, registered_user):
        """Test password update with wrong old password."""
        success, error = auth_manager.update_password(
            db_session,
            registered_user,
            old_password='wrongpassword',
            new_password='newpassword456'
        )

        assert success is False
        assert 'incorrect' in error.lower()

    def test_update_password_too_short(self, db_session, auth_manager, registered_user):
        """Test password update with new password too short."""
        success, error = auth_manager.update_password(
            db_session,
            registered_user,
            old_password='password123',
            new_password='short'
        )

        assert success is False
        assert 'at least 8 characters' in error
