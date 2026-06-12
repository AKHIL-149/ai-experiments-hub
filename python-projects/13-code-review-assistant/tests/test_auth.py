"""
Tests for authentication and authorization
"""

import pytest
from datetime import datetime, timedelta
from src.core.database import DatabaseManager, User, UserSession, UserRole
from src.core.auth_manager import AuthManager


@pytest.fixture
def db_manager():
    """Create in-memory database for testing"""
    db = DatabaseManager('sqlite:///:memory:')
    db.init_db()
    yield db
    db.close()


@pytest.fixture
def db_session(db_manager):
    """Get database session"""
    with db_manager.get_session() as session:
        yield session


@pytest.fixture
def auth_manager(db_session):
    """Create auth manager instance"""
    return AuthManager(db_session, session_ttl_days=30)


def test_register_user_success(auth_manager):
    """Test successful user registration"""
    success, user, error = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    assert success is True
    assert user is not None
    assert user.username == 'testuser'
    assert user.email == 'test@example.com'
    assert user.role == UserRole.USER
    assert error is None


def test_register_user_short_username(auth_manager):
    """Test registration with short username"""
    success, user, error = auth_manager.register_user(
        username='ab',
        email='test@example.com',
        password='password123'
    )

    assert success is False
    assert user is None
    assert 'Username must be 3-50 characters' in error


def test_register_user_long_username(auth_manager):
    """Test registration with long username"""
    success, user, error = auth_manager.register_user(
        username='a' * 51,
        email='test@example.com',
        password='password123'
    )

    assert success is False
    assert user is None
    assert 'Username must be 3-50 characters' in error


def test_register_user_short_password(auth_manager):
    """Test registration with short password"""
    success, user, error = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='short'
    )

    assert success is False
    assert user is None
    assert 'Password must be at least 8 characters' in error


def test_register_user_invalid_email(auth_manager):
    """Test registration with invalid email"""
    success, user, error = auth_manager.register_user(
        username='testuser',
        email='invalid-email',
        password='password123'
    )

    assert success is False
    assert user is None
    assert 'Invalid email format' in error


def test_register_duplicate_username(auth_manager):
    """Test registration with duplicate username"""
    auth_manager.register_user(
        username='testuser',
        email='test1@example.com',
        password='password123'
    )

    success, user, error = auth_manager.register_user(
        username='testuser',
        email='test2@example.com',
        password='password123'
    )

    assert success is False
    assert user is None
    assert 'Username or email already exists' in error


def test_register_duplicate_email(auth_manager):
    """Test registration with duplicate email"""
    auth_manager.register_user(
        username='testuser1',
        email='test@example.com',
        password='password123'
    )

    success, user, error = auth_manager.register_user(
        username='testuser2',
        email='test@example.com',
        password='password123'
    )

    assert success is False
    assert user is None
    assert 'Username or email already exists' in error


def test_authenticate_success(auth_manager):
    """Test successful authentication"""
    auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    success, user, error = auth_manager.authenticate(
        username='testuser',
        password='password123'
    )

    assert success is True
    assert user is not None
    assert user.username == 'testuser'
    assert error is None


def test_authenticate_wrong_password(auth_manager):
    """Test authentication with wrong password"""
    auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    success, user, error = auth_manager.authenticate(
        username='testuser',
        password='wrongpassword'
    )

    assert success is False
    assert user is None
    assert 'Invalid username or password' in error


def test_authenticate_nonexistent_user(auth_manager):
    """Test authentication with non-existent user"""
    success, user, error = auth_manager.authenticate(
        username='nonexistent',
        password='password123'
    )

    assert success is False
    assert user is None
    assert 'Invalid username or password' in error


def test_authenticate_inactive_user(auth_manager, db_session):
    """Test authentication with inactive user"""
    success, user, error = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    user.is_active = False
    db_session.commit()

    success, user, error = auth_manager.authenticate(
        username='testuser',
        password='password123'
    )

    assert success is False
    assert user is None
    assert 'Account is deactivated' in error


def test_create_session(auth_manager):
    """Test session creation"""
    success, user, _ = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    session_token = auth_manager.create_session(user, ip_address='127.0.0.1')

    assert session_token is not None
    assert len(session_token) > 0


def test_validate_session_success(auth_manager):
    """Test successful session validation"""
    success, user, _ = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    session_token = auth_manager.create_session(user)
    success, validated_user, error = auth_manager.validate_session(session_token)

    assert success is True
    assert validated_user is not None
    assert validated_user.id == user.id
    assert error is None


def test_validate_session_invalid_token(auth_manager):
    """Test session validation with invalid token"""
    success, user, error = auth_manager.validate_session('invalid_token')

    assert success is False
    assert user is None
    assert 'Invalid session' in error


def test_validate_session_expired(auth_manager, db_session):
    """Test session validation with expired session"""
    success, user, _ = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    session_token = auth_manager.create_session(user)

    # Manually expire the session
    session = db_session.query(UserSession).filter_by(id=session_token).first()
    session.expires_at = datetime.utcnow() - timedelta(days=1)
    db_session.commit()

    success, validated_user, error = auth_manager.validate_session(session_token)

    assert success is False
    assert validated_user is None
    assert 'Session expired' in error


def test_delete_session(auth_manager):
    """Test session deletion"""
    success, user, _ = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    session_token = auth_manager.create_session(user)
    result = auth_manager.delete_session(session_token)

    assert result is True

    success, _, _ = auth_manager.validate_session(session_token)
    assert success is False


def test_delete_all_user_sessions(auth_manager):
    """Test deleting all user sessions"""
    success, user, _ = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    token1 = auth_manager.create_session(user)
    token2 = auth_manager.create_session(user)

    count = auth_manager.delete_all_user_sessions(user.id)

    assert count == 2

    success1, _, _ = auth_manager.validate_session(token1)
    success2, _, _ = auth_manager.validate_session(token2)

    assert success1 is False
    assert success2 is False


def test_cleanup_expired_sessions(auth_manager, db_session):
    """Test cleanup of expired sessions"""
    success, user, _ = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    token1 = auth_manager.create_session(user)
    token2 = auth_manager.create_session(user)

    # Expire one session
    session = db_session.query(UserSession).filter_by(id=token1).first()
    session.expires_at = datetime.utcnow() - timedelta(days=1)
    db_session.commit()

    count = auth_manager.cleanup_expired_sessions()

    assert count == 1

    success1, _, _ = auth_manager.validate_session(token1)
    success2, _, _ = auth_manager.validate_session(token2)

    assert success1 is False
    assert success2 is True


def test_is_admin(auth_manager):
    """Test admin role check"""
    success, admin_user, _ = auth_manager.register_user(
        username='admin',
        email='admin@example.com',
        password='password123',
        role=UserRole.ADMIN
    )

    success, regular_user, _ = auth_manager.register_user(
        username='user',
        email='user@example.com',
        password='password123',
        role=UserRole.USER
    )

    assert auth_manager.is_admin(admin_user) is True
    assert auth_manager.is_admin(regular_user) is False


def test_has_role(auth_manager):
    """Test role hierarchy check"""
    success, admin_user, _ = auth_manager.register_user(
        username='admin',
        email='admin@example.com',
        password='password123',
        role=UserRole.ADMIN
    )

    success, regular_user, _ = auth_manager.register_user(
        username='user',
        email='user@example.com',
        password='password123',
        role=UserRole.USER
    )

    assert auth_manager.has_role(admin_user, UserRole.USER) is True
    assert auth_manager.has_role(admin_user, UserRole.ADMIN) is True
    assert auth_manager.has_role(regular_user, UserRole.USER) is True
    assert auth_manager.has_role(regular_user, UserRole.ADMIN) is False


def test_change_password_success(auth_manager):
    """Test successful password change"""
    success, user, _ = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='oldpassword'
    )

    success, error = auth_manager.change_password(
        user=user,
        old_password='oldpassword',
        new_password='newpassword'
    )

    assert success is True
    assert error is None

    auth_success, _, _ = auth_manager.authenticate('testuser', 'newpassword')
    assert auth_success is True


def test_change_password_wrong_old_password(auth_manager):
    """Test password change with wrong old password"""
    success, user, _ = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='oldpassword'
    )

    success, error = auth_manager.change_password(
        user=user,
        old_password='wrongpassword',
        new_password='newpassword'
    )

    assert success is False
    assert 'Current password is incorrect' in error


def test_change_password_short_new_password(auth_manager):
    """Test password change with short new password"""
    success, user, _ = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='oldpassword'
    )

    success, error = auth_manager.change_password(
        user=user,
        old_password='oldpassword',
        new_password='short'
    )

    assert success is False
    assert 'New password must be at least 8 characters' in error


def test_update_user_role(auth_manager):
    """Test updating user role"""
    success, admin_user, _ = auth_manager.register_user(
        username='admin',
        email='admin@example.com',
        password='password123',
        role=UserRole.ADMIN
    )

    success, target_user, _ = auth_manager.register_user(
        username='user',
        email='user@example.com',
        password='password123',
        role=UserRole.USER
    )

    success, updated_user, error = auth_manager.update_user_role(
        admin_user=admin_user,
        target_user_id=target_user.id,
        new_role=UserRole.ADMIN
    )

    assert success is True
    assert updated_user.role == UserRole.ADMIN
    assert error is None


def test_update_user_role_non_admin(auth_manager):
    """Test updating user role without admin privileges"""
    success, regular_user, _ = auth_manager.register_user(
        username='user1',
        email='user1@example.com',
        password='password123',
        role=UserRole.USER
    )

    success, target_user, _ = auth_manager.register_user(
        username='user2',
        email='user2@example.com',
        password='password123',
        role=UserRole.USER
    )

    success, updated_user, error = auth_manager.update_user_role(
        admin_user=regular_user,
        target_user_id=target_user.id,
        new_role=UserRole.ADMIN
    )

    assert success is False
    assert updated_user is None
    assert 'Insufficient permissions' in error


def test_deactivate_user(auth_manager):
    """Test user deactivation"""
    success, admin_user, _ = auth_manager.register_user(
        username='admin',
        email='admin@example.com',
        password='password123',
        role=UserRole.ADMIN
    )

    success, target_user, _ = auth_manager.register_user(
        username='user',
        email='user@example.com',
        password='password123'
    )

    success, deactivated_user, error = auth_manager.deactivate_user(
        admin_user=admin_user,
        target_user_id=target_user.id
    )

    assert success is True
    assert deactivated_user.is_active is False
    assert error is None


def test_deactivate_self(auth_manager):
    """Test preventing self-deactivation"""
    success, admin_user, _ = auth_manager.register_user(
        username='admin',
        email='admin@example.com',
        password='password123',
        role=UserRole.ADMIN
    )

    success, deactivated_user, error = auth_manager.deactivate_user(
        admin_user=admin_user,
        target_user_id=admin_user.id
    )

    assert success is False
    assert deactivated_user is None
    assert 'Cannot deactivate your own account' in error


def test_reactivate_user(auth_manager):
    """Test user reactivation"""
    success, admin_user, _ = auth_manager.register_user(
        username='admin',
        email='admin@example.com',
        password='password123',
        role=UserRole.ADMIN
    )

    success, target_user, _ = auth_manager.register_user(
        username='user',
        email='user@example.com',
        password='password123'
    )

    auth_manager.deactivate_user(admin_user, target_user.id)

    success, reactivated_user, error = auth_manager.reactivate_user(
        admin_user=admin_user,
        target_user_id=target_user.id
    )

    assert success is True
    assert reactivated_user.is_active is True
    assert error is None


def test_get_active_sessions(auth_manager, db_session):
    """Test getting active sessions for user"""
    success, user, _ = auth_manager.register_user(
        username='testuser',
        email='test@example.com',
        password='password123'
    )

    token1 = auth_manager.create_session(user)
    token2 = auth_manager.create_session(user)

    # Expire one session
    session = db_session.query(UserSession).filter_by(id=token1).first()
    session.expires_at = datetime.utcnow() - timedelta(days=1)
    db_session.commit()

    active_sessions = auth_manager.get_active_sessions(user)

    assert len(active_sessions) == 1
    assert active_sessions[0].id == token2
