"""Tests for GitHub authentication integration"""
import pytest
from unittest.mock import Mock, patch
from src.core.database import DatabaseManager, User, UserRole


@pytest.fixture
def db_manager():
    """Create test database manager"""
    return DatabaseManager('sqlite:///:memory:')


@pytest.fixture
def test_user(db_manager):
    """Create a test user"""
    with db_manager.get_session() as db:
        user = User(
            username='testuser',
            email='test@example.com',
            password_hash='hashed_password',
            role=UserRole.USER
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def test_user_github_token_field(db_manager, test_user):
    """Test that User model has github_token field"""
    with db_manager.get_session() as db:
        user = db.query(User).filter(User.id == test_user.id).first()

        # Field should exist and be None initially
        assert hasattr(user, 'github_token')
        assert user.github_token is None


def test_set_github_token(db_manager, test_user):
    """Test setting GitHub token on user"""
    test_token = "ghp_test_token_12345"

    with db_manager.get_session() as db:
        user = db.query(User).filter(User.id == test_user.id).first()
        user.github_token = test_token
        db.commit()
        db.refresh(user)

        assert user.github_token == test_token


def test_update_github_token(db_manager, test_user):
    """Test updating existing GitHub token"""
    old_token = "ghp_old_token"
    new_token = "ghp_new_token"

    with db_manager.get_session() as db:
        # Set initial token
        user = db.query(User).filter(User.id == test_user.id).first()
        user.github_token = old_token
        db.commit()

        # Update token
        user.github_token = new_token
        db.commit()
        db.refresh(user)

        assert user.github_token == new_token


def test_remove_github_token(db_manager, test_user):
    """Test removing GitHub token"""
    with db_manager.get_session() as db:
        # Set token
        user = db.query(User).filter(User.id == test_user.id).first()
        user.github_token = "ghp_token"
        db.commit()

        # Remove token
        user.github_token = None
        db.commit()
        db.refresh(user)

        assert user.github_token is None


def test_github_token_persistence(db_manager, test_user):
    """Test that GitHub token persists across sessions"""
    test_token = "ghp_persistent_token"

    # Set token in one session
    with db_manager.get_session() as db:
        user = db.query(User).filter(User.id == test_user.id).first()
        user.github_token = test_token
        db.commit()

    # Retrieve in another session
    with db_manager.get_session() as db:
        user = db.query(User).filter(User.id == test_user.id).first()
        assert user.github_token == test_token


def test_multiple_users_different_tokens(db_manager):
    """Test that different users can have different tokens"""
    with db_manager.get_session() as db:
        user1 = User(
            username='user1',
            email='user1@test.com',
            password_hash='hash1',
            github_token='token1'
        )
        user2 = User(
            username='user2',
            email='user2@test.com',
            password_hash='hash2',
            github_token='token2'
        )

        db.add_all([user1, user2])
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        assert user1.github_token == 'token1'
        assert user2.github_token == 'token2'
        assert user1.github_token != user2.github_token


def test_user_without_github_token(db_manager):
    """Test user can exist without GitHub token"""
    with db_manager.get_session() as db:
        user = User(
            username='notoken',
            email='notoken@test.com',
            password_hash='hash'
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.github_token is None


def test_github_token_max_length(db_manager, test_user):
    """Test that GitHub token field can store long tokens"""
    # GitHub tokens can be quite long (e.g., 255+ chars)
    long_token = "ghp_" + "x" * 400

    with db_manager.get_session() as db:
        user = db.query(User).filter(User.id == test_user.id).first()
        user.github_token = long_token
        db.commit()
        db.refresh(user)

        assert user.github_token == long_token
        assert len(user.github_token) > 400


def test_github_service_with_user_token(db_manager, test_user):
    """Test using GitHub service with user's token"""
    test_token = "ghp_valid_token"

    with db_manager.get_session() as db:
        user = db.query(User).filter(User.id == test_user.id).first()
        user.github_token = test_token
        db.commit()
        db.refresh(user)

    # Retrieve and use token
    with db_manager.get_session() as db:
        user = db.query(User).filter(User.id == test_user.id).first()

        with patch('src.services.github_service.Github') as mock_github:
            mock_user_obj = Mock()
            mock_user_obj.login = "testuser"

            mock_client = Mock()
            mock_client.get_user.return_value = mock_user_obj
            mock_github.return_value = mock_client

            from src.services.github_service import GitHubService

            # Should be able to create service with user's token
            service = GitHubService(github_token=user.github_token)
            assert service.token == test_token


def test_user_to_dict_excludes_github_token(db_manager, test_user):
    """Test that to_dict() doesn't expose GitHub token"""
    with db_manager.get_session() as db:
        user = db.query(User).filter(User.id == test_user.id).first()
        user.github_token = "ghp_secret_token"
        db.commit()

        user_dict = user.to_dict()

        # Token should not be in dict (security)
        assert 'github_token' not in user_dict
        assert 'password_hash' not in user_dict


def test_github_token_optional_field(db_manager):
    """Test that github_token is truly optional"""
    with db_manager.get_session() as db:
        # Create user without specifying github_token
        user = User(
            username='optional',
            email='optional@test.com',
            password_hash='hash',
            role=UserRole.USER,
            is_active=True
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        # Should succeed without github_token
        assert user.id is not None
        assert user.github_token is None
