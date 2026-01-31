"""
Authentication and session management for Research Assistant.

Provides user registration, login, and session-based authentication
using bcrypt for password hashing.
"""

import secrets
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
import bcrypt
from sqlalchemy.orm import Session
from .database import User, UserSession


class AuthManager:
    """Manages user authentication and sessions."""

    def __init__(self, session_ttl_days: int = 30):
        """
        Initialize authentication manager.

        Args:
            session_ttl_days: Number of days before session expires (default: 30)
        """
        self.session_ttl_days = session_ttl_days

    def register_user(
        self,
        db_session: Session,
        username: str,
        email: str,
        password: str
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Register a new user.

        Args:
            db_session: Database session
            username: Username (3-50 characters, alphanumeric + underscore)
            email: Email address
            password: Password (minimum 8 characters)

        Returns:
            Tuple of (success, user, error_message)
        """
        # Validate username
        if not username or len(username) < 3 or len(username) > 50:
            return False, None, "Username must be 3-50 characters"

        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return False, None, "Username can only contain letters, numbers, and underscores"

        # Validate email
        if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            return False, None, "Invalid email address"

        # Validate password
        if not password or len(password) < 8:
            return False, None, "Password must be at least 8 characters"

        # Check if username already exists
        existing_user = db_session.query(User).filter(User.username == username).first()
        if existing_user:
            return False, None, "Username already exists"

        # Check if email already exists
        existing_email = db_session.query(User).filter(User.email == email).first()
        if existing_email:
            return False, None, "Email already registered"

        # Hash password with bcrypt (12 rounds)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))

        # Create user
        user = User(
            username=username,
            email=email,
            password_hash=password_hash.decode('utf-8')
        )

        try:
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            return True, user, None
        except Exception as e:
            db_session.rollback()
            return False, None, f"Failed to create user: {str(e)}"

    def authenticate(
        self,
        db_session: Session,
        username: str,
        password: str
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Authenticate user with username and password.

        Args:
            db_session: Database session
            username: Username
            password: Password

        Returns:
            Tuple of (success, user, error_message)
        """
        # Find user
        user = db_session.query(User).filter(User.username == username).first()

        if not user:
            return False, None, "Invalid username or password"

        # Verify password
        password_matches = bcrypt.checkpw(
            password.encode('utf-8'),
            user.password_hash.encode('utf-8')
        )

        if not password_matches:
            return False, None, "Invalid username or password"

        return True, user, None

    def create_session(
        self,
        db_session: Session,
        user: User
    ) -> Tuple[bool, Optional[UserSession], Optional[str]]:
        """
        Create a new session for user.

        Args:
            db_session: Database session
            user: User object

        Returns:
            Tuple of (success, session, error_message)
        """
        # Generate secure random token (32 bytes = 256 bits)
        token = secrets.token_urlsafe(32)

        # Calculate expiration
        expires_at = datetime.utcnow() + timedelta(days=self.session_ttl_days)

        # Create session
        session = UserSession(
            id=token,
            user_id=user.id,
            expires_at=expires_at
        )

        try:
            db_session.add(session)
            db_session.commit()
            db_session.refresh(session)
            return True, session, None
        except Exception as e:
            db_session.rollback()
            return False, None, f"Failed to create session: {str(e)}"

    def validate_session(
        self,
        db_session: Session,
        token: str
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Validate session token and return user.

        Args:
            db_session: Database session
            token: Session token

        Returns:
            Tuple of (valid, user, error_message)
        """
        # Find session
        session = db_session.query(UserSession).filter(UserSession.id == token).first()

        if not session:
            return False, None, "Invalid session token"

        # Check expiration
        if session.is_expired():
            # Delete expired session
            db_session.delete(session)
            db_session.commit()
            return False, None, "Session expired"

        # Update last accessed time
        session.last_accessed = datetime.utcnow()
        db_session.commit()

        # Get user
        user = db_session.query(User).filter(User.id == session.user_id).first()

        if not user:
            return False, None, "User not found"

        return True, user, None

    def delete_session(
        self,
        db_session: Session,
        token: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Delete a session (logout).

        Args:
            db_session: Database session
            token: Session token

        Returns:
            Tuple of (success, error_message)
        """
        session = db_session.query(UserSession).filter(UserSession.id == token).first()

        if not session:
            return False, "Session not found"

        try:
            db_session.delete(session)
            db_session.commit()
            return True, None
        except Exception as e:
            db_session.rollback()
            return False, f"Failed to delete session: {str(e)}"

    def cleanup_expired_sessions(
        self,
        db_session: Session
    ) -> int:
        """
        Remove all expired sessions.

        Args:
            db_session: Database session

        Returns:
            Number of sessions deleted
        """
        now = datetime.utcnow()
        expired_sessions = db_session.query(UserSession).filter(
            UserSession.expires_at < now
        ).all()

        count = len(expired_sessions)

        for session in expired_sessions:
            db_session.delete(session)

        if count > 0:
            db_session.commit()

        return count

    def get_user_sessions(
        self,
        db_session: Session,
        user_id: str,
        include_expired: bool = False
    ) -> list:
        """
        Get all sessions for a user.

        Args:
            db_session: Database session
            user_id: User ID
            include_expired: Whether to include expired sessions

        Returns:
            List of UserSession objects
        """
        query = db_session.query(UserSession).filter(UserSession.user_id == user_id)

        if not include_expired:
            query = query.filter(UserSession.expires_at >= datetime.utcnow())

        return query.order_by(UserSession.created_at.desc()).all()

    def revoke_all_user_sessions(
        self,
        db_session: Session,
        user_id: str
    ) -> int:
        """
        Revoke all sessions for a user (force logout everywhere).

        Args:
            db_session: Database session
            user_id: User ID

        Returns:
            Number of sessions deleted
        """
        sessions = db_session.query(UserSession).filter(UserSession.user_id == user_id).all()

        count = len(sessions)

        for session in sessions:
            db_session.delete(session)

        if count > 0:
            db_session.commit()

        return count

    def update_password(
        self,
        db_session: Session,
        user: User,
        old_password: str,
        new_password: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Update user password (requires old password verification).

        Args:
            db_session: Database session
            user: User object
            old_password: Current password
            new_password: New password

        Returns:
            Tuple of (success, error_message)
        """
        # Verify old password
        password_matches = bcrypt.checkpw(
            old_password.encode('utf-8'),
            user.password_hash.encode('utf-8')
        )

        if not password_matches:
            return False, "Current password is incorrect"

        # Validate new password
        if len(new_password) < 8:
            return False, "New password must be at least 8 characters"

        # Hash new password
        new_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(rounds=12))

        # Update password
        user.password_hash = new_hash.decode('utf-8')
        user.updated_at = datetime.utcnow()

        try:
            db_session.commit()
            return True, None
        except Exception as e:
            db_session.rollback()
            return False, f"Failed to update password: {str(e)}"
