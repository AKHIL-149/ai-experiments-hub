"""Authentication, session management, and role-based access control"""

import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from .database import User, Session as SessionModel, UserRole


class AuthManager:
    """Handle user authentication, sessions, and RBAC"""

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
        role: UserRole = UserRole.USER
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Register new user

        Args:
            username: Username (3-50 characters)
            email: Email address
            password: Password (min 8 characters)
            role: User role (default: USER)

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
            password_hash=password_hash.decode('utf-8'),
            role=role,
            is_active=True,
            is_verified=False  # Require email verification in production
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return True, user, None

    def authenticate(
        self,
        username: str,
        password: str
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Authenticate user by username/password

        Args:
            username: Username
            password: Password

        Returns:
            Tuple of (success, user, error_message)
        """
        user = self.db.query(User).filter(User.username == username).first()

        if not user:
            return False, None, "Invalid username or password"

        # Check if user is active
        if not user.is_active:
            return False, None, "Account is deactivated"

        # Verify password with bcrypt
        try:
            if bcrypt.checkpw(
                password.encode('utf-8'),
                user.password_hash.encode('utf-8')
            ):
                return True, user, None
        except Exception:
            return False, None, "Invalid username or password"

        return False, None, "Invalid username or password"

    def create_session(
        self,
        user: User,
        ip_address: Optional[str] = None
    ) -> str:
        """
        Create new session for user

        Args:
            user: User object
            ip_address: Client IP address (optional)

        Returns:
            Session token (32-byte URL-safe string)
        """
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=self.session_ttl_days)

        session = SessionModel(
            id=session_token,
            user_id=user.id,
            expires_at=expires_at,
            ip_address=ip_address
        )

        self.db.add(session)
        self.db.commit()

        return session_token

    def validate_session(
        self,
        session_token: str
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Validate session token and return user

        Args:
            session_token: Session token to validate

        Returns:
            Tuple of (success, user, error_message)
        """
        if not session_token:
            return False, None, "No session token provided"

        session = self.db.query(SessionModel).filter(
            SessionModel.id == session_token
        ).first()

        if not session:
            return False, None, "Invalid session"

        # Check expiration
        if session.expires_at < datetime.utcnow():
            self.db.delete(session)
            self.db.commit()
            return False, None, "Session expired"

        # Check if user is still active
        if not session.user.is_active:
            self.db.delete(session)
            self.db.commit()
            return False, None, "Account is deactivated"

        # Update last accessed
        session.last_accessed = datetime.utcnow()
        self.db.commit()

        return True, session.user, None

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

    def delete_all_user_sessions(self, user_id: str) -> int:
        """
        Delete all sessions for a user (force logout)

        Args:
            user_id: User ID

        Returns:
            Number of sessions deleted
        """
        count = self.db.query(SessionModel).filter(
            SessionModel.user_id == user_id
        ).delete()
        self.db.commit()
        return count

    def cleanup_expired_sessions(self) -> int:
        """
        Remove all expired sessions

        Returns:
            Number of sessions deleted
        """
        count = self.db.query(SessionModel).filter(
            SessionModel.expires_at < datetime.utcnow()
        ).delete()
        self.db.commit()
        return count

    # Role-Based Access Control (RBAC)

    def has_role(self, user: User, required_role: UserRole) -> bool:
        """
        Check if user has required role or higher

        Role hierarchy: USER < MODERATOR < ADMIN

        Args:
            user: User object
            required_role: Required role

        Returns:
            True if user has sufficient role
        """
        role_hierarchy = {
            UserRole.USER: 1,
            UserRole.MODERATOR: 2,
            UserRole.ADMIN: 3
        }

        user_level = role_hierarchy.get(user.role, 0)
        required_level = role_hierarchy.get(required_role, 0)

        return user_level >= required_level

    def is_admin(self, user: User) -> bool:
        """Check if user is admin"""
        return user.role == UserRole.ADMIN

    def is_moderator(self, user: User) -> bool:
        """Check if user is moderator or higher"""
        return self.has_role(user, UserRole.MODERATOR)

    def update_user_role(
        self,
        admin_user: User,
        target_user_id: str,
        new_role: UserRole
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Update user role (admin only)

        Args:
            admin_user: Admin user making the change
            target_user_id: User ID to update
            new_role: New role to assign

        Returns:
            Tuple of (success, updated_user, error_message)
        """
        # Verify admin permissions
        if not self.is_admin(admin_user):
            return False, None, "Insufficient permissions"

        # Get target user
        target_user = self.db.query(User).filter(
            User.id == target_user_id
        ).first()

        if not target_user:
            return False, None, "User not found"

        # Prevent self-demotion
        if admin_user.id == target_user_id and new_role != UserRole.ADMIN:
            return False, None, "Cannot change your own admin role"

        # Update role
        target_user.role = new_role
        target_user.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(target_user)

        return True, target_user, None

    def deactivate_user(
        self,
        admin_user: User,
        target_user_id: str
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Deactivate user account (admin only)

        Args:
            admin_user: Admin user making the change
            target_user_id: User ID to deactivate

        Returns:
            Tuple of (success, updated_user, error_message)
        """
        # Verify admin permissions
        if not self.is_admin(admin_user):
            return False, None, "Insufficient permissions"

        # Get target user
        target_user = self.db.query(User).filter(
            User.id == target_user_id
        ).first()

        if not target_user:
            return False, None, "User not found"

        # Prevent self-deactivation
        if admin_user.id == target_user_id:
            return False, None, "Cannot deactivate your own account"

        # Deactivate and logout
        target_user.is_active = False
        target_user.updated_at = datetime.utcnow()
        self.db.commit()

        # Delete all sessions
        self.delete_all_user_sessions(target_user_id)

        self.db.refresh(target_user)
        return True, target_user, None

    def reactivate_user(
        self,
        admin_user: User,
        target_user_id: str
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Reactivate user account (admin only)

        Args:
            admin_user: Admin user making the change
            target_user_id: User ID to reactivate

        Returns:
            Tuple of (success, updated_user, error_message)
        """
        # Verify admin permissions
        if not self.is_admin(admin_user):
            return False, None, "Insufficient permissions"

        # Get target user
        target_user = self.db.query(User).filter(
            User.id == target_user_id
        ).first()

        if not target_user:
            return False, None, "User not found"

        # Reactivate
        target_user.is_active = True
        target_user.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(target_user)

        return True, target_user, None

    def change_password(
        self,
        user: User,
        old_password: str,
        new_password: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Change user password

        Args:
            user: User object
            old_password: Current password
            new_password: New password

        Returns:
            Tuple of (success, error_message)
        """
        # Verify old password
        try:
            if not bcrypt.checkpw(
                old_password.encode('utf-8'),
                user.password_hash.encode('utf-8')
            ):
                return False, "Current password is incorrect"
        except Exception:
            return False, "Current password is incorrect"

        # Validate new password
        if len(new_password) < 8:
            return False, "New password must be at least 8 characters"

        # Hash new password
        password_hash = bcrypt.hashpw(
            new_password.encode('utf-8'),
            bcrypt.gensalt(rounds=12)
        )

        # Update password
        user.password_hash = password_hash.decode('utf-8')
        user.updated_at = datetime.utcnow()
        self.db.commit()

        # Force logout all sessions except current one
        # (implementation would require passing current session_token)

        return True, None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self.db.query(User).filter(User.username == username).first()

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return self.db.query(User).filter(User.email == email).first()

    def list_users(
        self,
        admin_user: User,
        offset: int = 0,
        limit: int = 50
    ) -> Tuple[bool, Optional[List[User]], Optional[str]]:
        """
        List all users (admin only)

        Args:
            admin_user: Admin user making the request
            offset: Pagination offset
            limit: Pagination limit (max 100)

        Returns:
            Tuple of (success, users, error_message)
        """
        # Verify admin permissions
        if not self.is_admin(admin_user):
            return False, None, "Insufficient permissions"

        # Cap limit
        limit = min(limit, 100)

        users = self.db.query(User).order_by(
            User.created_at.desc()
        ).offset(offset).limit(limit).all()

        return True, users, None

    def get_active_sessions(
        self,
        user: User
    ) -> List[SessionModel]:
        """
        Get all active sessions for user

        Args:
            user: User object

        Returns:
            List of active sessions
        """
        return self.db.query(SessionModel).filter(
            SessionModel.user_id == user.id,
            SessionModel.expires_at > datetime.utcnow()
        ).order_by(SessionModel.last_accessed.desc()).all()
