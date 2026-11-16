"""Sign in, create an account, continue as a guest, sign out.

* The first real account adopts the data that existed before accounts (it has no owner).
* A guest who creates an account keeps their documents: the guest row is turned into the real account.
* Guests are temporary: the account and everything it owns disappear after GUEST_TTL_HOURS.
* Wrong-password attempts are limited per address and per username.
"""
import asyncio
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from src.core import auth, database
from src.core.config import get_settings
from src.models.graph import Document, Entity, Fact
from src.models.resolution import EntityAlias, MergeRecord, MergeSuggestion
from src.models.user import GUEST_PREFIX, User, UserSession

router = APIRouter(prefix="/api/auth", tags=["auth"])

FAILURE_LIMIT, FAILURE_WINDOW = 8, 600     # wrong passwords per address and per username
CREATE_LIMIT, CREATE_WINDOW = 20, 3600     # accounts or guests created per address per hour

OWNED = (Document, Entity, Fact, EntityAlias, MergeSuggestion, MergeRecord)


class _Throttle:
    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self.events: Dict[str, Deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> Deque[float]:
        q = self.events[key]
        while q and q[0] < now - self.window:
            q.popleft()
        if not q:
            self.events.pop(key, None)
            return deque()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._prune(key, time.time())) >= self.limit

    def add(self, key: str) -> None:
        now = time.time()
        self._prune(key, now)
        self.events[key].append(now)
        if len(self.events) > 5000:  # a long-running server must not grow without limit
            for k in list(self.events)[:1000]:
                self._prune(k, now)

    def clear(self, key: str) -> None:
        self.events.pop(key, None)


login_failures = _Throttle(FAILURE_LIMIT, FAILURE_WINDOW)
creations = _Throttle(CREATE_LIMIT, CREATE_WINDOW)


class Credentials(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=500)
    display_name: Optional[str] = Field(None, max_length=200)


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _device(request: Request) -> str:
    return request.headers.get("user-agent", "")[:160]


def _set_cookie(response: Response, token: str, user: User) -> None:
    response.set_cookie(auth.COOKIE_NAME, token, max_age=int(auth.session_lifetime(user).total_seconds()), httponly=True,
                        samesite="lax", secure=get_settings().cookie_secure, path="/")


def _too_many(seconds: int) -> HTTPException:
    return HTTPException(429, detail="Too many attempts, try again later", headers={"Retry-After": str(seconds)})


@router.get("/config")
async def auth_config():
    s = get_settings()
    return {"require_login": s.require_login, "registration": s.allow_registration, "guests": s.allow_guests,
            "guest_ttl_hours": s.guest_ttl_hours, "guest_max_documents": s.guest_max_documents, "min_password": auth.MIN_PASSWORD}


@router.get("/me")
async def me():
    caller = auth.current_caller()
    if caller is None:
        raise HTTPException(401, detail="Not signed in")
    if caller.user_id is None:
        return {"id": None, "username": "local", "display_name": "Local user", "is_guest": False, "local_mode": True}
    with database.session_scope() as db:
        user = db.get(User, caller.user_id)
        if user is None:
            raise HTTPException(401, detail="Not signed in")
        data = user.to_dict()
        if user.is_guest:
            data["guest_ttl_hours"] = get_settings().guest_ttl_hours
            data["guest_max_documents"] = get_settings().guest_max_documents
        return data


def _register(creds: Credentials, request: Request, response: Response, current_token: str) -> dict:
    s = get_settings()
    if not s.allow_registration:
        raise HTTPException(403, detail="Creating accounts is turned off on this server")
    ip = _ip(request)
    if creations.blocked(ip):
        raise _too_many(CREATE_WINDOW)
    try:
        username, password = auth.check_username(creds.username), auth.check_password(creds.password)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    display = auth.clean_display_name(creds.display_name)
    with database.session_scope() as db:
        if db.execute(select(User.id).where(User.username == username)).first():
            raise HTTPException(409, detail="That username is taken")
        first_account = (db.scalar(select(func.count()).select_from(User).where(User.is_guest.is_(False))) or 0) == 0
        found = auth.resolve_session(db, current_token, touch=False) if current_token else None
        guest = found[0] if found and found[0].is_guest else None
        if guest is not None:  # upgrade in place: the guest's documents stay with the account
            user = guest
            user.username, user.display_name, user.password_hash, user.is_guest = username, display, auth.hash_password(password), False
        else:
            user = User(username=username, display_name=display, password_hash=auth.hash_password(password))
            db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, detail="That username is taken")
        adopted = 0
        if first_account:  # data from before accounts existed belongs to the first account
            for model in OWNED:
                n = db.execute(update(model).where(model.owner_id.is_(None)).values(owner_id=user.id)).rowcount
                adopted += n if model is Document else 0
        creations.add(ip)
        token = auth.start_session(db, user, _device(request), ip)
        _set_cookie(response, token, user)
        out = user.to_dict()
        out["adopted_documents"] = adopted
        return out


@router.post("/register")
async def register(creds: Credentials, request: Request, response: Response):
    return await asyncio.to_thread(_register, creds, request, response, request.cookies.get(auth.COOKIE_NAME, ""))


def _login(creds: Credentials, request: Request, response: Response) -> dict:
    ip = _ip(request)
    name = (creds.username or "").strip().lower()
    if login_failures.blocked(f"ip:{ip}") or login_failures.blocked(f"user:{name}"):
        raise _too_many(FAILURE_WINDOW)
    with database.session_scope() as db:
        user = db.execute(select(User).where(User.username == name)).scalar_one_or_none()
        if user is None or user.is_guest:
            auth.burn_password_time(creds.password)
            ok = False
        else:
            ok = auth.verify_password(creds.password, user.password_hash)
        if not ok or not user.is_active:
            login_failures.add(f"ip:{ip}")
            login_failures.add(f"user:{name}")
            raise HTTPException(401, detail="Wrong username or password")
        login_failures.clear(f"user:{name}")
        token = auth.start_session(db, user, _device(request), ip)
        _set_cookie(response, token, user)
        return user.to_dict()


@router.post("/login")
async def login(creds: Credentials, request: Request, response: Response):
    return await asyncio.to_thread(_login, creds, request, response)


def _guest(request: Request, response: Response) -> dict:
    if not get_settings().allow_guests:
        raise HTTPException(403, detail="Guest access is turned off on this server")
    ip = _ip(request)
    if creations.blocked(ip):
        raise _too_many(CREATE_WINDOW)
    with database.session_scope() as db:
        # nobody can sign in to a guest account by password: it is reached through its cookie only
        user = User(username=GUEST_PREFIX + secrets.token_hex(4), display_name="Guest", is_guest=True,
                    password_hash=auth.hash_password(secrets.token_urlsafe(24)))
        db.add(user)
        db.commit()
        creations.add(ip)
        token = auth.start_session(db, user, _device(request), ip)
        _set_cookie(response, token, user)
        return user.to_dict()


@router.post("/guest")
async def guest(request: Request, response: Response):
    return await asyncio.to_thread(_guest, request, response)


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(auth.COOKIE_NAME, "")
    if token:
        with database.session_scope() as db:
            auth.end_session(db, token)
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"success": True}


def cleanup_expired_guests(now: Optional[datetime] = None) -> int:
    """Remove guest accounts older than GUEST_TTL_HOURS and everything they own (the foreign keys cascade).
    Also forgets sign-ins that ended more than a day ago."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=get_settings().guest_ttl_hours)
    removed = 0
    with database.session_scope() as db:
        for user in db.execute(select(User).where(User.is_guest.is_(True), User.created_at < cutoff)).scalars().all():
            db.delete(user)
            removed += 1
        db.execute(UserSession.__table__.delete().where(UserSession.expires_at < now - timedelta(days=1)))
    return removed
