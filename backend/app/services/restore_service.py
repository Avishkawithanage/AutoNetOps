"""Controlled restore: validate -> pre-restore backup -> apply -> verify -> record.

A pre-restore backup helps recovery but cannot guarantee it. Outcomes that cannot be
verified are marked UNCERTAIN, never assumed successful or failed.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal
from app.models import Configuration, Device, RestoreJob, User
from app.network import commands as C
from app.network.base_driver import DeviceError
from app.network.connection import get_driver
from app.services import diff_service, storage
from app.services.audit import audit
from app.services.backup_service import latest_config, store_version, verify_integrity
from app.services.device_service import build_target
from app.services.notification_service import notify
from app.workers import executor

log = logging.getLogger("autonetops.restore")
ACTIVE = ("PENDING_APPROVAL", "PENDING", "RUNNING")


class RestoreBlocked(Exception):
    """Validation errors: the restore must not proceed."""
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class RestoreNeedsAck(Exception):
    """Warnings the operator must explicitly acknowledge."""
    def __init__(self, warnings: list[str]):
        super().__init__("; ".join(warnings))
        self.warnings = warnings


def validate_restore(db: Session, device: Device, cfg: Configuration) -> dict:
    errors, warnings = [], []
    if cfg.device_id != device.id:
        errors.append("Configuration belongs to a different device")
    if cfg.config_type != "running":
        errors.append("Only running-config versions can be restored")
    if not verify_integrity(cfg):
        errors.append("Integrity check failed: stored file does not match its recorded SHA-256 checksum")
        return {"errors": errors, "warnings": warnings}
    text = storage.read_config(cfg.storage_key)
    lines = [l.strip().lower() for l in text.splitlines() if l.strip()]
    if len(lines) < 5 or lines[-1] != "end":
        errors.append("Configuration looks incomplete (too short or missing terminating 'end')")
    for l in lines:
        if any(l.startswith(p) for p in C.DANGEROUS_PATTERNS):
            errors.append(f"Configuration contains a blocked command: '{l[:60]}'")
    if device.platform not in ("cisco_ios", "cisco_xe"):
        errors.append(f"Unsupported platform for restore: {device.platform}")
    if f"ip address {device.ip_address} " not in text.lower() + " ":
        warnings.append(
            f"Target config does not contain the management IP {device.ip_address}. "
            "Applying it may disconnect AutoNetOps from the device.")
    cur = latest_config(db, device.id, "running")
    notes = []
    if cur is not None and cur.id == cfg.id:
        notes.append("Target version is already the latest stored version (little or no change expected)")
    return {"errors": errors, "warnings": warnings, "notes": notes}


def create_restore(db: Session, user: User, device: Device, cfg: Configuration, mode: str,
                   save_startup: bool, acknowledge_risks: bool, is_recovery: bool = False,
                   pre_restore_id: int | None = None) -> RestoreJob:
    if mode not in ("merge", "replace"):
        raise RestoreBlocked(["mode must be 'merge' or 'replace'"])
    if not device.is_enabled:
        raise RestoreBlocked(["Device is disabled"])
    v = validate_restore(db, device, cfg)
    if v["errors"]:
        raise RestoreBlocked(v["errors"])
    if v["warnings"] and not acknowledge_risks:
        raise RestoreNeedsAck(v["warnings"])
    busy = db.scalar(select(RestoreJob.id).where(RestoreJob.device_id == device.id, RestoreJob.status.in_(ACTIVE)))
    if busy:
        raise RestoreBlocked([f"Another restore (#{busy}) is already active on this device"])
    needs_approval = settings.restore_requires_approval and not is_recovery
    job = RestoreJob(
        device_id=device.id, target_configuration_id=cfg.id, mode=mode,
        save_startup=save_startup or settings.restore_save_startup, is_recovery=is_recovery,
        status="PENDING_APPROVAL" if needs_approval else "PENDING", performed_by=user.username,
        validation_warnings=v["warnings"], pre_restore_configuration_id=pre_restore_id,
    )
    db.add(job)
    db.commit()
    if not needs_approval:
        executor.submit(run_restore_job, job.id)
    return job


def approve_restore(db: Session, job: RestoreJob, approver: User) -> RestoreJob:
    if job.status != "PENDING_APPROVAL":
        raise RestoreBlocked(["Restore is not awaiting approval"])
    if approver.username == job.performed_by:
        raise RestoreBlocked(["Second-person approval required: the requester cannot approve their own restore"])
    job.approved_by, job.status = approver.username, "PENDING"
    db.commit()
    executor.submit(run_restore_job, job.id)
    return job


def _lines(text: str) -> list[str]:
    return [l.strip() for l in diff_service.normalize(text).splitlines() if l.strip() and l.strip() != "end"]


def verify(target_text: str, actual_text: str) -> dict:
    t, a = _lines(target_text), _lines(actual_text)
    ts, as_ = set(t), set(a)
    missing = [l for l in t if l not in as_]
    extra = [l for l in a if l not in ts]
    return {"missing_count": len(missing), "extra_count": len(extra),
            "missing": missing[:50], "extra": extra[:50]}


def _finish(db: Session, job: RestoreJob, status: str, error: str | None = None, **kw) -> None:
    job.status, job.completed_at, job.error_message = status, datetime.now(timezone.utc), error
    for k, v in kw.items():
        setattr(job, k, v)
    db.commit()


def run_restore_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(RestoreJob, job_id)
        if job is None or job.status != "PENDING":
            return
        device = db.get(Device, job.device_id)
        target = db.get(Configuration, job.target_configuration_id)
        try:
            with executor.device_lock(device.id):
                _execute(db, job, device, target)
        except TimeoutError as e:
            _finish(db, job, "FAILED", str(e))
            audit(db, None, "restore", device.id, f"job={job.id} {e}", "FAILED", username=job.performed_by)
        except Exception as e:
            log.exception("Restore %s crashed", job_id)
            _finish(db, job, "UNCERTAIN", f"Unexpected error: {type(e).__name__}: {e}. Verify device state manually.")
            audit(db, None, "restore", device.id, f"job={job.id} crashed", "UNCERTAIN", username=job.performed_by)
    finally:
        db.close()


def _execute(db: Session, job: RestoreJob, device: Device, target: Configuration) -> None:
    job.status, job.started_at = "RUNNING", datetime.now(timezone.utc)
    db.commit()
    user = job.performed_by
    driver = get_driver(build_target(device))

    # 1. Re-verify the target right before use (it may have been tampered with since request time)
    v = validate_restore(db, device, target)
    if v["errors"]:
        _finish(db, job, "FAILED", "Validation failed: " + "; ".join(v["errors"]))
        notify(db, "restore_blocked", f"{device.name}: restore blocked", "; ".join(v["errors"]), "critical", device.id)
        audit(db, None, "restore", device.id, f"job={job.id} blocked: {v['errors']}", "FAILED", username=user)
        return
    target_text = storage.read_config(target.storage_key)

    # 2. Pre-restore safety backup (abort if it cannot be created and verified)
    try:
        current = driver.get_config("running")
        pre, _ = store_version(db, device, "running", current, None, user, source="pre_restore", protect=True)
        if not verify_integrity(pre):
            raise DeviceError("pre-restore backup failed its integrity check", "PRE_BACKUP_INVALID")
        job.pre_restore_configuration_id = pre.id
        db.commit()
    except (DeviceError, OSError) as e:
        _finish(db, job, "FAILED", f"Pre-restore backup failed; nothing was applied: {e}")
        notify(db, "restore_failed", f"{device.name}: restore aborted", f"Pre-restore backup failed: {e}", "critical", device.id)
        audit(db, None, "restore", device.id, f"job={job.id} pre-restore backup failed", "FAILED", username=user)
        return

    # 3. Apply
    cli_errors: list[str] = []
    apply_lost = False
    try:
        res = driver.apply_config(target_text, job.mode)
        cli_errors = res.errors
    except DeviceError as e:
        apply_lost = True  # connection lost / timeout: the device may be partially configured
        cli_errors = [f"{e.code}: {e}"]

    # 4. Verify with a fresh connection
    try:
        actual = driver.get_config("running")
    except DeviceError as e:
        _finish(db, job, "UNCERTAIN",
                f"Could not verify device state after restore ({e.code}: {e}). Outcome unknown - check the device "
                "manually before any further action.",
                verification_result={"cli_errors": cli_errors}, recovery_status="MANUAL_CHECK_REQUIRED")
        notify(db, "restore_uncertain", f"{device.name}: restore outcome UNCERTAIN",
               "Device could not be verified after restore.", "critical", device.id)
        audit(db, None, "restore", device.id, f"job={job.id} uncertain", "UNCERTAIN", username=user)
        return

    result = verify(target_text, actual)
    result["cli_errors"] = cli_errors
    result["management_reachable"] = True  # we just reconnected over the management address
    if result["missing_count"] == 0 and result["extra_count"] == 0 and not cli_errors:
        status, rec = "SUCCESS", None
    elif result["missing_count"] == 0 and not apply_lost and not cli_errors:
        status, rec = "NEEDS_REVIEW", "ROLLBACK_AVAILABLE"  # extra lines remain (normal for merge mode)
    else:
        status, rec = "FAILED", "ROLLBACK_AVAILABLE"
    _finish(db, job, status, None if status == "SUCCESS" else "Verification did not match the target",
            verification_result=result, recovery_status=rec)

    # 5. Record the post-restore state as a version; optionally persist to startup
    try:
        store_version(db, device, "running", actual, None, user)
    except Exception:
        log.warning("Could not store post-restore version", exc_info=True)
    if status == "SUCCESS" and job.save_startup:
        try:
            driver.save_config()
        except DeviceError as e:
            job.error_message = f"Restored and verified, but saving to startup failed: {e}"
            db.commit()

    sev = "info" if status == "SUCCESS" else "critical"
    notify(db, "restore_result", f"{device.name}: restore {status}",
           f"Target v{target.version_number}; missing={result['missing_count']} extra={result['extra_count']}", sev, device.id)
    audit(db, None, "restore", device.id,
          f"job={job.id} target=v{target.version_number} mode={job.mode} -> {status}", status, username=user)


def start_recovery(db: Session, user: User, job: RestoreJob, acknowledge_risks: bool) -> RestoreJob:
    """Roll back by restoring the pre-restore configuration (always an explicit, admin-driven action)."""
    if job.pre_restore_configuration_id is None:
        raise RestoreBlocked(["No pre-restore backup exists for this restore"])
    if job.status not in ("FAILED", "NEEDS_REVIEW", "UNCERTAIN"):
        raise RestoreBlocked(["Recovery is only offered for FAILED, NEEDS_REVIEW or UNCERTAIN restores"])
    device = db.get(Device, job.device_id)
    pre = db.get(Configuration, job.pre_restore_configuration_id)
    new = create_restore(db, user, device, pre, "replace" if job.mode == "replace" else "merge",
                         False, acknowledge_risks, is_recovery=True)
    job.recovery_status = f"RECOVERY_STARTED(#{new.id})"
    db.commit()
    return new
