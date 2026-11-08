"""
Authentication and authorization utilities

Every sign-in is a row in user_sessions and both tokens carry its id (`sid`), so a token stops working as
soon as its session is revoked (sign out, "sign out that device", password change).
"""

import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.models.user import User, UserRole, UserSession
from src.core.logging import logger


# The key every token is signed with. A key that ships in the repository would let anyone who has read
# it mint a token for any account, so the default is a random key generated on the first launch of each
# clone and kept in data/.jwt_secret (git-ignored); JWT_SECRET_KEY overrides it.
PLACEHOLDER_SECRETS = {"", "your-secret-key-change-in-production", "change-me-in-production", "changeme"}
MIN_SECRET_LENGTH = 32


def _load_secret_key() -> str:
    configured = os.getenv("JWT_SECRET_KEY", "").strip()
    if configured and configured not in PLACEHOLDER_SECRETS:
        if len(configured) < MIN_SECRET_LENGTH:
            raise RuntimeError(f"JWT_SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters")
        return configured

    secret_file = Path(os.getenv("JWT_SECRET_FILE") or Path(__file__).resolve().parents[2] / "data" / ".jwt_secret")
    try:
        existing = secret_file.read_text().strip()
        if len(existing) >= MIN_SECRET_LENGTH:
            return existing
    except FileNotFoundError:
        pass
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(48)
    descriptor = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(generated)
    logger.info(f"Generated a new token signing key in {secret_file}")
    return generated


# JWT Configuration
SECRET_KEY = _load_secret_key()
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
SESSION_TOUCH_SECONDS = 30  # last_seen_at is written at most this often


# HTTP Bearer security scheme (we raise the 401 ourselves, FastAPI's default is a 403)
security = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


class AuthService:
    """Authentication service for JWT operations"""

    @staticmethod
    def _encode(data: dict, token_type: str, lifetime: timedelta) -> str:
        to_encode = data.copy()
        if "sub" in to_encode:
            to_encode["sub"] = str(to_encode["sub"])  # python-jose rejects a non-string subject on decode
        now = datetime.utcnow()
        to_encode.update({"exp": now + lifetime, "iat": now, "type": token_type})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token (`data` holds sub = user id and sid = session id)"""
        return AuthService._encode(
            data, "access", expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )

    @staticmethod
    def create_refresh_token(data: dict) -> str:
        """Create a JWT refresh token"""
        return AuthService._encode(data, "refresh", timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))

    @staticmethod
    def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """Decode a token; None if it is malformed, expired or signed with another key"""
        try:
            return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError as e:
            logger.warning(f"JWT verification failed: {e}")
            return None

    @staticmethod
    def get_user_from_token(token: str, db: Session) -> Optional[User]:
        """The user a valid access token belongs to (None if the token or its session is not valid)"""
        try:
            return authenticate_token(token, db, touch=False)[0]
        except HTTPException:
            return None


def authenticate_token(
    token: str, db: Session, token_type: str = "access", touch: bool = True
) -> Tuple[User, UserSession]:
    """
    Resolve a token to its user and session, or raise 401.

    The session must still be active: that is what makes sign-out immediate.
    """
    payload = AuthService.verify_token(token) if token else None
    if not payload or payload.get("type") != token_type:
        raise _unauthorized()

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise _unauthorized()
    session_id = payload.get("sid")
    if not session_id:
        raise _unauthorized()

    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if session is None or session.user_id != user_id or not session.is_active():
        raise _unauthorized("Session ended, please sign in again")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise _unauthorized()
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    if touch:
        now = datetime.utcnow()
        if (now - session.last_seen_at).total_seconds() >= SESSION_TOUCH_SECONDS:
            session.last_seen_at = now
            db.commit()
    return user, session


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db_session)
) -> User:
    """Get the signed-in user from the Bearer token, or raise 401"""
    if credentials is None:
        raise _unauthorized("Not authenticated")
    user, _ = authenticate_token(credentials.credentials, db)
    user.update_api_call()
    db.commit()
    return user


def get_current_session(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db_session)
) -> Tuple[User, UserSession]:
    """The signed-in user together with the session (device) the request comes from"""
    if credentials is None:
        raise _unauthorized("Not authenticated")
    return authenticate_token(credentials.credentials, db)


def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


def require_role(required_role: UserRole):
    """
    Dependency to require specific user role

    Args:
        required_role: Required user role

    Returns:
        Callable: Dependency function
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {required_role.value}"
            )
        return current_user

    return role_checker


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin user"""
    if not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_current_user_ws(token: str, db: Session) -> User:
    """
    Get the signed-in user from an access token for WebSocket connections.

    Raises:
        HTTPException: If authentication fails
    """
    return authenticate_token(token, db)[0]
