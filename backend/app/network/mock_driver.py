"""In-memory Cisco simulator for demos and tests (DRIVER_MODE=mock). No network access."""
import threading
from datetime import datetime, timezone

from app.network.base_driver import (
    ApplyResult, BaseDriver, DeviceAuthError, DeviceConnectionError, DeviceTarget, DeviceTimeout,
)
from app.network.cisco_ios import sanitize_for_merge, validate_config_output

_lock = threading.Lock()
STORE: dict[str, dict[str, str]] = {}  # device name -> {"running": str, "startup": str}
FAILURES: dict[str, str] = {}  # device name -> timeout | auth | unreachable | bad_output | drop_on_apply


def reset() -> None:
    with _lock:
        STORE.clear()
        FAILURES.clear()


def _default_config(t: DeviceTarget) -> str:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC %a %b %d %Y")
    return (
        "Building configuration...\n\n"
        "Current configuration : 1024 bytes\n!\n"
        f"! Last configuration change at {stamp}\n!\n"
        "version 17.3\nservice timestamps debug datetime msec\n!\n"
        f"hostname {t.name}\n!\n"
        "interface GigabitEthernet0/0\n description management\n"
        f" ip address {t.ip_address} 255.255.255.0\n no shutdown\n!\n"
        "interface GigabitEthernet0/1\n no ip address\n shutdown\n!\n"
        "ip ssh version 2\nntp server 192.0.2.123\n!\nline vty 0 4\n transport input ssh\n!\nend\n"
    )


def _state(t: DeviceTarget) -> dict[str, str]:
    with _lock:
        if t.name not in STORE:
            cfg = _default_config(t)
            STORE[t.name] = {"running": cfg, "startup": cfg}
        return STORE[t.name]


def mutate(t: DeviceTarget, line: str) -> None:
    """Demo helper: append a config line to the simulated running-config (before `end`)."""
    st = _state(t)
    body = st["running"].rstrip().removesuffix("end").rstrip()
    st["running"] = f"{body}\n{line}\n!\nend\n"


class MockDriver(BaseDriver):
    def _check_failure(self, stage: str = "") -> None:
        f = FAILURES.get(self.target.name)
        if f == "timeout":
            raise DeviceTimeout("Simulated timeout")
        if f == "auth":
            raise DeviceAuthError("Simulated authentication failure")
        if f == "unreachable":
            raise DeviceConnectionError("Simulated unreachable device")

    def test_connection(self) -> dict:
        res = {"reachable": False, "ssh_auth": False, "privileged": None, "platform": None, "error": None}
        f = FAILURES.get(self.target.name)
        if f == "unreachable" or f == "timeout":
            res["error"] = "Simulated: device unreachable"
            return res
        res["reachable"] = True
        if f == "auth":
            res["error"] = "AUTH_FAILED: Simulated authentication failure"
            return res
        res.update(ssh_auth=True, privileged=True, platform=self.target.platform)
        return res

    def get_config(self, config_type: str) -> str:
        self._check_failure()
        if FAILURES.get(self.target.name) == "bad_output":
            return validate_config_output("% Invalid input detected at '^' marker.", config_type)
        return validate_config_output(_state(self.target)[config_type], config_type)

    def collect_state(self) -> dict[str, str]:
        self._check_failure()
        t = self.target
        return {
            "version": f"Cisco IOS XE Software, Version 17.3 (simulated)\n{t.name} uptime is 1 day",
            "interfaces": f"GigabitEthernet0/0  {t.ip_address}  YES manual up up",
            "vlans": "1 default active",
            "routes": f"C 192.0.2.0/24 is directly connected, GigabitEthernet0/0",
        }

    def apply_config(self, text: str, mode: str) -> ApplyResult:
        self._check_failure()
        st = _state(self.target)
        if mode == "replace":
            st["running"] = text if text.endswith("\n") else text + "\n"
        else:
            existing = {l.strip() for l in st["running"].splitlines()}
            body = st["running"].rstrip().removesuffix("end").rstrip()
            new = [l for l in sanitize_for_merge(text) if l.strip() not in existing]
            st["running"] = body + "\n" + "\n".join(new) + "\n!\nend\n"
        if FAILURES.get(self.target.name) == "drop_on_apply":
            raise DeviceConnectionError("Simulated: connection lost during restore")
        return ApplyResult()

    def save_config(self) -> None:
        st = _state(self.target)
        st["startup"] = st["running"]
