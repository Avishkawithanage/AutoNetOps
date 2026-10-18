"""Startup recovery for jobs orphaned by a crash/restart of the previous process."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import BackupJob, RestoreJob
from app.services import backup_service


def recover_stale_jobs() -> dict:
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        running = db.scalars(select(BackupJob).where(BackupJob.status == "RUNNING")).all()
        for j in running:
            j.status, j.completed_at = "FAILED", now
            j.error_code, j.error_message = "WORKER_INTERRUPTED", "Process restarted while the job was running"
        restores = db.scalars(select(RestoreJob).where(RestoreJob.status == "RUNNING")).all()
        for r in restores:  # a restore may have been half-applied: never assume either outcome
            r.status, r.completed_at = "UNCERTAIN", now
            r.error_message = "Process restarted during restore. Verify the device state manually."
            r.recovery_status = "MANUAL_CHECK_REQUIRED"
        pending = [j.id for j in db.scalars(select(BackupJob).where(BackupJob.status == "PENDING")).all()]
        db.commit()
    finally:
        db.close()
    for jid in pending:
        backup_service.enqueue(jid)
    return {"failed_backups": len(running), "uncertain_restores": len(restores), "requeued": len(pending)}
