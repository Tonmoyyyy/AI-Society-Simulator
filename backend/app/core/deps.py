from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core import security
from app.db.session import SessionLocal
from app.models.user import User

# OAuth2PasswordBearer এর বদলে HTTPBearer সিকিউরিটি স্কিম ব্যবহার করা হয়েছে
security_scheme = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    """Yields a DB session per-request and always closes it, even on error."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Decodes the JWT access token, loads the user, and raises 401 if the
    token is invalid/expired or the user no longer exists.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # HTTPAuthorizationCredentials থেকে আসল টোকেন বের করে নেওয়া হচ্ছে
    token = credentials.credentials

    payload = security.decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = db.get(User, int(user_id))
    if user is None:
        raise credentials_exception

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Gate for admin-only endpoints (used by future dashboard/admin routes)."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user