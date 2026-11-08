"""
Authentication API endpoints: accounts, guests, device sessions, who is online

Handlers are plain `def` on purpose: password hashing and the database calls block, and FastAPI runs
them in a worker thread instead of freezing the event loop for everyone.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.core.auth import (
    AuthService,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_token,
    get_current_user,
    get_current_session,
    require_admin,
)
from src.core import portal
from src.models.user import User, UserSession
from src.core.logging import logger


router = APIRouter()


# Pydantic models

class UserRegister(BaseModel):
    """Account creation: an email is optional (it is only a second way to sign in)"""
    username: str = Field(..., max_length=64)
    password: str = Field(..., max_length=1024)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=100)


class UserLogin(BaseModel):
    """Sign-in request"""
    username: str = Field(..., max_length=254)  # username or email
    password: str = Field(..., max_length=1024)


class TokenRefresh(BaseModel):
    """Token refresh request"""
    refresh_token: str = Field(..., max_length=4096)


class PasswordChange(BaseModel):
    """Password change request"""
    current_password: str = Field(..., max_length=1024)
    new_password: str = Field(..., max_length=1024)


class GuestUpgrade(BaseModel):
    """Turn the guest account you are using into a real one, keeping what you made"""
    username: str = Field(..., max_length=64)
    password: str = Field(..., max_length=1024)
    email: Optional[EmailStr] = None


def _too_many(seconds: int, what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many {what}. Try again in {seconds} seconds.",
        headers={"Retry-After": str(seconds)},
    )


def _bad_request(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


# Endpoints

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user_data: UserRegister, request: Request, db: Session = Depends(get_db_session)):
    """Create an account and sign in on this device"""
    ip = portal.client_ip(request)
    wait = portal.signups_by_ip.retry_after(ip)
    if wait:
        raise _too_many(wait, "accounts created from this address")
    portal.signups_by_ip.record(ip)

    try:
        user = portal.create_user(db, user_data.username, user_data.password, user_data.email, user_data.full_name)
    except ValueError as e:
        raise _bad_request(e)

    logger.info(f"New user registered: {user.username}")
    portal.publish(portal.presence.announce("joined", user.username, False))
    return portal.start_session(db, user, request)


@router.post("/login")
def login(login_data: UserLogin, request: Request, db: Session = Depends(get_db_session)):
    """Sign in (username or email) on this device"""
    ip = portal.client_ip(request)
    name_key = login_data.username.strip().lower()
    wait = max(portal.login_failures_by_name.retry_after(name_key), portal.login_failures_by_ip.retry_after(ip))
    if wait:
        raise _too_many(wait, "failed sign-ins")

    user = portal.authenticate(db, login_data.username, login_data.password)
    if not user:
        portal.login_failures_by_name.record(name_key)
        portal.login_failures_by_ip.record(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    portal.login_failures_by_name.reset(name_key)
    portal.apply_admin_list(user)
    logger.info(f"User logged in: {user.username}")
    return portal.start_session(db, user, request)


@router.post("/guest", status_code=status.HTTP_201_CREATED)
def continue_as_guest(request: Request, db: Session = Depends(get_db_session)):
    """Start a throwaway guest account: no details needed, removed after a day without use"""
    ip = portal.client_ip(request)
    wait = portal.guests_by_ip.retry_after(ip)
    if wait:
        raise _too_many(wait, "guest accounts started from this address")
    portal.guests_by_ip.record(ip)

    user = portal.create_guest_user(db)
    logger.info(f"Guest account started: {user.username}")
    portal.publish(portal.presence.announce("guest", user.username, True))
    return portal.start_session(db, user, request)


@router.post("/guest/upgrade")
def upgrade_guest(
    data: GuestUpgrade,
    request: Request,
    session_info=Depends(get_current_session),
    db: Session = Depends(get_db_session),
):
    """Give the guest account a real username and password; its tasks stay with it"""
    user, session = session_info
    if not user.is_guest:
        raise HTTPException(status_code=400, detail="Only guest accounts can be upgraded")
    user = db.query(User).filter(User.id == user.id).first()

    try:
        username = portal.validate_username(data.username)
        portal.validate_password(data.password)
        email = portal.normalize_email(data.email, username)
        taken = db.query(User).filter(
            func.lower(User.username) == username.lower(), User.id != user.id
        ).first()
        if taken:
            raise ValueError("Username already taken")
        if db.query(User).filter(func.lower(User.email) == email, User.id != user.id).first():
            raise ValueError("Email already registered")
    except ValueError as e:
        raise _bad_request(e)

    old_name = user.username
    user.username = username
    user.email = email
    user.full_name = None
    user.hashed_password = User.get_password_hash(data.password)
    portal.apply_admin_list(user)
    db.commit()
    logger.info(f"Guest {old_name} became {username}")
    portal.publish(portal.presence.rename_user(user.id, user.username, user.is_guest))
    return {"user": user.to_dict()}


@router.post("/refresh")
def refresh_token(token_data: TokenRefresh, db: Session = Depends(get_db_session)):
    """Exchange a refresh token for new tokens (the sign-in on this device continues)"""
    user, session = authenticate_token(token_data.refresh_token, db, token_type="refresh")
    claims = {"sub": user.id, "sid": session.id}
    return {
        "access_token": AuthService.create_access_token(claims),
        "refresh_token": AuthService.create_refresh_token(claims),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "session_id": session.id,
        "user": user.to_dict(),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session_info=Depends(get_current_session), db: Session = Depends(get_db_session)):
    """Sign out of this device"""
    user, session = session_info
    portal.end_session(db, session)
    logger.info(f"User logged out: {user.username}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
def get_current_user_info(session_info=Depends(get_current_session)):
    """The signed-in user and the id of this device's session"""
    user, session = session_info
    return {**user.to_dict(), "session_id": session.id}


@router.put("/me")
def update_current_user(
    full_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Update the display name"""
    if full_name is not None:
        current_user.full_name = full_name.strip()[:100] or None
    db.commit()
    db.refresh(current_user)
    return current_user.to_dict()


@router.post("/change-password")
def change_password(
    password_data: PasswordChange,
    session_info=Depends(get_current_session),
    db: Session = Depends(get_db_session),
):
    """Change the password; every other device is signed out"""
    user, session = session_info
    if user.is_guest:
        raise HTTPException(status_code=400, detail="Guest accounts have no password: create an account first")
    if not user.check_password(password_data.current_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    try:
        portal.validate_password(password_data.new_password)
    except ValueError as e:
        raise _bad_request(e)

    user.hashed_password = User.get_password_hash(password_data.new_password)
    db.commit()
    signed_out = portal.end_other_sessions(db, user.id, keep_session_id=session.id)
    logger.info(f"User changed password: {user.username}")
    return {"message": "Password changed successfully", "other_devices_signed_out": signed_out}


@router.get("/sessions")
def list_sessions(session_info=Depends(get_current_session), db: Session = Depends(get_db_session)):
    """The devices signed in to this account"""
    user, current = session_info
    sessions = db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > datetime.utcnow(),
    ).order_by(UserSession.last_seen_at.desc()).all()
    return [s.to_dict(current_id=current.id) for s in sessions]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: str, session_info=Depends(get_current_session), db: Session = Depends(get_db_session)):
    """Sign a device out; it finds out immediately if it has the page open"""
    user, _ = session_info
    target = db.query(UserSession).filter(
        UserSession.id == session_id, UserSession.user_id == user.id
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Session not found")
    portal.end_session(db, target)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/revoke-others")
def revoke_other_sessions(session_info=Depends(get_current_session), db: Session = Depends(get_db_session)):
    """Sign out every device except this one"""
    user, session = session_info
    return {"signed_out": portal.end_other_sessions(db, user.id, keep_session_id=session.id)}


@router.get("/online")
def who_is_online(_: User = Depends(get_current_user)):
    """Accounts with the app open right now (the same data the live WebSocket pushes)"""
    return portal.presence.snapshot()


@router.get("/users")
def list_users(
    skip: int = 0,
    limit: int = 100,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
):
    """List all accounts (admin only)"""
    skip = max(0, skip)
    limit = max(1, min(limit, 500))
    return [u.to_dict() for u in db.query(User).order_by(User.id).offset(skip).limit(limit).all()]
