from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BackupJob, RestoreJob, User
from app.schemas import JobOut, RestoreOut
from app.security.auth import client_ip, get_current_user, require_role
from app.services import restore_service
from app.services.audit import audit

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(device_id: int | None = None, status: str | None = None, job_type: str | None = None,
              schedule_id: int | None = None, limit: int = 100, offset: int = 0,
              _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(BackupJob)
    for col, val in ((BackupJob.device_id, device_id), (BackupJob.status, status),
                     (BackupJob.job_type, job_type), (BackupJob.schedule_id, schedule_id)):
        if val is not None:
            q = q.where(col == val)
    return db.scalars(q.order_by(BackupJob.id.desc()).limit(min(limit, 500)).offset(offset)).all()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = db.get(BackupJob, job_id)
    if j is None:
        raise HTTPException(404, "Job not found")
    return j


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, request: Request, user: User = Depends(require_role("operator")),
               db: Session = Depends(get_db)):
    j = db.get(BackupJob, job_id)
    if j is None:
        raise HTTPException(404, "Job not found")
    if j.status != "PENDING":
        raise HTTPException(409, "Only PENDING jobs can be cancelled (running SSH sessions are not interrupted)")
    j.status, j.completed_at = "CANCELLED", datetime.now(timezone.utc)
    db.commit()
    audit(db, user, "job_cancel", j.device_id, f"job={j.id}", source_ip=client_ip(request))
    return j


# ---- restores
def _restore(db: Session, rid: int) -> RestoreJob:
    r = db.get(RestoreJob, rid)
    if r is None:
        raise HTTPException(404, "Restore not found")
    return r


@router.get("/restores", response_model=list[RestoreOut])
def list_restores(device_id: int | None = None, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(RestoreJob)
    if device_id:
        q = q.where(RestoreJob.device_id == device_id)
    return db.scalars(q.order_by(RestoreJob.id.desc()).limit(100)).all()


@router.get("/restores/{restore_id}", response_model=RestoreOut)
def get_restore(restore_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _restore(db, restore_id)


@router.post("/restores/{restore_id}/approve", response_model=RestoreOut, status_code=202)
def approve(restore_id: int, request: Request, user: User = Depends(require_role("admin")),
            db: Session = Depends(get_db)):
    r = _restore(db, restore_id)
    try:
        restore_service.approve_restore(db, r, user)
    except restore_service.RestoreBlocked as e:
        raise HTTPException(409, "; ".join(e.errors))
    audit(db, user, "restore_approve", r.device_id, f"restore={r.id}", source_ip=client_ip(request))
    db.refresh(r)
    return r


@router.post("/restores/{restore_id}/reject", response_model=RestoreOut)
def reject(restore_id: int, request: Request, user: User = Depends(require_role("admin")),
           db: Session = Depends(get_db)):
    r = _restore(db, restore_id)
    if r.status != "PENDING_APPROVAL":
        raise HTTPException(409, "Restore is not awaiting approval")
    r.status, r.completed_at, r.approved_by = "REJECTED", datetime.now(timezone.utc), user.username
    db.commit()
    audit(db, user, "restore_reject", r.device_id, f"restore={r.id}", source_ip=client_ip(request))
    return r


@router.post("/restores/{restore_id}/recover", response_model=RestoreOut, status_code=202)
def recover(restore_id: int, request: Request, acknowledge_risks: bool = False,
            user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    """Roll back to the pre-restore backup. Explicit admin action - never automatic."""
    r = _restore(db, restore_id)
    try:
        new = restore_service.start_recovery(db, user, r, acknowledge_risks)
    except restore_service.RestoreBlocked as e:
        raise HTTPException(409, "; ".join(e.errors))
    except restore_service.RestoreNeedsAck as e:
        raise HTTPException(409, {"warnings": e.warnings, "message": "Acknowledge the risks and resubmit"})
    audit(db, user, "restore_recover", r.device_id, f"restore={r.id} -> recovery restore={new.id}",
          source_ip=client_ip(request))
    db.refresh(new)
    return new
