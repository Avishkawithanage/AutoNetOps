from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import Configuration, Device, User
from app.schemas import ConfigOut, RestoreOut, RestoreRequest
from app.security.auth import client_ip, get_current_user, require_role
from app.services import diff_service, restore_service, storage
from app.services.audit import audit
from app.services.backup_service import latest_config, verify_integrity
from app.services.notification_service import notify

router = APIRouter(tags=["configurations"])


def _cfg(db: Session, cid: int) -> Configuration:
    c = db.get(Configuration, cid)
    if c is None:
        raise HTTPException(404, "Configuration not found")
    return c


def _read_verified(db: Session, cfg: Configuration, user: User | None = None) -> str:
    """Read a stored config, blocking and alerting if its checksum no longer matches."""
    try:
        text = storage.read_config(cfg.storage_key)
    except Exception:
        text = None
    if text is None or diff_service.sha256_text(text) != cfg.checksum_sha256:
        notify(db, "integrity_failure", f"Integrity failure: config #{cfg.id}",
               f"Stored file for device {cfg.device_id} v{cfg.version_number} does not match its checksum.",
               "critical", cfg.device_id)
        audit(db, user, "integrity_failure", cfg.device_id, f"config={cfg.id}", "FAILED")
        raise HTTPException(409, "Integrity check failed: stored configuration is corrupted or was modified")
    return text


@router.get("/configurations/{config_id}", response_model=ConfigOut)
def get_configuration(config_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _cfg(db, config_id)


@router.get("/configurations/{config_id}/content")
def get_content(config_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = _cfg(db, config_id)
    return {"id": cfg.id, "version_number": cfg.version_number, "content": _read_verified(db, cfg, user)}


@router.get("/configurations/{config_id}/download", response_class=PlainTextResponse)
def download(config_id: int, request: Request, user: User = Depends(require_role("operator")),
             db: Session = Depends(get_db)):
    cfg = _cfg(db, config_id)
    text = _read_verified(db, cfg, user)
    audit(db, user, "config_download", cfg.device_id, f"config={cfg.id}", source_ip=client_ip(request))
    dev = db.get(Device, cfg.device_id)
    fname = f"{dev.name}_v{cfg.version_number:03d}_{cfg.config_type}.cfg"
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/configurations/{config_id}/integrity")
def integrity(config_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = _cfg(db, config_id)
    return {"id": cfg.id, "ok": verify_integrity(cfg), "checksum_sha256": cfg.checksum_sha256}


@router.post("/configurations/{config_id}/protect", response_model=ConfigOut)
def set_protected(config_id: int, protected: bool = True, user: User = Depends(require_role("operator")),
                  db: Session = Depends(get_db)):
    cfg = _cfg(db, config_id)
    cfg.is_protected = protected
    db.commit()
    audit(db, user, "config_protect", cfg.device_id, f"config={cfg.id} protected={protected}")
    return cfg


@router.get("/compare")
def compare(source_id: int, target_id: int, normalized: bool = True,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a, b = _cfg(db, source_id), _cfg(db, target_id)
    if a.device_id != b.device_id or a.config_type != b.config_type:
        raise HTTPException(422, "Versions must belong to the same device and configuration type")
    result = diff_service.compute_diff(_read_verified(db, a, user), _read_verified(db, b, user), normalized)
    result["source"] = ConfigOut.model_validate(a).model_dump(mode="json")
    result["target"] = ConfigOut.model_validate(b).model_dump(mode="json")
    result["normalized"] = normalized
    return result


@router.get("/configurations/{config_id}/restore-preview")
def restore_preview(config_id: int, user: User = Depends(require_role("operator")), db: Session = Depends(get_db)):
    """Everything the confirmation screen needs: validation result + diff vs the current config."""
    cfg = _cfg(db, config_id)
    device = db.get(Device, cfg.device_id)
    validation = restore_service.validate_restore(db, device, cfg)
    current = latest_config(db, device.id, "running")
    diff = None
    if not validation["errors"] and current is not None:
        diff = diff_service.compute_diff(_read_verified(db, current, user), _read_verified(db, cfg, user))
        diff.pop("lines", None)
    return {"device": device.name, "current_version": current.version_number if current else None,
            "target_version": cfg.version_number, "validation": validation, "diff": diff,
            "requires_approval": settings.restore_requires_approval,
            "note": "Validation cannot prove a configuration is operationally safe. Test restores in a lab first."}


@router.post("/configurations/{config_id}/restore", response_model=RestoreOut, status_code=202)
def request_restore(config_id: int, body: RestoreRequest, request: Request,
                    user: User = Depends(require_role("operator")), db: Session = Depends(get_db)):
    if user.role != "admin" and not settings.restore_requires_approval:
        raise HTTPException(403, "Only administrators may restore unless approval workflow is enabled")
    if not body.confirm:
        raise HTTPException(422, "Explicit confirmation required: send confirm=true after reviewing the diff")
    cfg = _cfg(db, config_id)
    device = db.get(Device, cfg.device_id)
    ip = client_ip(request)
    try:
        job = restore_service.create_restore(db, user, device, cfg, body.mode, body.save_startup, body.acknowledge_risks)
    except restore_service.RestoreBlocked as e:
        audit(db, user, "restore_request", device.id, f"blocked: {e}", "FAILED", ip)
        raise HTTPException(422, {"errors": e.errors})
    except restore_service.RestoreNeedsAck as e:
        raise HTTPException(409, {"warnings": e.warnings, "message": "Acknowledge the risks and resubmit"})
    audit(db, user, "restore_request", device.id, f"restore={job.id} target=v{cfg.version_number} mode={job.mode}",
          source_ip=ip)
    db.refresh(job)
    return job
