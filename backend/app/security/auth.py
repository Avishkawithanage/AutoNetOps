"""Password hashing, JWT tokens and FastAPI auth dependencies (RBAC)."""
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import User
from app.security.crypto import jwt_secret

_ph = PasswordHasher()  # Argon2id
_bearer = HTTPBearer(auto_error=False)

ROLES = ("viewer", "operator", "admin")
_RANK = {r: i for i, r in enumerate(ROLES)}


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def validate_password_strength(password: str) -> None:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, jwt_secret(), algorithm="HS256")


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, jwt_secret(), algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")
    return user


def require_role(minimum: str):
    """Dependency factory: user's role must be >= `minimum` (viewer < operator < admin)."""

    def dep(user: User = Depends(get_current_user)) -> User:
        if _RANK.get(user.role, -1) < _RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role '{minimum}' or higher")
        return user

    return dep


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""
