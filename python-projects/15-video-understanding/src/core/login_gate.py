"""
The sign-in gate, in front of every request.

* /api/* answers 401 unless the cookie holds a live sign-in (a few auth paths are public).
* A cookie that is not sent along with a *cross-site* write is refused, so another website cannot make the
  browser delete your videos (the cookie is SameSite=Lax as well; this is the second lock).
* A WebSocket from another site is refused for the same reason (browsers do not apply CORS to WebSockets).
* REQUIRE_LOGIN=false turns the gate off for single-user local use: everyone is the local administrator.

Written as a plain ASGI middleware, not BaseHTTPMiddleware, because that one never sees WebSockets and
would not pass the caller on to the endpoint.
"""

import asyncio
import json
from http.cookies import SimpleCookie
from typing import Optional
from urllib.parse import urlparse

from src.core.auth import (
    COOKIE_NAME, LOCAL_CALLER, Caller, caller_for, reset_current_caller, resolve_session, set_current_caller,
)
from src.core.config import settings
from src.core.database import SessionLocal

PUBLIC_API_PATHS = {
    "/api/info",
    "/api/auth/config",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/guest",
    "/api/auth/logout",
}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_public(path: str) -> bool:
    if not path.startswith("/api/"):
        return True
    return path.rstrip("/") in PUBLIC_API_PATHS


def _headers(scope) -> dict:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


def _cookie_token(headers: dict) -> str:
    raw = headers.get("cookie")
    if not raw:
        return ""
    try:
        jar = SimpleCookie()
        jar.load(raw)
        morsel = jar.get(COOKIE_NAME)
        return morsel.value if morsel else ""
    except Exception:
        return ""


def _lookup(token: str) -> Optional[Caller]:
    db = SessionLocal()
    try:
        found = resolve_session(db, token)
        return caller_for(*found) if found else None
    finally:
        db.close()


def allowed_origins() -> set:
    return {o.rstrip("/") for o in settings.cors_origins}


def same_site(headers: dict) -> bool:
    """
    True when the Origin (or, failing that, the Referer) of a request is this site or a configured origin.
    A request that sends neither (curl, a script, a test client) is not a browser attack, so it passes.
    """
    source = headers.get("origin") or headers.get("referer")
    if not source:
        return True
    parsed = urlparse(source)
    if not parsed.netloc:  # includes Origin: null (sandboxed frames, redirects across sites)
        return False
    if parsed.netloc == headers.get("host", ""):
        return True
    return f"{parsed.scheme}://{parsed.netloc}" in allowed_origins() | {
        "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001", "http://127.0.0.1:8000",
    }


async def _json(send, status: int, body: dict, extra: Optional[list] = None):
    payload = json.dumps(body).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers + (extra or [])})
    await send({"type": "http.response.body", "body": payload})


class LoginGateMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = _headers(scope)
        path = scope.get("path", "")

        if kind == "websocket":
            if not same_site(headers):
                await send({"type": "websocket.close", "code": 1008})
                return
            caller = await self._caller(headers)
            token = set_current_caller(caller)
            try:
                return await self.app(scope, receive, send)
            finally:
                reset_current_caller(token)

        method = scope.get("method", "GET")
        if method == "OPTIONS":
            return await self.app(scope, receive, send)

        has_cookie = bool(_cookie_token(headers))
        if method not in SAFE_METHODS and has_cookie and not same_site(headers):
            return await _json(send, 403, {"detail": "Cross-site request refused"})

        caller = await self._caller(headers)
        if caller is None and not is_public(path):
            return await _json(
                send, 401, {"detail": "Not signed in"}, [(b"www-authenticate", b'Cookie realm="video"')]
            )

        token = set_current_caller(caller)
        try:
            return await self.app(scope, receive, send)
        finally:
            reset_current_caller(token)

    async def _caller(self, headers: dict) -> Optional[Caller]:
        if not settings.require_login:
            return LOCAL_CALLER
        cookie = _cookie_token(headers)
        if not cookie:
            return None
        return await asyncio.to_thread(_lookup, cookie)
