"""
Accounts and sign-ins.

A sign-in is a row in user_sessions whose id is the SHA-256 of the random token held in the browser's
cookie, so a stolen database never contains a usable token, and signing out (or removing a guest) ends
the sign-in at once.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.core.database import Base

GUEST_PREFIX = "guest-"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    # stored lower-cased: "Ann" and "ann" are the same account
    username = Column(String(40), unique=True, nullable=False, index=True)
    display_name = Column(String(80), nullable=True)
    password_hash = Column(String(255), nullable=False)
    is_guest = Column(Boolean, nullable=False, default=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    sessions = relationship("UserSession", cascade="all, delete-orphan", passive_deletes=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name or self.username,
            "is_guest": bool(self.is_guest),
            "is_admin": bool(self.is_admin),
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(String(64), primary_key=True)  # sha256 hex of the cookie token
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device = Column(String(160), nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    def is_live(self, now: datetime = None) -> bool:
        return self.revoked_at is None and self.expires_at > (now or datetime.utcnow())
