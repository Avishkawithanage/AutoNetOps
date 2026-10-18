"""APScheduler integration: schedules in the DB -> one backup job per device per config type.

Timezone handling: every schedule stores an IANA timezone. APScheduler's cron trigger evaluates
wall-clock times in that zone, so a 02:00 job in a DST zone is skipped on the 'spring forward'
night's non-existent hour and runs once on 'fall back'.
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import BackupJob, Device, Schedule
from app.services import backup_service
from app.services.audit import audit

log = logging.getLogger("autonetops.scheduler")
scheduler = BackgroundScheduler(timezone="UTC")
FREQUENCIES = ("hourly", "every_n_hours", "daily", "weekly", "monthly", "cron")
_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def build_trigger(s: Schedule):
    """Build (and thereby validate) an APScheduler trigger. Raises ValueError on bad input."""
    try:
        tz = ZoneInfo(s.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown timezone '{s.timezone}'")
    try:
        hh, mm = (int(x) for x in s.time_of_day.split(":"))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError
    except ValueError:
        raise ValueError("time_of_day must be HH:MM")
    f = s.frequency
    if f == "hourly":
        return CronTrigger(minute=mm, timezone=tz)
    if f == "every_n_hours":
        if not s.interval_hours or not 1 <= s.interval_hours <= 168:
            raise ValueError("interval_hours must be 1-168")
        return IntervalTrigger(hours=s.interval_hours, timezone=tz)
    if f == "daily":
        return CronTrigger(hour=hh, minute=mm, timezone=tz)
    if f == "weekly":
        days = [d.strip().lower() for d in s.days_of_week.split(",") if d.strip()]
        if not days or not set(days) <= _DAYS:
            raise ValueError("days_of_week must be a comma list of mon,tue,wed,thu,fri,sat,sun")
        return CronTrigger(day_of_week=",".join(days), hour=hh, minute=mm, timezone=tz)
    if f == "monthly":
        if not s.day_of_month or not 1 <= s.day_of_month <= 28:
            raise ValueError("day_of_month must be 1-28 (avoids short-month gaps)")
        return CronTrigger(day=s.day_of_month, hour=hh, minute=mm, timezone=tz)
    if f == "cron":
        try:
            return CronTrigger.from_crontab(s.cron_expression, timezone=tz)
        except ValueError:
            raise ValueError("cron_expression must be a valid 5-field crontab")
    raise ValueError(f"frequency must be one of {FREQUENCIES}")


def validate_config_types(value: str) -> None:
    types = [t.strip() for t in value.split(",") if t.strip()]
    if not types or not set(types) <= set(backup_service.CONFIG_TYPES):
        raise ValueError("config_types must be a comma list of: running, startup")


def run_schedule(schedule_id: int) -> int:
    """Fire a schedule now. Returns number of jobs created. Idempotent per minute (run key)."""
    db = SessionLocal()
    try:
        s = db.get(Schedule, schedule_id)
        if s is None or not s.enabled:
            return 0
        run_key = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        q = select(Device).where(Device.is_enabled.is_(True))
        if s.target_group_id:
            q = q.where(Device.group_id == s.target_group_id)
        created = []
        for device in db.scalars(q).all():
            for ctype in (t.strip() for t in s.config_types.split(",") if t.strip()):
                dup = db.scalar(select(BackupJob.id).where(
                    BackupJob.schedule_id == s.id, BackupJob.device_id == device.id,
                    BackupJob.config_type == ctype, BackupJob.scheduled_for == run_key))
                if dup:
                    continue
                created.append(backup_service.create_job(
                    db, device, ctype, "scheduled", f"schedule:{s.name}", s.id, run_key).id)
        s.last_run_at = datetime.now(timezone.utc)
        db.commit()
        audit(db, None, "schedule_run", None, f"schedule={s.name} jobs={len(created)}", username="scheduler")
        for jid in created:
            backup_service.enqueue(jid)
        return len(created)
    finally:
        db.close()


def sync_schedule(s: Schedule) -> None:
    job_id = f"schedule-{s.id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if s.enabled:
        scheduler.add_job(run_schedule, build_trigger(s), args=[s.id], id=job_id,
                          coalesce=True, max_instances=1, misfire_grace_time=300)


def remove_schedule(schedule_id: int) -> None:
    if scheduler.get_job(f"schedule-{schedule_id}"):
        scheduler.remove_job(f"schedule-{schedule_id}")


def start() -> None:
    from app.services import retention_service
    db = SessionLocal()
    try:
        for s in db.scalars(select(Schedule)).all():
            try:
                sync_schedule(s)
            except ValueError as e:
                log.error("Schedule %s is invalid and was not loaded: %s", s.name, e)
    finally:
        db.close()
    scheduler.add_job(retention_service.scheduled_cleanup, CronTrigger(hour=3, minute=30, timezone="UTC"),
                      id="retention-cleanup", coalesce=True, max_instances=1)
    scheduler.start()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
