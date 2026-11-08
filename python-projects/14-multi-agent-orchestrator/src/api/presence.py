"""
Live presence over WebSocket: who is online, and sign-in / sign-out as they happen

The token is sent as the first message, not in the URL (URLs end up in logs and browser history).
"""

import asyncio
from datetime import datetime
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from src.core import portal
from src.core.auth import authenticate_token
from src.core.config import settings
from src.core.database import SessionLocal
from src.core.logging import logger

router = APIRouter()

AUTH_TIMEOUT_SECONDS = 10
IDLE_TIMEOUT_SECONDS = 70  # the page pings every 20 s
MAX_MESSAGE_CHARS = 4096


def origin_allowed(websocket: WebSocket) -> bool:
    """
    Browsers send the page's Origin on a WebSocket and let any site open one, so a page on another site
    could otherwise talk to this server as the visitor. Same host as the request, or a configured CORS
    origin; clients that send no Origin (scripts) are not browsers and are let through.
    """
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    if origin in settings.CORS_ORIGINS:
        return True
    return urlparse(origin).netloc == websocket.headers.get("host")


def _check_session(session_id: str, user_id: int):
    """The user and session if the sign-in is still valid, else None"""
    db = SessionLocal()
    try:
        from src.models.user import UserSession, User
        session = db.query(UserSession).filter(UserSession.id == session_id).first()
        if session is None or session.user_id != user_id or not session.is_active():
            return None
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or not user.is_active:
            return None
        session.last_seen_at = datetime.utcnow()
        db.commit()
        return user
    finally:
        db.close()


@router.websocket("/ws/presence")
async def presence_socket(websocket: WebSocket):
    """
    Protocol:
      client -> {"type": "auth", "token": "<access token>"}      (first message, within 10 s)
      server -> {"type": "ready", "me": {...}, "online": [...], "count": n, "activity": [...]}
      server -> {"type": "presence" | "activity", ...}           (whenever something changes)
      client -> {"type": "ping"}    server -> {"type": "pong"}   (keeps the connection and session fresh)
      server -> {"type": "session_revoked"}                      (this device was signed out)
    """
    if not origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    await websocket.accept()
    connection_id = str(uuid4())
    registered = False

    try:
        try:
            first = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS)
        except (asyncio.TimeoutError, ValueError):
            await websocket.close(code=4400, reason="Authentication required")
            return
        if not isinstance(first, dict) or first.get("type") != "auth" or not isinstance(first.get("token"), str):
            await websocket.close(code=4400, reason="Authentication required")
            return

        def authenticate():
            db = SessionLocal()
            try:
                user, session = authenticate_token(first["token"], db)
                return user.to_dict(), session.id
            finally:
                db.close()

        try:
            me, session_id = await asyncio.to_thread(authenticate)
        except HTTPException:
            await websocket.close(code=4401, reason="Invalid or expired token")
            return

        if portal.presence.connection_count(me["id"]) >= portal.MAX_PRESENCE_CONNECTIONS_PER_USER:
            await websocket.close(code=4429, reason="Too many open tabs")
            return

        announcement = portal.presence.register(connection_id, portal.Connection(
            websocket=websocket,
            user_id=me["id"],
            username=me["username"],
            is_guest=me["is_guest"],
            session_id=session_id,
            since=datetime.utcnow().isoformat() + "Z",
        ))
        registered = True
        await websocket.send_json({"type": "ready", "me": me, **{
            k: v for k, v in portal.presence.snapshot().items() if k != "type"
        }})
        await portal.presence.broadcast(announcement)

        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=IDLE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                await websocket.close(code=4408, reason="Idle")
                return
            if len(raw) > MAX_MESSAGE_CHARS:
                await websocket.close(code=1009, reason="Message too big")
                return
            if '"ping"' in raw:
                if await asyncio.to_thread(_check_session, session_id, me["id"]) is None:
                    await websocket.send_json({"type": "session_revoked"})
                    await websocket.close(code=4401, reason="Signed out")
                    return
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Presence socket error: {e}")
    finally:
        if registered:
            await portal.presence.remove(connection_id)
