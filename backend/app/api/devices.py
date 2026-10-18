from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import BackupJob, Configuration, Device, DeviceGroup, StateSnapshot, User
from app.network.base_driver import DeviceError
from app.network.connection import get_driver
from app.schemas import (
    BackupRequest, ConfigOut, DeviceIn, DeviceOut, DeviceUpdate, GroupIn, GroupOut, JobOut, SnapshotOut,
)
from app.security.auth import client_ip, get_current_user, require_role
from app.services import backup_service, device_service
from app.services.audit import audit

router = APIRouter(tags=["devices"])


def _device(db: Session, device_id: int) -> Device:
    d = db.get(Device, device_id)
    if d is None:
        raise HTTPException(404, "Device not found")
    return d


# ---- groups
@router.get("/groups", response_model=list[GroupOut])
def list_groups(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(DeviceGroup).order_by(DeviceGroup.name)).all()


@router.post("/groups", response_model=GroupOut, status_code=201)
def create_group(body: GroupIn, request: Request, user: User = Depends(require_role("admin")),
                 db: Session = Depends(get_db)):
    g = DeviceGroup(name=body.name, description=body.description)
    db.add(g)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Group name already exists")
    audit(db, user, "group_create", details=g.name, source_ip=client_ip(request))
    return g


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(group_id: int, request: Request, user: User = Depends(require_role("admin")),
                 db: Session = Depends(get_db)):
    g = db.get(DeviceGroup, group_id)
    if g is None:
        raise HTTPException(404, "Group not found")
    db.delete(g)
    db.commit()
    audit(db, user, "group_delete", details=g.name, source_ip=client_ip(request))


# ---- devices
@router.get("/devices", response_model=list[DeviceOut])
def list_devices(group_id: int | None = None, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(Device).order_by(Device.name)
    if group_id:
        q = q.where(Device.group_id == group_id)
    return db.scalars(q).all()


@router.post("/devices", response_model=DeviceOut, status_code=201)
def create_device(body: DeviceIn, request: Request, user: User = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    try:
        device_service.validate_device_fields(body.name, body.ip_address, body.ssh_port, body.platform)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not body.username or not body.password:
        raise HTTPException(422, "SSH username and password are required")
    d = Device(name=body.name, hostname=body.hostname, ip_address=body.ip_address, platform=body.platform,
               ssh_port=body.ssh_port, location=body.location, description=body.description,
               group_id=body.group_id, is_enabled=body.is_enabled)
    device_service.set_credentials(d, body.username, body.password, body.enable_secret)
    db.add(d)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A device with this name already exists (or invalid group)")
    audit(db, user, "device_create", d.id, f"{d.name} {d.ip_address}", source_ip=client_ip(request))
    return d


@router.get("/devices/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _device(db, device_id)


@router.put("/devices/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, body: DeviceUpdate, request: Request,
                  user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    d = _device(db, device_id)
    data = body.model_dump(exclude_unset=True)
    creds = {k: data.pop(k) for k in ("username", "password", "enable_secret") if k in data}
    for k, v in data.items():
        setattr(d, k, v)
    try:
        device_service.validate_device_fields(d.name, d.ip_address, d.ssh_port, d.platform)
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e))
    if creds:
        cur = device_service.build_target(d)
        device_service.set_credentials(
            d, creds.get("username") or cur.username, creds.get("password") or cur.password,
            creds["enable_secret"] if "enable_secret" in creds else cur.enable_secret)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Name already in use (or invalid group)")
    audit(db, user, "device_update", d.id, f"{d.name} fields={sorted(body.model_dump(exclude_unset=True))}",
          source_ip=client_ip(request))
    return d


@router.delete("/devices/{device_id}", status_code=204)
def delete_device(device_id: int, request: Request, user: User = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    d = _device(db, device_id)
    if db.scalar(select(Configuration.id).where(Configuration.device_id == d.id).limit(1)):
        raise HTTPException(409, "Device has stored backups. Disable it instead, or purge its backups first.")
    audit(db, user, "device_delete", d.id, d.name, source_ip=client_ip(request))
    db.delete(d)
    db.commit()


@router.post("/devices/{device_id}/test-connection")
def test_connection(device_id: int, request: Request, user: User = Depends(require_role("operator")),
                    db: Session = Depends(get_db)):
    d = _device(db, device_id)
    res = device_service.test_connection(db, d)
    audit(db, user, "device_test", d.id, "ok" if d.last_test_ok else f"failed: {res.get('error')}",
          "SUCCESS" if d.last_test_ok else "FAILED", client_ip(request))
    return res


@router.post("/devices/{device_id}/backup", response_model=list[JobOut], status_code=202)
def backup_now(device_id: int, request: Request, body: BackupRequest | None = None,
               user: User = Depends(require_role("operator")), db: Session = Depends(get_db)):
    d = _device(db, device_id)
    if not d.is_enabled:
        raise HTTPException(409, "Device is disabled")
    types = (body or BackupRequest()).config_types
    if not types or not set(types) <= set(backup_service.CONFIG_TYPES):
        raise HTTPException(422, "config_types must be a list of: running, startup")
    jobs = [backup_service.create_job(db, d, t, "manual", user.username) for t in dict.fromkeys(types)]
    audit(db, user, "backup_request", d.id, f"jobs={[j.id for j in jobs]}", source_ip=client_ip(request))
    for j in jobs:
        backup_service.enqueue(j.id)
    for j in jobs:
        db.refresh(j)  # inline mode (tests) may already have finished
    return jobs


@router.get("/devices/{device_id}/backups", response_model=list[ConfigOut])
def device_backups(device_id: int, config_type: str | None = None, _: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    _device(db, device_id)
    q = select(Configuration).where(Configuration.device_id == device_id)
    if config_type:
        q = q.where(Configuration.config_type == config_type)
    return db.scalars(q.order_by(Configuration.created_at.desc(), Configuration.id.desc())).all()


# ---- operational state snapshots (separate from config backups)
@router.post("/devices/{device_id}/snapshot", response_model=SnapshotOut, status_code=201)
def take_snapshot(device_id: int, request: Request, user: User = Depends(require_role("operator")),
                  db: Session = Depends(get_db)):
    d = _device(db, device_id)
    try:
        data = get_driver(device_service.build_target(d)).collect_state()
    except DeviceError as e:
        raise HTTPException(502, f"{e.code}: {e}")
    s = StateSnapshot(device_id=d.id, created_by=user.username, data=data)
    db.add(s)
    db.commit()
    audit(db, user, "state_snapshot", d.id, source_ip=client_ip(request))
    return s


@router.get("/devices/{device_id}/snapshots", response_model=list[SnapshotOut])
def list_snapshots(device_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _device(db, device_id)
    return db.scalars(select(StateSnapshot).where(StateSnapshot.device_id == device_id)
                      .order_by(StateSnapshot.created_at.desc()).limit(20)).all()


@router.get("/devices/{device_id}/jobs", response_model=list[JobOut])
def device_jobs(device_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _device(db, device_id)
    return db.scalars(select(BackupJob).where(BackupJob.device_id == device_id)
                      .order_by(BackupJob.id.desc()).limit(50)).all()


# ---- demo helper (mock driver only)
@router.post("/devices/{device_id}/mock/change")
def mock_change(device_id: int, user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    if settings.driver_mode != "mock":
        raise HTTPException(404, "Not available")
    from datetime import datetime
    from app.network import mock_driver
    d = _device(db, device_id)
    line = f"snmp-server location demo-{datetime.now():%H%M%S}"
    mock_driver.mutate(device_service.build_target(d), line)
    return {"applied": line}
