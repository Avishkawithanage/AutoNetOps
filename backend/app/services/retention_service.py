"""Retention cleanup + storage usage. Protected, latest, and restore-referenced versions are never removed."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal
from app.models import Configuration, RestoreJob, RetentionPolicy
from app.services import storage
from app.services.audit import audit
from app.services.notification_service import notify


def get_policy(db: Session) -> RetentionPolicy:
    p = db.get(RetentionPolicy, 1)
    if p is None:
        p = RetentionPolicy(id=1)
        db.add(p)
        db.commit()
    return p


def storage_status() -> dict:
    used = storage.usage_bytes()
    cap = settings.storage_capacity_bytes
    pct = round(used * 100 / cap, 1) if cap else 0.0
    level = "critical" if pct >= settings.storage_critical_percent else "warning" if pct >= settings.storage_warn_percent else "ok"
    return {"used_bytes": used, "capacity_bytes": cap, "percent": pct, "level": level}


def apply_retention(db: Session, dry_run: bool = False) -> list[int]:
    policy = get_policy(db)
    referenced = set(db.scalars(select(RestoreJob.target_configuration_id)).all()) | \
        {i for i in db.scalars(select(RestoreJob.pre_restore_configuration_id)).all() if i}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=policy.max_age_days)) if policy.max_age_days else None
    deleted: list[int] = []
    groups: dict[tuple, list[Configuration]] = {}
    for c in db.scalars(select(Configuration).order_by(Configuration.version_number.desc())).all():
        groups.setdefault((c.device_id, c.config_type), []).append(c)
    for versions in groups.values():
        for idx, c in enumerate(versions):  # newest first
            if idx == 0 or c.is_protected or c.id in referenced:
                continue  # never delete the only/latest recoverable config
            created = c.created_at if c.created_at.tzinfo else c.created_at.replace(tzinfo=timezone.utc)
            too_many = policy.max_versions_per_device and idx >= policy.max_versions_per_device
            too_old = cutoff is not None and created < cutoff
            if too_many or too_old:
                deleted.append(c.id)
                if not dry_run:
                    storage.delete_config(c.storage_key)
                    db.delete(c)
    if not dry_run:
        db.commit()
        if deleted:
            audit(db, None, "retention_cleanup", None, f"deleted {len(deleted)} versions: {deleted[:50]}", username="scheduler")
    return deleted


def scheduled_cleanup() -> None:
    db = SessionLocal()
    try:
        apply_retention(db)
        st = storage_status()
        if st["level"] != "ok":
            notify(db, "storage_threshold", f"Backup storage at {st['percent']}%",
                   f"{st['used_bytes']} of {st['capacity_bytes']} bytes used", st["level"])
    finally:
        db.close()
