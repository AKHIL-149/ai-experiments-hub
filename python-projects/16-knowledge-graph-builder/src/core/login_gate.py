"""The sign-in gate, in front of every request.

* /api/* answers 401 unless the cookie holds a live sign-in (the auth paths and /api/health are public).
* A write that carries the cookie from another website is refused (the cookie is SameSite=Lax as well; this is the
  second lock), so another site cannot make the browser delete your documents.
* REQUIRE_LOGIN=false turns the gate off for single-user local use: everyone is the local user.

A plain ASGI middleware, not BaseHTTPMiddleware, so the caller reaches the endpoint through a ContextVar.
"""
import asyncio
import json
from http.cookies import SimpleCookie
from typing import Optional
from urllib.parse import urlparse

from src.core import database
from src.core.auth import COOKIE_NAME, LOCAL_CALLER, Caller, caller_for, reset_current_caller, resolve_session, set_current_caller
from src.core.config import get_settings

PUBLIC_API_PATHS = {"/api/health", "/api/auth/config", "/api/auth/login", "/api/auth/register", "/api/auth/guest", "/api/auth/logout"}
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
    db = database.SessionLocal()
    try:
        found = resolve_session(db, token)
        return caller_for(*found) if found else None
    finally:
        db.close()


def same_site(headers: dict) -> bool:
    """True when the Origin (or failing that the Referer) is this site or an allowed origin. A request that sends
    neither (curl, a script, a test client) is not a browser attack, so it passes."""
    source = headers.get("origin") or headers.get("referer")
    if not source:
        return True
    parsed = urlparse(source)
    if not parsed.netloc:  # includes "Origin: null" (sandboxed frames, redirects across sites)
        return False
    if parsed.netloc == headers.get("host", ""):
        return True
    extra = {o.strip().rstrip("/") for o in get_settings().allowed_origins.split(",") if o.strip()}
    return f"{parsed.scheme}://{parsed.netloc}" in extra


async def _json(send, status: int, body: dict, extra: Optional[list] = None):
    payload = json.dumps(body).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers + (extra or [])})
    await send({"type": "http.response.body", "body": payload})


class LoginGateMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = _headers(scope)
        method = scope.get("method", "GET")
        if method == "OPTIONS":
            return await self.app(scope, receive, send)
        if method not in SAFE_METHODS and _cookie_token(headers) and not same_site(headers):
            return await _json(send, 403, {"detail": "Cross-site request refused"})
        caller = await self._caller(headers)
        if caller is None and not is_public(scope.get("path", "")):
            return await _json(send, 401, {"detail": "Not signed in"}, [(b"www-authenticate", b'Cookie realm="knowledge-graph"')])
        token = set_current_caller(caller)
        try:
            return await self.app(scope, receive, send)
        finally:
            reset_current_caller(token)

    async def _caller(self, headers: dict) -> Optional[Caller]:
        if not get_settings().require_login:
            return LOCAL_CALLER
        cookie = _cookie_token(headers)
        return await asyncio.to_thread(_lookup, cookie) if cookie else None
