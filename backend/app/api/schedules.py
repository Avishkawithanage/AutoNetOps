from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Schedule, User
from app.schemas import ScheduleIn, ScheduleOut
from app.security.auth import client_ip, get_current_user, require_role
from app.services import scheduler_service as sched
from app.services.audit import audit

router = APIRouter(tags=["schedules"])


def _get(db: Session, sid: int) -> Schedule:
    s = db.get(Schedule, sid)
    if s is None:
        raise HTTPException(404, "Schedule not found")
    return s


def _validate(s: Schedule) -> None:
    try:
        sched.build_trigger(s)
        sched.validate_config_types(s.config_types)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/schedules", response_model=list[ScheduleOut])
def list_schedules(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Schedule).order_by(Schedule.name)).all()


@router.post("/schedules", response_model=ScheduleOut, status_code=201)
def create_schedule(body: ScheduleIn, request: Request, user: User = Depends(require_role("admin")),
                    db: Session = Depends(get_db)):
    s = Schedule(**body.model_dump(), created_by=user.id)
    _validate(s)
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Schedule name exists (or invalid group)")
    sched.sync_schedule(s)
    audit(db, user, "schedule_create", None, s.name, source_ip=client_ip(request))
    return s


@router.get("/schedules/{schedule_id}", response_model=ScheduleOut)
def get_schedule(schedule_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get(db, schedule_id)


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: int, body: ScheduleIn, request: Request,
                    user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    s = _get(db, schedule_id)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    try:
        _validate(s)
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    sched.sync_schedule(s)
    audit(db, user, "schedule_update", None, s.name, source_ip=client_ip(request))
    return s


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, request: Request, user: User = Depends(require_role("admin")),
                    db: Session = Depends(get_db)):
    s = _get(db, schedule_id)
    sched.remove_schedule(s.id)
    audit(db, user, "schedule_delete", None, s.name, source_ip=client_ip(request))
    db.delete(s)
    db.commit()


@router.post("/schedules/{schedule_id}/run")
def run_now(schedule_id: int, request: Request, user: User = Depends(require_role("admin")),
            db: Session = Depends(get_db)):
    s = _get(db, schedule_id)
    n = sched.run_schedule(s.id)
    audit(db, user, "schedule_run_now", None, f"{s.name} jobs={n}", source_ip=client_ip(request))
    return {"jobs_created": n}
