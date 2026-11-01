"""Authentication and session management"""

import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session
from .database import User, Session as SessionModel

# bcrypt only uses the first 72 bytes of a password. Longer ones used to be accepted and then
# silently truncated, so a password and the same password plus any suffix both logged in.
MAX_PASSWORD_BYTES = 72

# Hash of a throwaway password, checked when the username does not exist so that an unknown
# user and a wrong password take equally long (login timing otherwise tells which usernames exist).
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=12))


def _generate_guest_credentials() -> Tuple[str, str, str]:
    """Random username/email/password for a temporary guest account."""
    suffix = secrets.token_hex(6)
    username = f"guest_{suffix}"
    email = f"{username}@guest.local"
    password = secrets.token_urlsafe(24)
    return username, email, password


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
        password: str,
        is_guest: bool = False
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Register new user

        Args:
            username: Username (3-50 characters)
            email: Email address
            password: Password (min 8 characters)
            is_guest: Mark this account as a temporary guest account

        Returns:
            Tuple of (success, user, error_message)
        """
        # Validate input. Surrounding spaces are never part of a name ("   " used to be a valid
        # username, and "alice " a second account that looks like "alice").
        username = username.strip()
        email = email.strip()

        if len(username) < 3 or len(username) > 50:
            return False, None, "Username must be 3-50 characters"

        if any(ord(ch) < 32 or ord(ch) == 127 for ch in username):
            return False, None, "Username cannot contain control characters"

        if len(password) < 8:
            return False, None, "Password must be at least 8 characters"

        if len(password.encode('utf-8')) > MAX_PASSWORD_BYTES:
            return False, None, f"Password must be at most {MAX_PASSWORD_BYTES} bytes (fewer characters if it has accents or emoji)"

        if '@' not in email or '.' not in email or len(email) > 100:
            return False, None, "Invalid email format"

        # Check if username/email exists. Case-insensitive: "ALICE" next to "alice" is
        # indistinguishable from the real one to anyone reading a conversation list.
        existing = self.db.query(User).filter(
            (func.lower(User.username) == username.lower()) | (func.lower(User.email) == email.lower())
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
            password_hash=password_hash.decode('utf-8'),
            is_guest=is_guest
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return True, user, None

    def create_guest_user(self) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Create and register a temporary guest account - no signup form
        required. Uses a random username/email/password (the password
        is never given back to the caller; the guest is logged in via
        create_session() the same way a normal login would be).

        Returns:
            Tuple of (success, user, error_message)
        """
        # Vanishingly unlikely, but register_user() rejects a
        # username/email collision rather than retrying - collide once
        # against secrets.token_hex(6) and try again with a fresh one.
        for _ in range(3):
            username, email, password = _generate_guest_credentials()
            success, user, error = self.register_user(username, email, password, is_guest=True)
            if success:
                return True, user, None

        return False, None, "Failed to create guest account"

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
        password_bytes = password.encode('utf-8')[:MAX_PASSWORD_BYTES]

        if not user:
            bcrypt.checkpw(password_bytes, _DUMMY_HASH)  # same work as a real check
            return None

        # Verify password with bcrypt (truncated like bcrypt itself did when the hash was made,
        # so accounts created before the length limit still log in)
        if bcrypt.checkpw(password_bytes, user.password_hash.encode('utf-8')):
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
