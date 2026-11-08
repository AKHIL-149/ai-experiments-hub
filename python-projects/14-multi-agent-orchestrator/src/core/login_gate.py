"""
Sign-in gate: the API answers 401 unless the request carries a valid Bearer token of a live session

Pages (/, /login, /dashboard, /static) are public so the browser can load the sign-in page; everything
they fetch is under /api. REQUIRE_LOGIN=false turns the gate off.
"""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

import anyio
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.core import portal
from src.core.auth import authenticate_token
from src.core.database import SessionLocal

# API paths that work without signing in
PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/guest",
    "/api/auth/refresh",
}


@dataclass
class Caller:
    """Who a request is from, read by endpoints that scope data to its owner"""
    user_id: int
    username: str
    is_admin: bool
    is_guest: bool
    role: object = None


def is_public(path: str) -> bool:
    if not path.startswith("/api/"):
        return True
    return path.rstrip("/") in PUBLIC_API_PATHS


def _authenticate(token: str):
    db = SessionLocal()
    try:
        user, _ = authenticate_token(token, db)
        return Caller(user.id, user.username, user.is_admin(), user.is_guest, user.role)
    finally:
        db.close()


class LoginGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.caller = None
        if request.method == "OPTIONS" or is_public(request.url.path):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        token = header[7:].strip() if header[:7].lower() == "bearer " else ""
        if not token:
            if not portal.REQUIRE_LOGIN:
                return await call_next(request)
            return JSONResponse(
                {"detail": "Not authenticated"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )

        try:
            caller = await anyio.to_thread.run_sync(_authenticate, token)
            request.state.caller = caller
            # the rate limiter and the cache read request.state.user: limits then apply per account
            # instead of to everyone sharing an address (a household, an office, one NAT)
            request.state.user = SimpleNamespace(id=caller.user_id, role=caller.role)
        except HTTPException as e:
            if not portal.REQUIRE_LOGIN:
                return await call_next(request)
            return JSONResponse(
                {"detail": e.detail}, status_code=e.status_code, headers={"WWW-Authenticate": "Bearer"}
            )
        return await call_next(request)


def get_caller(request: Request) -> Optional[Caller]:
    """Dependency: the signed-in caller, or None when the gate is off and nobody signed in"""
    return getattr(request.state, "caller", None)
