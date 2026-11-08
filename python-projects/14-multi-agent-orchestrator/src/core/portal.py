"""
Sign-in portal: accounts, guests, device sessions and who is online right now

Everything here is per installation. Each clone of the repository has its own database and its own
signing key, so the people who reach one running copy (from their own devices) have accounts in that copy
and nowhere else.
"""

import asyncio
import os
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional

import anyio
from fastapi import Request, WebSocket
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from src.core.auth import AuthService, REFRESH_TOKEN_EXPIRE_DAYS, ACCESS_TOKEN_EXPIRE_MINUTES
from src.core.database import Base, SessionLocal, engine
from src.core.logging import logger
from src.models.task import Task
from src.models.user import (
    User, UserRole, UserSession, GUEST_EMAIL_DOMAIN, GUEST_USERNAME_PREFIX
)


# Settings -----------------------------------------------------------------------------------------

def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


# Without a signed-in account the API answers 401. REQUIRE_LOGIN=false turns the gate off (tests, or
# running the API as a private tool on one machine).
REQUIRE_LOGIN = _env_flag("REQUIRE_LOGIN", True)
# X-Forwarded-For is only believed behind a reverse proxy that sets it; anyone can send it otherwise
TRUST_PROXY = _env_flag("TRUST_PROXY", False)
GUEST_TTL_HOURS = int(os.getenv("GUEST_TTL_HOURS", "24"))
ADMIN_USERNAMES = {
    name.strip().lower() for name in os.getenv("ADMIN_USERNAMES", "").split(",") if name.strip()
}
MAX_PRESENCE_CONNECTIONS_PER_USER = 10

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,29}$")
MAX_PASSWORD_BYTES = 72  # bcrypt ignores everything past this, so a longer password is refused
MIN_PASSWORD_LENGTH = 8
NO_EMAIL_DOMAIN = "users.local"  # an account without an email gets <username>@users.local


# Small in-memory limiters ----------------------------------------------------------------------------

class AttemptLimiter:
    """Allows `max_attempts` per key in `window_seconds` (a restart forgets it, which is fine here)"""

    def __init__(self, max_attempts: int, window_seconds: int, clock=time.monotonic):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.clock = clock
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> Deque[float]:
        events = self._events.get(key)
        if events is None:
            return deque()
        while events and now - events[0] >= self.window:
            events.popleft()
        if not events:
            del self._events[key]
            return deque()
        return events

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may act again (0 if it may now)"""
        with self._lock:
            now = self.clock()
            events = self._recent(key, now)
            if len(events) < self.max_attempts:
                return 0
            return max(1, int(self.window - (now - events[0])) + 1)

    def record(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            self._recent(key, now)
            self._events.setdefault(key, deque()).append(now)
            if len(self._events) > 10000:  # bound memory under a flood of distinct keys
                self._events.pop(next(iter(self._events)))

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


login_failures_by_name = AttemptLimiter(max_attempts=5, window_seconds=15 * 60)
login_failures_by_ip = AttemptLimiter(max_attempts=int(os.getenv("LOGIN_FAILURES_PER_IP", "30")), window_seconds=15 * 60)
signups_by_ip = AttemptLimiter(max_attempts=int(os.getenv("SIGNUPS_PER_HOUR", "10")), window_seconds=60 * 60)
guests_by_ip = AttemptLimiter(max_attempts=int(os.getenv("GUESTS_PER_5_MINUTES", "10")), window_seconds=5 * 60)


def client_ip(connection) -> str:
    """The caller's address. X-Forwarded-For only counts when TRUST_PROXY says a proxy sets it."""
    if TRUST_PROXY:
        forwarded = connection.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return connection.client.host if connection.client else "unknown"


def describe_device(user_agent: Optional[str]) -> str:
    """A short label for a device from its User-Agent, e.g. 'Chrome on macOS'"""
    ua = user_agent or ""
    if not ua:
        return "Unknown device"
    if "Edg/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua or "CriOS/" in ua:
        browser = "Chrome"
    elif "Safari/" in ua:
        browser = "Safari"
    elif ua.lower().startswith(("curl", "python", "httpx", "postman")):
        browser = ua.split("/")[0][:30]
    else:
        browser = "Browser"
    if "iPhone" in ua:
        system = "iPhone"
    elif "iPad" in ua:
        system = "iPad"
    elif "Android" in ua:
        system = "Android"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        system = "macOS"
    elif "Windows" in ua:
        system = "Windows"
    elif "CrOS" in ua:
        system = "ChromeOS"
    elif "Linux" in ua:
        system = "Linux"
    else:
        system = None
    return f"{browser} on {system}" if system else browser


# Validation ----------------------------------------------------------------------------------------

def validate_username(username: str) -> str:
    username = (username or "").strip()
    if not USERNAME_PATTERN.match(username):
        raise ValueError(
            "Username must be 3-30 characters: letters, numbers, dots, dashes and underscores"
        )
    if username.lower().startswith(GUEST_USERNAME_PREFIX):
        raise ValueError(f"Usernames starting with '{GUEST_USERNAME_PREFIX}' are reserved for guests")
    return username


def validate_password(password: str) -> str:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    return password


def normalize_email(email: Optional[str], username: str) -> str:
    """The email to store: the given one lower-cased, or <username>@users.local when none was given"""
    email = (email or "").strip().lower()
    if not email:
        return f"{username.lower()}@{NO_EMAIL_DOMAIN}"
    if email.endswith("@" + GUEST_EMAIL_DOMAIN) or email.endswith("@" + NO_EMAIL_DOMAIN):
        raise ValueError("That email domain is reserved")
    return email


# Accounts ------------------------------------------------------------------------------------------

_DUMMY_HASH = User.get_password_hash("not-a-real-password")


def find_user(db: Session, identifier: str) -> Optional[User]:
    """Look an account up by username or email, ignoring case"""
    identifier = (identifier or "").strip().lower()
    if not identifier:
        return None
    return db.query(User).filter(
        (func.lower(User.username) == identifier) | (func.lower(User.email) == identifier)
    ).first()


def authenticate(db: Session, identifier: str, password: str) -> Optional[User]:
    """Check a password. An unknown account costs the same time as a wrong password."""
    user = find_user(db, identifier)
    if user is None:
        User.verify_password(password or "", _DUMMY_HASH)
        return None
    if len((password or "").encode("utf-8")) > MAX_PASSWORD_BYTES:
        return None
    if not user.check_password(password):
        return None
    if not user.is_active or user.is_guest:  # guests have no password to sign in with
        return None
    return user


def apply_admin_list(user: User) -> None:
    """Accounts named in ADMIN_USERNAMES get the admin role (so the first admin needs no database edit)"""
    if user.username.lower() in ADMIN_USERNAMES and not user.is_guest and user.role != UserRole.ADMIN:
        user.role = UserRole.ADMIN


def create_user(db: Session, username: str, password: str, email: Optional[str], full_name: Optional[str]) -> User:
    """Create a regular account; ValueError says what is wrong (bad username/password, name taken)"""
    username = validate_username(username)
    validate_password(password)
    email = normalize_email(email, username)

    if db.query(User).filter(func.lower(User.username) == username.lower()).first():
        raise ValueError("Username already taken")
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise ValueError("Email already registered")

    user = User(
        username=username,
        email=email,
        hashed_password=User.get_password_hash(password),
        full_name=(full_name or "").strip()[:100] or None,
        role=UserRole.USER,
        is_active=True,
    )
    apply_admin_list(user)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_guest_user(db: Session) -> User:
    """A throwaway account that needs no password, deleted after GUEST_TTL_HOURS of inactivity"""
    for _ in range(5):
        username = f"{GUEST_USERNAME_PREFIX}{uuid.uuid4().hex[:8]}"
        if not db.query(User).filter(User.username == username).first():
            break
    user = User(
        username=username,
        email=f"{username}@{GUEST_EMAIL_DOMAIN}",
        hashed_password=User.get_password_hash(uuid.uuid4().hex),  # nobody knows it
        full_name="Guest",
        role=UserRole.USER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def purge_expired_guests(db: Session, ttl_hours: int = None) -> int:
    """Delete guests (and their sessions and tasks) idle for longer than the TTL; returns how many"""
    cutoff = datetime.utcnow() - timedelta(hours=GUEST_TTL_HOURS if ttl_hours is None else ttl_hours)
    guests = db.query(User).filter(User.email.like(f"%@{GUEST_EMAIL_DOMAIN}")).all()
    purged = 0
    for guest in guests:
        last_seen = db.query(func.max(UserSession.last_seen_at)).filter(
            UserSession.user_id == guest.id
        ).scalar() or guest.created_at
        if last_seen >= cutoff or presence.is_online(guest.id):
            continue
        db.query(UserSession).filter(UserSession.user_id == guest.id).delete()
        for task in db.query(Task).filter(Task.created_by_user_id == guest.id).all():
            db.delete(task)
        db.delete(guest)
        purged += 1
    if purged:
        db.commit()
        logger.info(f"Removed {purged} expired guest account(s)")
    return purged


# Sessions ------------------------------------------------------------------------------------------

def start_session(db: Session, user: User, request: Request) -> Dict[str, Any]:
    """Record a sign-in on this device and return the tokens that belong to it"""
    now = datetime.utcnow()
    session = UserSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        device=describe_device(request.headers.get("user-agent"))[:120],
        ip_address=client_ip(request),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    user.update_last_login()
    db.add(session)
    db.commit()
    claims = {"sub": user.id, "sid": session.id}
    return {
        "access_token": AuthService.create_access_token(claims),
        "refresh_token": AuthService.create_refresh_token(claims),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "session_id": session.id,
        "user": user.to_dict(),
    }


def end_session(db: Session, session: UserSession) -> None:
    """Revoke one sign-in and cut its live connections"""
    if session.revoked_at is None:
        session.revoked_at = datetime.utcnow()
        db.commit()
    publish(presence.disconnect_session(session.id))


def end_other_sessions(db: Session, user_id: int, keep_session_id: Optional[str]) -> int:
    query = db.query(UserSession).filter(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if keep_session_id:
        query = query.filter(UserSession.id != keep_session_id)
    sessions = query.all()
    for session in sessions:
        session.revoked_at = datetime.utcnow()
    db.commit()
    for session in sessions:
        publish(presence.disconnect_session(session.id))
    return len(sessions)


def purge_old_sessions(db: Session, keep_days: int = 30) -> int:
    """Forget sessions that expired or were revoked long ago"""
    cutoff = datetime.utcnow() - timedelta(days=keep_days)
    deleted = db.query(UserSession).filter(
        (UserSession.expires_at < cutoff) | (UserSession.revoked_at < cutoff)
    ).delete(synchronize_session=False)
    db.commit()
    return deleted


# Real time -----------------------------------------------------------------------------------------

def publish(coroutine) -> None:
    """
    Run a presence coroutine from either place the portal is called from: a sync endpoint (runs in a
    worker thread, so hand the coroutine to the event loop) or code already on the event loop.
    """
    try:
        anyio.from_thread.run(lambda: coroutine)
        return
    except RuntimeError:
        pass
    try:
        asyncio.get_running_loop().create_task(coroutine)
    except RuntimeError:
        coroutine.close()  # no loop at all (a script or a test): nobody is connected anyway


@dataclass
class Connection:
    websocket: WebSocket
    user_id: int
    username: str
    is_guest: bool
    session_id: str
    since: str


class PresenceManager:
    """
    Who is online, kept in memory: the live WebSocket connections, grouped by account.

    One process holds all connections, which is how the app runs (one uvicorn worker). Behind several
    workers each would only know its own connections.
    """

    def __init__(self):
        self.connections: Dict[str, Connection] = {}
        self.activity: Deque[Dict[str, Any]] = deque(maxlen=20)

    # state
    def is_online(self, user_id: int) -> bool:
        return any(c.user_id == user_id for c in self.connections.values())

    def connection_count(self, user_id: int) -> int:
        return sum(1 for c in self.connections.values() if c.user_id == user_id)

    def online_users(self) -> List[Dict[str, Any]]:
        users: Dict[int, Dict[str, Any]] = {}
        for connection in self.connections.values():
            entry = users.setdefault(connection.user_id, {
                "id": connection.user_id,
                "username": connection.username,
                "is_guest": connection.is_guest,
                "since": connection.since,
                "devices": 0,
            })
            entry["devices"] += 1
            entry["since"] = min(entry["since"], connection.since)
        return sorted(users.values(), key=lambda u: (u["is_guest"], u["username"].lower()))

    def snapshot(self) -> Dict[str, Any]:
        users = self.online_users()
        return {
            "type": "presence",
            "online": users,
            "count": len(users),
            "guests": sum(1 for u in users if u["is_guest"]),
            "activity": list(self.activity),
        }

    def with_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """The current snapshot plus the event that changed it (clients render both)"""
        return {**self.snapshot(), "type": "activity", "event": event}

    # events
    def record_activity(self, kind: str, username: str, is_guest: bool) -> Dict[str, Any]:
        event = {
            "kind": kind,
            "username": username,
            "is_guest": is_guest,
            "at": datetime.utcnow().isoformat() + "Z",
        }
        self.activity.append(event)
        return event

    async def announce(self, kind: str, username: str, is_guest: bool) -> None:
        """Somebody signed in / out / created an account: tell everyone connected"""
        event = self.record_activity(kind, username, is_guest)
        await self.broadcast(self.with_event(event))

    async def broadcast(self, message: Dict[str, Any]) -> None:
        for connection_id, connection in list(self.connections.items()):
            try:
                await connection.websocket.send_json(message)
            except Exception:
                self.connections.pop(connection_id, None)

    async def broadcast_presence(self) -> None:
        await self.broadcast(self.snapshot())

    def register(self, connection_id: str, connection: Connection) -> Dict[str, Any]:
        """Add a connection; returns the message to broadcast to everyone (send the newcomer's own
        'ready' first, so it never sees the broadcast before it knows who it is)"""
        was_online = self.is_online(connection.user_id)
        self.connections[connection_id] = connection
        if not was_online:
            return self.with_event(self.record_activity("online", connection.username, connection.is_guest))
        return self.snapshot()

    async def remove(self, connection_id: str) -> None:
        connection = self.connections.pop(connection_id, None)
        if connection is None:
            return
        if not self.is_online(connection.user_id):
            event = self.record_activity("offline", connection.username, connection.is_guest)
            await self.broadcast(self.with_event(event))
        else:
            await self.broadcast_presence()

    async def rename_user(self, user_id: int, username: str, is_guest: bool) -> None:
        """A guest became a real account: show the new name to everyone"""
        for connection in self.connections.values():
            if connection.user_id == user_id:
                connection.username = username
                connection.is_guest = is_guest
        await self.broadcast_presence()

    async def disconnect_session(self, session_id: str) -> None:
        """A session was revoked: tell the device, then close its connections"""
        for connection_id, connection in list(self.connections.items()):
            if connection.session_id != session_id:
                continue
            try:
                await connection.websocket.send_json({"type": "session_revoked"})
                await connection.websocket.close(code=4401, reason="Signed out")
            except Exception:
                pass
            await self.remove(connection_id)


presence = PresenceManager()


# Startup -------------------------------------------------------------------------------------------

def ensure_schema() -> None:
    """
    Make sure the tables and columns the portal needs exist.

    The users and user_sessions tables are new to databases made before accounts worked (create_all adds
    missing tables), and tasks gains created_by_user_id (create_all never alters an existing table).
    """
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    if "created_by_user_id" not in task_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN created_by_user_id INTEGER"))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_tasks_created_by_user_id ON tasks (created_by_user_id)"
            ))
        logger.info("Added tasks.created_by_user_id")


def housekeeping() -> None:
    """Remove expired guests and old sessions"""
    db = SessionLocal()
    try:
        purge_expired_guests(db)
        purge_old_sessions(db)
    except Exception as e:
        db.rollback()
        logger.warning(f"Portal housekeeping failed: {e}")
    finally:
        db.close()


async def housekeeping_loop(interval_seconds: int = 3600) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await anyio.to_thread.run_sync(housekeeping)
