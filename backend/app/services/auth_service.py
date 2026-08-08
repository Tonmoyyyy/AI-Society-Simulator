from sqlalchemy.orm import Session

from app.core import security
from app.repositories import user_repo
from app.models.user import User


class AuthError(Exception):
    """Raised for any auth failure the API layer should turn into a 4xx response."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def signup(db: Session, email: str, password: str) -> User:
    if user_repo.get_by_email(db, email):
        raise AuthError("An account with this email already exists")

    password_hash = security.hash_password(password)
    # First-ever account could be promoted to admin manually later;
    # v0.1 keeps signup simple and always creates a spectator account.
    return user_repo.create(db, email=email, password_hash=password_hash, role="spectator")


def authenticate(db: Session, email: str, password: str) -> User:
    user = user_repo.get_by_email(db, email)
    if user is None or not security.verify_password(password, user.password_hash):
        raise AuthError("Incorrect email or password")
    return user


def login(db: Session, email: str, password: str) -> dict:
    user = authenticate(db, email, password)
    return {
        "access_token": security.create_access_token(user.id),
        "refresh_token": security.create_refresh_token(user.id),
        "token_type": "bearer",
    }


def refresh_access_token(db: Session, refresh_token: str) -> dict:
    payload = security.decode_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise AuthError("Invalid or expired refresh token")

    user_id = int(payload["sub"])
    user = user_repo.get_by_id(db, user_id)
    if user is None:
        raise AuthError("User no longer exists")

    return {
        "access_token": security.create_access_token(user.id),
        "token_type": "bearer",
    }
