"""
Accounts: passwords, sign-in sessions and who the current request is from.

Sign-ins are random tokens in an HttpOnly cookie (a cookie, not a header, because the page loads thumbnails,
video frames and clip downloads through plain <img> and <a> tags that cannot send an Authorization header).
The database stores only the SHA-256 of a token, so a leaked database holds nothing a browser can replay.

Kept free of FastAPI so each rule can be tested alone.
"""

import hashlib
import hmac
import os
import re
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from src.core.config import settings
from src.models.user import GUEST_PREFIX, User, UserSession

COOKIE_NAME = "vu_session"
SESSION_TOUCH_SECONDS = 60  # last_seen_at is written at most this often

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
MIN_PASSWORD = 8
MAX_PASSWORD = 128


# ---------------------------------------------------------------------------
# Passwords (scrypt from the standard library: nothing extra to install)
# ---------------------------------------------------------------------------

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(digest) // 2
        )
        return hmac.compare_digest(actual.hex(), digest)
    except (ValueError, TypeError):
        return False


# A real hash to check against when the username does not exist, so "no such user" and "wrong password"
# take the same time and cannot be told apart.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_password_time(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def check_username(raw: str) -> str:
    """The stored form of a username, or ValueError saying what is wrong"""
    name = (raw or "").strip().lower()
    if not USERNAME_RE.match(name):
        raise ValueError("Username must be 3-32 characters: letters, numbers, dot, dash or underscore")
    if name.startswith(GUEST_PREFIX):
        raise ValueError(f"Usernames starting with '{GUEST_PREFIX}' are reserved")
    return name


def check_password(password: str) -> str:
    if not isinstance(password, str) or not (MIN_PASSWORD <= len(password) <= MAX_PASSWORD):
        raise ValueError(f"Password must be {MIN_PASSWORD}-{MAX_PASSWORD} characters")
    if not password.strip():
        raise ValueError("Password cannot be only spaces")
    return password


def clean_display_name(raw: Optional[str]) -> Optional[str]:
    text = re.sub(r"[\x00-\x1f\x7f]", "", raw or "").strip()
    return text[:80] or None


# ---------------------------------------------------------------------------
# Who is asking
# ---------------------------------------------------------------------------

@dataclass
class Caller:
    user_id: Optional[int]   # None only in single-user mode (REQUIRE_LOGIN=false)
    username: str
    is_admin: bool
    is_guest: bool
    session_id: Optional[str] = None


LOCAL_CALLER = Caller(user_id=None, username="local", is_admin=True, is_guest=False)

# Set by the sign-in gate for the length of one request (sync endpoints run in a thread that copies it)
_current_caller: ContextVar[Optional[Caller]] = ContextVar("current_caller", default=None)


def current_caller() -> Optional[Caller]:
    caller = _current_caller.get()
    if caller is None and not settings.require_login:
        return LOCAL_CALLER  # single-user mode: everyone is the local administrator, gate or no gate
    return caller


def set_current_caller(caller: Optional[Caller]):
    return _current_caller.set(caller)


def reset_current_caller(token) -> None:
    _current_caller.reset(token)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_lifetime(user: User) -> timedelta:
    days = timedelta(days=settings.session_days)
    return min(days, timedelta(hours=settings.guest_ttl_hours)) if user.is_guest else days


def start_session(db: Session, user: User, device: str = "", ip: str = "") -> str:
    """Create a sign-in for the user and return the token to put in the cookie"""
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(UserSession(
        id=_digest(token), user_id=user.id, device=(device or "")[:160] or None, ip_address=(ip or "")[:64] or None,
        created_at=now, last_seen_at=now, expires_at=now + session_lifetime(user),
    ))
    user.last_login_at = now
    db.commit()
    return token


def resolve_session(db: Session, token: str, touch: bool = True) -> Optional[Tuple[User, UserSession]]:
    """The user and sign-in a cookie token belongs to, or None when it is unknown, ended or expired"""
    if not token or len(token) > 200:
        return None
    session = db.query(UserSession).filter(UserSession.id == _digest(token)).first()
    if session is None or not session.is_live():
        return None
    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None or not user.is_active:
        return None
    if touch:
        now = datetime.utcnow()
        if (now - session.last_seen_at).total_seconds() >= SESSION_TOUCH_SECONDS:
            session.last_seen_at = now
            db.commit()
    return user, session


def end_session(db: Session, token: str) -> None:
    session = db.query(UserSession).filter(UserSession.id == _digest(token or "")).first()
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.utcnow()
        db.commit()


def caller_for(user: User, session: UserSession) -> Caller:
    return Caller(
        user_id=user.id, username=user.username, is_admin=bool(user.is_admin),
        is_guest=bool(user.is_guest), session_id=session.id,
    )


def configured_admins() -> set:
    return {n.strip().lower() for n in (settings.admin_usernames or "").split(",") if n.strip()}
