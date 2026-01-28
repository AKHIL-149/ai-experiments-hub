"""Authentication and session management"""

import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from .database import User, Session as SessionModel


class AuthManager:
    """Handle user authentication and session management"""

    def __init__(self, db_session: Session, session_ttl_days: int = 30):
        """
        Initialize authentication manager

        Args:
            db_session: Database session
            session_ttl_days: Session time-to-live in days (default: 30)
        """
        self.db = db_session
        self.session_ttl_days = session_ttl_days

    def register_user(
        self,
        username: str,
        email: str,
        password: str
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Register new user

        Args:
            username: Username (3-50 characters)
            email: Email address
            password: Password (min 8 characters)

        Returns:
            Tuple of (success, user, error_message)
        """
        # Validate input
        if len(username) < 3 or len(username) > 50:
            return False, None, "Username must be 3-50 characters"

        if len(password) < 8:
            return False, None, "Password must be at least 8 characters"

        if '@' not in email or '.' not in email:
            return False, None, "Invalid email format"

        # Check if username/email exists
        existing = self.db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing:
            return False, None, "Username or email already exists"

        # Hash password with bcrypt (12 rounds)
        password_hash = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt(rounds=12)
        )

        # Create user
        user = User(
            username=username,
            email=email,
            password_hash=password_hash.decode('utf-8')
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return True, user, None

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user by username/password

        Args:
            username: Username
            password: Password

        Returns:
            User object if successful, None otherwise
        """
        user = self.db.query(User).filter(User.username == username).first()

        if not user:
            return None

        # Verify password with bcrypt
        if bcrypt.checkpw(
            password.encode('utf-8'),
            user.password_hash.encode('utf-8')
        ):
            return user

        return None

    def create_session(self, user: User) -> str:
        """
        Create new session for user

        Args:
            user: User object

        Returns:
            Session token (32-byte URL-safe string)
        """
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=self.session_ttl_days)

        session = SessionModel(
            id=session_token,
            user_id=user.id,
            expires_at=expires_at
        )

        self.db.add(session)
        self.db.commit()

        return session_token

    def validate_session(self, session_token: str) -> Optional[User]:
        """
        Validate session token and return user

        Args:
            session_token: Session token to validate

        Returns:
            User if session valid, None otherwise
        """
        session = self.db.query(SessionModel).filter(
            SessionModel.id == session_token
        ).first()

        if not session:
            return None

        # Check expiration
        if session.expires_at < datetime.utcnow():
            self.db.delete(session)
            self.db.commit()
            return None

        # Update last accessed
        session.last_accessed = datetime.utcnow()
        self.db.commit()

        return session.user

    def delete_session(self, session_token: str) -> bool:
        """
        Delete (logout) session

        Args:
            session_token: Session token to delete

        Returns:
            True if deleted, False if not found
        """
        session = self.db.query(SessionModel).filter(
            SessionModel.id == session_token
        ).first()

        if session:
            self.db.delete(session)
            self.db.commit()
            return True

        return False

    def cleanup_expired_sessions(self):
        """Remove all expired sessions"""
        self.db.query(SessionModel).filter(
            SessionModel.expires_at < datetime.utcnow()
        ).delete()
        self.db.commit()
