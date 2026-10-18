import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import AuditLog, BackupJob, Configuration, Device, Notification, RestoreJob, User
from app.schemas import AuditOut, NotificationOut, RetentionIn
from app.security.auth import client_ip, get_current_user, require_role
from app.services import retention_service
from app.services.audit import audit

router = APIRouter(tags=["reports"])


def _today_start() -> datetime:
    n = datetime.now(timezone.utc)
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def _count(db: Session, *where) -> int:
    return db.scalar(select(func.count()).select_from(BackupJob).where(*where)) or 0


@router.get("/reports/dashboard")
def dashboard(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t0 = _today_start()
    devs = db.scalars(select(Device).where(Device.is_enabled.is_(True))).all()
    last_ok = db.scalar(select(func.max(BackupJob.completed_at)).where(BackupJob.status == "SUCCESS"))
    st = retention_service.storage_status()
    return {
        "enabled_devices": len(devs),
        "reachable_devices": sum(1 for d in devs if d.last_test_ok is True),
        "failed_connection_tests": sum(1 for d in devs if d.last_test_ok is False),
        "backups_success_today": _count(db, BackupJob.status == "SUCCESS", BackupJob.completed_at >= t0),
        "backups_failed_today": _count(db, BackupJob.status.in_(("FAILED", "TIMEOUT")), BackupJob.completed_at >= t0),
        "unchanged_today": _count(db, BackupJob.change_status == "UNCHANGED", BackupJob.completed_at >= t0),
        "changes_today": _count(db, BackupJob.change_status == "CHANGED", BackupJob.completed_at >= t0),
        "pending_jobs": _count(db, BackupJob.status.in_(("PENDING", "RUNNING"))),
        "latest_successful_backup": last_ok,
        "storage": st,
        "unread_notifications": db.scalar(select(func.count()).select_from(Notification).where(Notification.is_read.is_(False))),
        "restores_awaiting_approval": db.scalar(select(func.count()).select_from(RestoreJob).where(RestoreJob.status == "PENDING_APPROVAL")),
    }


def _daily(db: Session, days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(select(BackupJob.status, BackupJob.change_status, BackupJob.device_id, BackupJob.completed_at)
                      .where(BackupJob.created_at >= since)).all()
    out: dict[str, dict] = {}
    for status, change, device_id, done in rows:
        day = (done or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        r = out.setdefault(day, {"date": day, "jobs": 0, "success": 0, "failed": 0, "unchanged": 0,
                                 "changed": 0, "devices_failed": set()})
        r["jobs"] += 1
        if status == "SUCCESS":
            r["success"] += 1
            r["unchanged"] += change == "UNCHANGED"
            r["changed"] += change == "CHANGED"
        elif status in ("FAILED", "TIMEOUT"):
            r["failed"] += 1
            r["devices_failed"].add(device_id)
    result = []
    for day in sorted(out, reverse=True):
        r = out[day]
        r["devices_not_reached"] = len(r.pop("devices_failed"))
        result.append(r)
    return result


@router.get("/reports/daily-backups")
def daily_backups(days: int = 14, format: str = "json", _: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    data = _daily(db, min(max(days, 1), 365))
    if format == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["date", "jobs", "success", "failed", "unchanged", "changed", "devices_not_reached"])
        w.writeheader()
        w.writerows(data)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": 'attachment; filename="daily-backups.csv"'})
    return data


@router.get("/reports/storage")
def storage_report(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    st = retention_service.storage_status()
    rows = db.execute(select(Device.name, func.count(Configuration.id), func.coalesce(func.sum(Configuration.size_bytes), 0))
                      .join(Configuration, Configuration.device_id == Device.id).group_by(Device.name)).all()
    st["per_device"] = [{"device": n, "versions": c, "bytes": int(b)} for n, c, b in rows]
    return st


@router.get("/audit-logs", response_model=list[AuditOut])
def audit_logs(action: str | None = None, device_id: int | None = None, username: str | None = None,
               limit: int = 200, offset: int = 0, _: User = Depends(require_role("operator")),
               db: Session = Depends(get_db)):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    if device_id:
        q = q.where(AuditLog.device_id == device_id)
    if username:
        q = q.where(AuditLog.username == username)
    return db.scalars(q.order_by(AuditLog.id.desc()).limit(min(limit, 1000)).offset(offset)).all()


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(limit: int = 100, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Notification).order_by(Notification.id.desc()).limit(min(limit, 500))).all()


@router.post("/notifications/read-all")
def mark_read(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.is_read.is_(False))).all():
        n.is_read = True
    db.commit()
    return {"ok": True}


# ---- retention
@router.get("/settings/retention")
def get_retention(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = retention_service.get_policy(db)
    return {"max_versions_per_device": p.max_versions_per_device, "max_age_days": p.max_age_days}


@router.put("/settings/retention")
def put_retention(body: RetentionIn, request: Request, user: User = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    p = retention_service.get_policy(db)
    p.max_versions_per_device, p.max_age_days = body.max_versions_per_device, body.max_age_days
    db.commit()
    audit(db, user, "retention_update", None, f"{body.model_dump()}", source_ip=client_ip(request))
    return body


@router.post("/settings/retention/run")
def run_retention(dry_run: bool = True, request: Request = None, user: User = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    ids = retention_service.apply_retention(db, dry_run=dry_run)
    audit(db, user, "retention_run", None, f"dry_run={dry_run} versions={len(ids)}", source_ip=client_ip(request))
    return {"dry_run": dry_run, "deleted_configuration_ids": ids}
