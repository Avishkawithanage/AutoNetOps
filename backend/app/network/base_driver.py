"""Driver interface and error taxonomy. API routes and services never talk SSH directly."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DeviceTarget:
    """Everything a driver needs; deliberately not an ORM object."""
    name: str
    ip_address: str
    port: int = 22
    platform: str = "cisco_ios"
    username: str = ""
    password: str = ""
    enable_secret: str = ""


class DeviceError(Exception):
    code = "DEVICE_ERROR"
    transient = False  # worth retrying with backoff?
    job_status = "FAILED"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class DeviceTimeout(DeviceError):
    code = "TIMEOUT"
    transient = True
    job_status = "TIMEOUT"


class DeviceConnectionError(DeviceError):
    code = "UNREACHABLE"
    transient = True


class DeviceAuthError(DeviceError):
    """Bad credentials. Never retried: repeated attempts risk locking the account."""
    code = "AUTH_FAILED"


class DeviceOutputError(DeviceError):
    """Device answered, but the output is not a valid configuration."""
    code = "INVALID_OUTPUT"


class DeviceCommandError(DeviceError):
    code = "COMMAND_FAILED"


@dataclass
class ApplyResult:
    errors: list[str] = field(default_factory=list)  # device-reported CLI errors
    output: str = ""


class BaseDriver(ABC):
    def __init__(self, target: DeviceTarget):
        self.target = target

    @abstractmethod
    def test_connection(self) -> dict:
        """Per-stage result: reachable / ssh_auth / privileged / platform / error."""

    @abstractmethod
    def get_config(self, config_type: str) -> str:
        """Return raw `running` or `startup` configuration text (validated)."""

    @abstractmethod
    def collect_state(self) -> dict[str, str]:
        """Read-only operational commands -> output."""

    @abstractmethod
    def apply_config(self, text: str, mode: str) -> ApplyResult:
        """Apply configuration. mode: 'merge' or 'replace'."""

    @abstractmethod
    def save_config(self) -> None:
        """Persist running-config to startup-config."""
