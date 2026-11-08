"""
User model for authentication
"""

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from passlib.context import CryptContext

from src.core.database import Base


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserRole(str, enum.Enum):
    """User role enumeration"""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


GUEST_EMAIL_DOMAIN = "guest.local"
GUEST_USERNAME_PREFIX = "guest_"


class User(Base):
    """
    User model for authentication and authorization
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)

    # Role and status
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    # API usage tracking
    api_calls_count = Column(Integer, default=0, nullable=False)
    last_api_call = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against a hash

        Args:
            plain_password: Plain text password
            hashed_password: Hashed password from database

        Returns:
            bool: True if password matches
        """
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """
        Hash a password

        Args:
            password: Plain text password

        Returns:
            str: Hashed password
        """
        return pwd_context.hash(password)

    def check_password(self, password: str) -> bool:
        """
        Check if provided password matches user's password

        Args:
            password: Plain text password

        Returns:
            bool: True if password matches
        """
        return self.verify_password(password, self.hashed_password)

    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()

    def update_api_call(self):
        """Update API call tracking"""
        self.api_calls_count += 1
        self.last_api_call = datetime.utcnow()

    @property
    def is_guest(self) -> bool:
        """Guest accounts are throwaway: their email is in the reserved guest domain"""
        return (self.email or "").lower().endswith("@" + GUEST_EMAIL_DOMAIN)

    def is_admin(self) -> bool:
        """Check if user is admin"""
        return self.role == UserRole.ADMIN or self.is_superuser

    def can_create_tasks(self) -> bool:
        """Check if user can create tasks"""
        return self.is_active and self.role in [UserRole.ADMIN, UserRole.USER]

    def can_manage_agents(self) -> bool:
        """Check if user can manage agents"""
        return self.is_active and self.role == UserRole.ADMIN

    def to_dict(self) -> dict:
        """
        Convert user to dictionary (excluding password)

        Returns:
            dict: User data
        """
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role.value,
            'is_active': self.is_active,
            'is_superuser': self.is_superuser,
            'is_guest': self.is_guest,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'api_calls_count': self.api_calls_count
        }



class UserSession(Base):
    """
    One sign-in on one device.

    Every login (or guest start) creates a row; the access and refresh tokens carry its id, so signing
    out, or revoking a device from another device, ends that sign-in at once.
    """
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device = Column(String(120), nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    def is_active(self, now: datetime = None) -> bool:
        now = now or datetime.utcnow()
        return self.revoked_at is None and self.expires_at > now

    def to_dict(self, current_id: str = None) -> dict:
        return {
            'id': self.id,
            'device': self.device,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None,
            'current': self.id == current_id,
        }
