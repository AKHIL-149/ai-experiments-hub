"""Accounts: passwords, sign-in sessions and who the current request is from.

Sign-ins are random tokens in an HttpOnly cookie. The database stores only the SHA-256 of a token, so a leaked
database holds nothing a browser can replay. Kept free of FastAPI so each rule can be tested alone.
"""
import hashlib
import hmac
import os
import re
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.models.user import GUEST_PREFIX, User, UserSession

COOKIE_NAME = "kg_session"
SESSION_TOUCH_SECONDS = 60       # last_seen_at is written at most this often
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
MIN_PASSWORD, MAX_PASSWORD = 8, 128

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
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(digest) // 2)
        return hmac.compare_digest(actual.hex(), digest)
    except (ValueError, TypeError):
        return False


# A real hash to check against when the username does not exist, so "no such user" and "wrong password" take the
# same time and cannot be told apart.
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


# ---------------------------------------------------------------- who is asking

@dataclass
class Caller:
    user_id: Optional[int]      # None only in single-user mode (REQUIRE_LOGIN=false)
    username: str
    is_guest: bool
    session_id: Optional[str] = None


LOCAL_CALLER = Caller(user_id=None, username="local", is_guest=False)

# Set by the sign-in gate for the length of one request
_current_caller: ContextVar[Optional[Caller]] = ContextVar("current_caller", default=None)


def current_caller() -> Optional[Caller]:
    caller = _current_caller.get()
    if caller is None and not get_settings().require_login:
        return LOCAL_CALLER  # single-user mode: everyone is the local user, gate or no gate
    return caller


def set_current_caller(caller: Optional[Caller]):
    return _current_caller.set(caller)


def reset_current_caller(token) -> None:
    _current_caller.reset(token)


# ---------------------------------------------------------------- sessions

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_lifetime(user: User) -> timedelta:
    s = get_settings()
    days = timedelta(days=s.session_days)
    return min(days, timedelta(hours=s.guest_ttl_hours)) if user.is_guest else days


def start_session(db: Session, user: User, device: str = "", ip: str = "") -> str:
    """Create a sign-in for the user and return the token to put in the cookie"""
    token = secrets.token_urlsafe(32)
    now = _now()
    db.add(UserSession(id=_digest(token), user_id=user.id, device=(device or "")[:160] or None, ip_address=(ip or "")[:64] or None,
                       created_at=now, last_seen_at=now, expires_at=now + session_lifetime(user)))
    user.last_login_at = now
    db.commit()
    return token


def resolve_session(db: Session, token: str, touch: bool = True):
    """(user, session) a cookie token belongs to, or None when it is unknown, ended, expired or the user is disabled"""
    if not token or len(token) > 200:
        return None
    session = db.get(UserSession, _digest(token))
    if session is None or not session.is_live():
        return None
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None
    if touch and (_now() - _aware(session.last_seen_at)).total_seconds() >= SESSION_TOUCH_SECONDS:
        session.last_seen_at = _now()
        db.commit()
    return user, session


def end_session(db: Session, token: str) -> None:
    session = db.get(UserSession, _digest(token or ""))
    if session is not None and session.revoked_at is None:
        session.revoked_at = _now()
        db.commit()


def caller_for(user: User, session: UserSession) -> Caller:
    return Caller(user_id=user.id, username=user.username, is_guest=bool(user.is_guest), session_id=session.id)
