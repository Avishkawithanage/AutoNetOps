from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth / users
class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(ORM):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


# ---- devices
class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""


class GroupOut(ORM):
    id: int
    name: str
    description: str


class DeviceIn(BaseModel):
    name: str
    hostname: str = ""
    ip_address: str
    platform: str = "cisco_ios"
    ssh_port: int = 22
    location: str = ""
    description: str = ""
    group_id: int | None = None
    is_enabled: bool = True
    username: str = ""
    password: str = ""
    enable_secret: str = ""


class DeviceUpdate(BaseModel):
    name: str | None = None
    hostname: str | None = None
    ip_address: str | None = None
    platform: str | None = None
    ssh_port: int | None = None
    location: str | None = None
    description: str | None = None
    group_id: int | None = None
    is_enabled: bool | None = None
    username: str | None = None
    password: str | None = None
    enable_secret: str | None = None


class DeviceOut(ORM):
    id: int
    name: str
    hostname: str
    ip_address: str
    vendor: str
    platform: str
    ssh_port: int
    location: str
    description: str
    group_id: int | None
    is_enabled: bool
    last_test_at: datetime | None
    last_test_ok: bool | None
    last_test_result: dict | None
    created_at: datetime
    updated_at: datetime


# ---- backups / configs
class BackupRequest(BaseModel):
    config_types: list[str] = ["running"]


class ConfigOut(ORM):
    id: int
    device_id: int
    version_number: int
    config_type: str
    checksum_sha256: str
    size_bytes: int
    backup_job_id: int | None
    created_at: datetime
    created_by: str
    change_status: str
    is_protected: bool
    source: str


class JobOut(ORM):
    id: int
    device_id: int
    schedule_id: int | None
    job_type: str
    config_type: str
    status: str
    change_status: str | None
    requested_by: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    retry_count: int
    error_code: str | None
    error_message: str | None
    configuration_id: int | None


class RestoreRequest(BaseModel):
    mode: str = "merge"
    save_startup: bool = False
    acknowledge_risks: bool = False
    confirm: bool = False  # must be true: explicit confirmation


class RestoreOut(ORM):
    id: int
    device_id: int
    target_configuration_id: int
    pre_restore_configuration_id: int | None
    status: str
    mode: str
    save_startup: bool
    is_recovery: bool
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    performed_by: str
    approved_by: str | None
    verification_result: dict | None
    validation_warnings: list | None
    recovery_status: str | None
    error_message: str | None


# ---- schedules
class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    frequency: str
    time_of_day: str = "02:00"
    interval_hours: int | None = None
    days_of_week: str = ""
    day_of_month: int | None = None
    cron_expression: str = ""
    timezone: str = "UTC"
    config_types: str = "running,startup"
    target_group_id: int | None = None
    enabled: bool = True


class ScheduleOut(ORM, ScheduleIn):
    id: int
    created_at: datetime
    last_run_at: datetime | None


# ---- misc
class AuditOut(ORM):
    id: int
    username: str
    action: str
    device_id: int | None
    details: str
    source_ip: str
    result: str
    timestamp: datetime


class NotificationOut(ORM):
    id: int
    event: str
    severity: str
    title: str
    message: str
    device_id: int | None
    created_at: datetime
    delivery: str
    is_read: bool


class RetentionIn(BaseModel):
    max_versions_per_device: int = Field(ge=1, le=10000)
    max_age_days: int = Field(ge=0, le=36500)


class SnapshotOut(ORM):
    id: int
    device_id: int
    created_at: datetime
    created_by: str
    data: dict[str, Any]
