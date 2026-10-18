"""Backup engine: collect -> validate -> checksum -> compare -> store -> record."""
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal
from app.models import BackupJob, Configuration, Device
from app.network.base_driver import DeviceError
from app.network.connection import get_driver
from app.services import diff_service, storage
from app.services.audit import audit
from app.services.device_service import build_target
from app.services.notification_service import notify
from app.workers import executor

log = logging.getLogger("autonetops.backup")
CONFIG_TYPES = ("running", "startup")


def latest_config(db: Session, device_id: int, config_type: str, source: str | None = None) -> Configuration | None:
    q = select(Configuration).where(Configuration.device_id == device_id, Configuration.config_type == config_type)
    if source:
        q = q.where(Configuration.source == source)
    return db.scalars(q.order_by(Configuration.version_number.desc()).limit(1)).first()


def verify_integrity(cfg: Configuration) -> bool:
    """Recompute the SHA-256 of the stored file and compare with the recorded one."""
    try:
        return diff_service.sha256_text(storage.read_config(cfg.storage_key)) == cfg.checksum_sha256
    except Exception:
        return False


def store_version(db: Session, device: Device, config_type: str, content: str, job_id: int | None,
                  created_by: str, source: str = "backup", protect: bool = False) -> tuple[Configuration, str]:
    """Store `content` as a new version unless it is unchanged. Returns (configuration, change_status)."""
    norm = diff_service.normalized_checksum(content)
    prev = latest_config(db, device.id, config_type)
    if prev is not None and prev.normalized_checksum == norm:
        if protect and not prev.is_protected:
            prev.is_protected = True
            db.commit()
        return prev, "UNCHANGED"
    version = (db.scalar(select(func.max(Configuration.version_number)).where(
        Configuration.device_id == device.id, Configuration.config_type == config_type)) or 0) + 1
    key = storage.write_config(device.id, device.name, version, config_type, content)
    cfg = Configuration(
        device_id=device.id, version_number=version, config_type=config_type, storage_key=key,
        checksum_sha256=diff_service.sha256_text(content), normalized_checksum=norm,
        size_bytes=len(content.encode()), backup_job_id=job_id, created_by=created_by,
        change_status="CHANGED" if prev else "NOT_COMPARABLE", is_protected=protect, source=source,
    )
    try:
        db.add(cfg)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_config(key)  # never leave an orphan file if metadata was not committed
        raise
    return cfg, ("CHANGED" if prev else "NOT_COMPARABLE")


def create_job(db: Session, device: Device, config_type: str, job_type: str, requested_by: str,
               schedule_id: int | None = None, scheduled_for: str | None = None) -> BackupJob:
    job = BackupJob(device_id=device.id, config_type=config_type, job_type=job_type,
                    requested_by=requested_by, schedule_id=schedule_id, scheduled_for=scheduled_for)
    db.add(job)
    db.commit()
    return job


def enqueue(job_id: int) -> None:
    executor.submit(run_backup_job, job_id)


def _finish(db: Session, job: BackupJob, status: str, **kw) -> None:
    job.status = status
    job.completed_at = datetime.now(timezone.utc)
    for k, v in kw.items():
        setattr(job, k, v)
    db.commit()


def run_backup_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(BackupJob, job_id)
        if job is None or job.status != "PENDING":
            return  # cancelled or already handled
        device = db.get(Device, job.device_id)
        job.status, job.started_at = "RUNNING", datetime.now(timezone.utc)
        db.commit()
        if not device.is_enabled:
            _finish(db, job, "FAILED", error_code="DEVICE_DISABLED", error_message="Device is disabled")
            return
        try:
            with executor.device_lock(device.id):
                content = _collect_with_retries(db, job, device)
                cfg, change = store_version(db, device, job.config_type, content, job.id, job.requested_by)
        except TimeoutError as e:
            _fail(db, job, device, "DEVICE_BUSY", str(e), "FAILED")
            return
        except DeviceError as e:
            _fail(db, job, device, e.code, str(e), e.job_status)
            return
        except OSError as e:
            _fail(db, job, device, "STORAGE_ERROR", f"Could not write backup: {e}", "FAILED")
            notify(db, "storage_error", "Backup storage write failed", str(e), "critical", device.id)
            return
        except Exception as e:
            log.exception("Backup job %s crashed", job_id)
            _fail(db, job, device, "INTERNAL_ERROR", f"{type(e).__name__}: {e}", "FAILED")
            return

        _finish(db, job, "SUCCESS", change_status=change, configuration_id=cfg.id)
        audit(db, None, "backup", device.id, f"job={job.id} {job.config_type} v{cfg.version_number} {change}",
              username=job.requested_by)
        if change == "CHANGED":
            prev = db.scalars(select(Configuration).where(
                Configuration.device_id == device.id, Configuration.config_type == job.config_type,
                Configuration.version_number < cfg.version_number
            ).order_by(Configuration.version_number.desc()).limit(1)).first()
            if prev:
                d = diff_service.compute_diff(storage.read_config(prev.storage_key), storage.read_config(cfg.storage_key))
                cats = ", ".join(f"{k}:{v}" for k, v in d["categories"].items())
                notify(db, "config_changed", f"{device.name}: {job.config_type} config changed",
                       f"v{prev.version_number} -> v{cfg.version_number}: +{d['added']} / -{d['removed']} lines ({cats})",
                       "warning", device.id)
    finally:
        db.close()


def _collect_with_retries(db: Session, job: BackupJob, device: Device) -> str:
    driver = get_driver(build_target(device))
    attempt = 0
    while True:
        try:
            return driver.get_config(job.config_type)
        except DeviceError as e:
            if not e.transient or attempt >= settings.max_retries:
                raise
            attempt += 1
            job.retry_count = attempt
            db.commit()
            time.sleep(settings.retry_backoff_seconds * 2 ** (attempt - 1))  # bounded exponential backoff


def _fail(db: Session, job: BackupJob, device: Device, code: str, message: str, status: str) -> None:
    _finish(db, job, status, error_code=code, error_message=message[:1000])
    audit(db, None, "backup", device.id, f"job={job.id} {code}: {message[:300]}", "FAILED", username=job.requested_by)
    notify(db, "backup_failed", f"{device.name}: backup failed ({code})", message[:500],
           "critical" if code == "AUTH_FAILED" else "warning", device.id)
