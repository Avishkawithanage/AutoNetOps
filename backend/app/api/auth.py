from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import User
from app.schemas import LoginIn, PasswordChange, UserCreate, UserOut, UserUpdate
from app.security.auth import (
    ROLES, client_ip, create_token, get_current_user, hash_password, require_role,
    validate_password_strength, verify_password,
)
from app.services.audit import audit

router = APIRouter(tags=["auth"])
# Identical message for unknown user / wrong password / locked: no account enumeration
_BAD = HTTPException(401, "Invalid credentials")
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    user = db.scalar(select(User).where(User.username == body.username))
    now = datetime.now(timezone.utc)
    if user is None:
        verify_password(body.password, _DUMMY_HASH)  # equalise timing
        audit(db, None, "login", details=f"unknown user '{body.username[:64]}'", result="FAILED", source_ip=ip)
        raise _BAD
    locked = _aware(user.locked_until)
    if locked and locked > now:
        audit(db, user, "login", details="account locked", result="FAILED", source_ip=ip)
        raise _BAD
    if not user.is_active or not verify_password(body.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_attempts = 0
        db.commit()
        audit(db, user, "login", details="bad credentials", result="FAILED", source_ip=ip)
        raise _BAD
    user.failed_attempts, user.locked_until, user.last_login_at = 0, None, now
    db.commit()
    audit(db, user, "login", source_ip=ip)
    return {"access_token": create_token(user), "token_type": "bearer", "user": UserOut.model_validate(user)}


@router.post("/auth/logout")
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Tokens are stateless and short-lived; the client discards it. We record the event.
    audit(db, user, "logout", source_ip=client_ip(request))
    return {"ok": True}


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/auth/change-password")
def change_password(body: PasswordChange, request: Request, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    try:
        validate_password_strength(body.new_password)
    except ValueError as e:
        raise HTTPException(422, str(e))
    user.password_hash = hash_password(body.new_password)
    db.commit()
    audit(db, user, "password_change", source_ip=client_ip(request))
    return {"ok": True}


# ---- user management (admin)
@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, admin: User = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(409, "Username already exists")
    u = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    db.commit()
    audit(db, admin, "user_create", details=f"{u.username} ({u.role})", source_ip=client_ip(request))
    return u


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, admin: User = Depends(require_role("admin")),
                db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    if u.id == admin.id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(400, "You cannot demote or disable your own account")
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(422, f"role must be one of {ROLES}")
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.password:
        try:
            validate_password_strength(body.password)
        except ValueError as e:
            raise HTTPException(422, str(e))
        u.password_hash = hash_password(body.password)
        u.failed_attempts, u.locked_until = 0, None
    db.commit()
    audit(db, admin, "user_update", details=f"{u.username}: role={u.role} active={u.is_active}",
          source_ip=client_ip(request))
    return u
