"""Application settings, loaded from environment variables / .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # project root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    app_name: str = "AutoNetOps"
    environment: str = "development"

    # Database: SQLite for development, PostgreSQL for production
    database_url: str = f"sqlite:///{(BASE_DIR / 'autonetops.db').as_posix()}"
    auto_create_tables: bool = True  # dev convenience; production uses `alembic upgrade head`

    # Security
    secret_key: str = ""  # JWT signing key; generated into secrets/ when empty (dev only)
    encryption_key: str = ""  # Fernet key for credentials + backup files; generated when empty (dev only)
    access_token_minutes: int = 60
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    cors_origins: str = "http://localhost:5173,http://localhost:8000"
    admin_username: str = "admin"
    admin_password: str = ""  # bootstrap admin, created only when the users table is empty

    # Storage
    backup_dir: str = str(BASE_DIR / "backup_storage")
    secrets_dir: str = str(BASE_DIR / "secrets")
    storage_capacity_bytes: int = 5 * 1024**3  # logical quota used for usage warnings
    storage_warn_percent: int = 80
    storage_critical_percent: int = 90

    # Network automation
    driver_mode: str = "cisco"  # "cisco" (Netmiko over SSH) or "mock" (in-memory, for demo/tests)
    ssh_strict_host_key: bool = True
    ssh_known_hosts_file: str = str(BASE_DIR / "secrets" / "known_hosts")
    ssh_connect_timeout: int = 15
    ssh_command_timeout: int = 60

    # Jobs
    max_concurrent_jobs: int = 5
    max_retries: int = 2
    retry_backoff_seconds: float = 5.0
    device_lock_timeout: int = 120
    run_jobs_inline: bool = False  # tests: run jobs synchronously
    scheduler_enabled: bool = True

    # Restore policy
    restore_requires_approval: bool = False
    restore_save_startup: bool = False  # `write memory` after a verified restore

    # Notifications (all optional)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "autonetops@localhost"
    notify_email_to: str = ""
    webhook_url: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
