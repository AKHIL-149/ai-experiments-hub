"""
Sign in, create an account, continue as a guest, sign out.

* The first real account becomes the administrator and adopts the videos that were uploaded before accounts
  existed (they have no owner). Names listed in ADMIN_USERNAMES are administrators too.
* A guest who creates an account keeps their videos: the guest row is turned into the real account.
* Wrong-password attempts are limited per address and per username.
"""

import asyncio
import secrets
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from src.core import auth
from src.core.config import settings
from src.core.database import get_db
from src.models.user import GUEST_PREFIX, User
from src.models.video import Video

router = APIRouter(prefix="/api/auth", tags=["auth"])

FAILURE_LIMIT = 8        # wrong passwords...
FAILURE_WINDOW = 600     # ...in this many seconds, per address and per username
CREATE_LIMIT = 20        # accounts or guests created per address per hour
CREATE_WINDOW = 3600


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
    response.set_cookie(
        auth.COOKIE_NAME, token,
        max_age=int(auth.session_lifetime(user).total_seconds()),
        httponly=True, samesite="lax", secure=settings.cookie_secure, path="/",
    )


def _too_many(seconds: int) -> HTTPException:
    return HTTPException(429, detail="Too many attempts, try again later", headers={"Retry-After": str(seconds)})


def _is_admin_name(username: str, first_account: bool) -> bool:
    return first_account or username in auth.configured_admins()


@router.get("/config")
async def auth_config():
    """What the sign-in page may offer"""
    return {
        "require_login": settings.require_login,
        "registration": settings.allow_registration,
        "guests": settings.allow_guests,
        "guest_ttl_hours": settings.guest_ttl_hours,
        "guest_max_videos": settings.guest_max_videos,
        "min_password": auth.MIN_PASSWORD,
    }


@router.get("/me")
async def me():
    caller = auth.current_caller()
    if caller is None:
        raise HTTPException(401, detail="Not signed in")
    if caller.user_id is None:  # single-user mode
        return {"id": None, "username": "local", "display_name": "Local user", "is_guest": False,
                "is_admin": True, "local_mode": True}
    with get_db() as db:
        user = db.query(User).filter(User.id == caller.user_id).first()
        if user is None:
            raise HTTPException(401, detail="Not signed in")
        data = user.to_dict()
        if user.is_guest:
            data["guest_ttl_hours"] = settings.guest_ttl_hours
        return data


def _register(creds: Credentials, request: Request, response: Response, current_token: str) -> dict:
    if not settings.allow_registration:
        raise HTTPException(403, detail="Creating accounts is turned off on this server")
    ip = _ip(request)
    if creations.blocked(ip):
        raise _too_many(CREATE_WINDOW)
    try:
        username = auth.check_username(creds.username)
        password = auth.check_password(creds.password)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    display = auth.clean_display_name(creds.display_name)

    with get_db() as db:
        if db.query(User).filter(User.username == username).first():
            raise HTTPException(409, detail="That username is taken")

        first_account = db.query(User).filter(User.is_guest.is_(False)).count() == 0
        found = auth.resolve_session(db, current_token, touch=False) if current_token else None
        guest = found[0] if found and found[0].is_guest else None

        if guest is not None:  # upgrade in place: the guest's videos stay with the account
            user = guest
            user.username, user.display_name = username, display
            user.password_hash = auth.hash_password(password)
            user.is_guest = False
        else:
            user = User(username=username, display_name=display, password_hash=auth.hash_password(password))
            db.add(user)
        user.is_admin = user.is_admin or _is_admin_name(username, first_account)

        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, detail="That username is taken")

        adopted = 0
        if first_account:  # videos from before accounts existed belong to the first account
            adopted = db.query(Video).filter(Video.user_id.is_(None)).update(
                {Video.user_id: user.id}, synchronize_session=False
            )
        db.commit()

        creations.add(ip)
        token = auth.start_session(db, user, _device(request), ip)
        _set_cookie(response, token, user)
        result = user.to_dict()
        result["adopted_videos"] = adopted
        return result


@router.post("/register")
async def register(creds: Credentials, request: Request, response: Response):
    token = request.cookies.get(auth.COOKIE_NAME, "")
    return await asyncio.to_thread(_register, creds, request, response, token)


def _login(creds: Credentials, request: Request, response: Response) -> dict:
    ip = _ip(request)
    name = (creds.username or "").strip().lower()
    if login_failures.blocked(f"ip:{ip}") or login_failures.blocked(f"user:{name}"):
        raise _too_many(FAILURE_WINDOW)

    with get_db() as db:
        user = db.query(User).filter(User.username == name).first()
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
        if name in auth.configured_admins() and not user.is_admin:
            user.is_admin = True
        token = auth.start_session(db, user, _device(request), ip)
        _set_cookie(response, token, user)
        return user.to_dict()


@router.post("/login")
async def login(creds: Credentials, request: Request, response: Response):
    return await asyncio.to_thread(_login, creds, request, response)


def _guest(request: Request, response: Response) -> dict:
    if not settings.allow_guests:
        raise HTTPException(403, detail="Guest access is turned off on this server")
    ip = _ip(request)
    if creations.blocked(ip):
        raise _too_many(CREATE_WINDOW)
    with get_db() as db:
        name = GUEST_PREFIX + secrets.token_hex(4)
        user = User(
            username=name, display_name="Guest", is_guest=True,
            # nobody can sign in to a guest account by password: it is reached through its cookie only
            password_hash=auth.hash_password(secrets.token_urlsafe(24)),
        )
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
        with get_db() as db:
            auth.end_session(db, token)
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"success": True}
