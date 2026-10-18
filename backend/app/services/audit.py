from sqlalchemy.orm import Session

from app.models import AuditLog, User


def audit(db: Session, user: User | None, action: str, device_id: int | None = None,
          details: str = "", result: str = "SUCCESS", source_ip: str = "", username: str | None = None) -> None:
    """Append-only audit record. Never put secrets or full configs in `details`."""
    db.add(AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else (username or "system"),
        action=action, device_id=device_id, details=details[:2000], result=result, source_ip=source_ip,
    ))
    db.commit()
