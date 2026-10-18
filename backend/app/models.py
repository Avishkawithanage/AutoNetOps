"""SQLAlchemy models. Timestamps are stored in UTC."""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, JSON, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin | operator | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceGroup(Base):
    __tablename__ = "device_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255), default="")
    ip_address: Mapped[str] = mapped_column(String(64))
    vendor: Mapped[str] = mapped_column(String(32), default="cisco")
    platform: Mapped[str] = mapped_column(String(32), default="cisco_ios")  # cisco_ios | cisco_xe
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    location: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(String(255), default="")
    group_id: Mapped[int | None] = mapped_column(ForeignKey("device_groups.id", ondelete="SET NULL"), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Last connection test result
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    group: Mapped[DeviceGroup | None] = relationship()
    credential: Mapped["Credential | None"] = relationship(
        back_populates="device", uselist=False, cascade="all, delete-orphan"
    )


class Credential(Base):
    """Device credentials, Fernet-encrypted. The key never lives in the database."""
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), unique=True)
    username_enc: Mapped[str] = mapped_column(Text)
    password_enc: Mapped[str] = mapped_column(Text)
    enable_enc: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    device: Mapped[Device] = relationship(back_populates="credential")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # hourly | every_n_hours | daily | weekly | monthly | cron
    frequency: Mapped[str] = mapped_column(String(20))
    time_of_day: Mapped[str] = mapped_column(String(5), default="02:00")  # HH:MM
    interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    days_of_week: Mapped[str] = mapped_column(String(40), default="")  # e.g. "mon,thu"
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cron_expression: Mapped[str] = mapped_column(String(100), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    config_types: Mapped[str] = mapped_column(String(40), default="running,startup")
    target_group_id: Mapped[int | None] = mapped_column(ForeignKey("device_groups.id", ondelete="SET NULL"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Configuration(Base):
    """One distinct stored configuration version."""
    __tablename__ = "configurations"
    __table_args__ = (UniqueConstraint("device_id", "config_type", "version_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    config_type: Mapped[str] = mapped_column(String(10))  # running | startup
    storage_key: Mapped[str] = mapped_column(String(500))
    checksum_sha256: Mapped[str] = mapped_column(String(64))  # over the exact raw content
    normalized_checksum: Mapped[str] = mapped_column(String(64))  # over normalized content (change detection)
    size_bytes: Mapped[int] = mapped_column(Integer)
    backup_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    change_status: Mapped[str] = mapped_column(String(20), default="CHANGED")  # CHANGED | NOT_COMPARABLE
    is_protected: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="backup")  # backup | pre_restore

    device: Mapped[Device] = relationship()


class BackupJob(Base):
    __tablename__ = "backup_jobs"
    __table_args__ = (Index("ix_backup_jobs_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)
    scheduled_for: Mapped[str | None] = mapped_column(String(32), nullable=True)  # run key, prevents duplicate runs
    job_type: Mapped[str] = mapped_column(String(20), default="manual")  # manual | scheduled | pre_restore | safety
    config_type: Mapped[str] = mapped_column(String(10), default="running")
    status: Mapped[str] = mapped_column(String(12), default="PENDING")
    change_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # CHANGED | UNCHANGED | NOT_COMPARABLE
    requested_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration_id: Mapped[int | None] = mapped_column(ForeignKey("configurations.id", ondelete="SET NULL"), nullable=True)

    device: Mapped[Device] = relationship()


class RestoreJob(Base):
    __tablename__ = "restore_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    target_configuration_id: Mapped[int] = mapped_column(ForeignKey("configurations.id", ondelete="RESTRICT"))
    pre_restore_configuration_id: Mapped[int | None] = mapped_column(ForeignKey("configurations.id", ondelete="SET NULL"), nullable=True)
    # PENDING_APPROVAL PENDING RUNNING SUCCESS FAILED NEEDS_REVIEW UNCERTAIN REJECTED CANCELLED
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    mode: Mapped[str] = mapped_column(String(10), default="merge")  # merge | replace
    save_startup: Mapped[bool] = mapped_column(Boolean, default=False)
    is_recovery: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    performed_by: Mapped[str] = mapped_column(String(64), default="")
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recovery_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped[Device] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # no FK: audit rows outlive users
    username: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(60), index=True)
    device_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    details: Mapped[str] = mapped_column(Text, default="")
    source_ip: Mapped[str] = mapped_column(String(64), default="")
    result: Mapped[str] = mapped_column(String(20), default="SUCCESS")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info | warning | critical
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, default="")
    device_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivery: Mapped[str] = mapped_column(String(200), default="")  # outcome of email/webhook delivery
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)


class StateSnapshot(Base):
    """Operational state (version, interfaces, VLANs, routes). Separate from config backups."""
    __tablename__ = "state_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    data: Mapped[dict] = mapped_column(JSON)


class RetentionPolicy(Base):
    """Single-row policy (id == 1)."""
    __tablename__ = "retention_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    max_versions_per_device: Mapped[int] = mapped_column(Integer, default=30)
    max_age_days: Mapped[int] = mapped_column(Integer, default=0)  # 0 = no age limit
