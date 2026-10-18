"""Cisco IOS / IOS-XE driver built on Netmiko (SSH)."""
import os
import re
import socket
import tempfile
from contextlib import contextmanager

from app.config import settings
from app.network import commands as C
from app.network.base_driver import (
    ApplyResult, BaseDriver, DeviceAuthError, DeviceCommandError, DeviceConnectionError,
    DeviceError, DeviceOutputError, DeviceTarget, DeviceTimeout,
)

_DEVICE_TYPES = {"cisco_ios": "cisco_ios", "cisco_xe": "cisco_xe"}


def validate_config_output(output: str, config_type: str) -> str:
    """Platform-specific sanity checks. Returns the output or raises DeviceOutputError."""
    text = output.replace("\r\n", "\n").strip("\n")
    for marker in C.CLI_ERROR_MARKERS:
        if marker.lower() in text.lower()[:400]:
            raise DeviceOutputError(f"Device returned a CLI error instead of a configuration: {marker}")
    if config_type == "startup" and "startup-config is not present" in text.lower():
        raise DeviceOutputError("Startup configuration is not present on the device", "NO_STARTUP_CONFIG")
    if len(text) < 30 or text.count("\n") < 2:
        raise DeviceOutputError("Configuration output is empty or implausibly short")
    tail = [l.strip() for l in text.splitlines() if l.strip()][-3:]
    if "end" not in tail:
        raise DeviceOutputError("Configuration output looks truncated (no terminating 'end')")
    return text + "\n"


def identify_platform(show_version: str) -> str:
    v = show_version.lower()
    if "ios-xe" in v or "ios xe" in v:
        return "cisco_xe"
    if "cisco ios software" in v or "ios (tm)" in v:
        return "cisco_ios"
    return "unknown"


def sanitize_for_merge(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        low = s.lower()
        if not s or s == "!" or low == "end":
            continue
        if low.startswith(C.RESTORE_SKIP_PREFIXES):
            continue
        out.append(line.rstrip())
    return out


class CiscoIOSDriver(BaseDriver):
    def _params(self) -> dict:
        t = self.target
        p = dict(
            device_type=_DEVICE_TYPES.get(t.platform, "cisco_ios"),
            host=t.ip_address, port=t.port, username=t.username, password=t.password,
            secret=t.enable_secret, timeout=settings.ssh_command_timeout,
            conn_timeout=settings.ssh_connect_timeout, auth_timeout=settings.ssh_connect_timeout,
            banner_timeout=settings.ssh_connect_timeout, fast_cli=False,
        )
        if settings.ssh_strict_host_key:
            if not os.path.isfile(settings.ssh_known_hosts_file):
                raise DeviceConnectionError(
                    f"Strict host-key checking is on but {settings.ssh_known_hosts_file} does not exist. "
                    "Add the device key (ssh-keyscan) or disable SSH_STRICT_HOST_KEY for a lab.",
                    "HOST_KEY_UNVERIFIED",
                )
            p.update(ssh_strict=True, system_host_keys=False, alt_host_keys=True,
                     alt_key_file=settings.ssh_known_hosts_file)
        return p

    @contextmanager
    def _connect(self):
        from netmiko import ConnectHandler
        from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
        import paramiko

        conn = None
        try:
            conn = ConnectHandler(**self._params())
            if self.target.enable_secret and not conn.check_enable_mode():
                conn.enable()
            yield conn
        except DeviceError:
            raise
        except NetmikoAuthenticationException as e:
            raise DeviceAuthError("SSH authentication failed") from e
        except NetmikoTimeoutException as e:
            raise DeviceTimeout("Connection or command timed out") from e
        except (paramiko.BadHostKeyException,) as e:
            raise DeviceConnectionError("SSH host key mismatch - possible impersonation", "HOST_KEY_MISMATCH") from e
        except paramiko.SSHException as e:
            msg = str(e)
            code = "HOST_KEY_UNKNOWN" if "known_hosts" in msg.lower() or "host key" in msg.lower() else "SSH_ERROR"
            raise DeviceConnectionError(f"SSH error: {msg}", code) from e
        except (socket.timeout, TimeoutError) as e:
            raise DeviceTimeout("Connection timed out") from e
        except OSError as e:
            raise DeviceConnectionError(f"Network error: {e}") from e
        finally:
            if conn is not None:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    # ---- interface -------------------------------------------------
    def test_connection(self) -> dict:
        res = {"reachable": False, "ssh_auth": False, "privileged": None, "platform": None, "error": None}
        try:
            with socket.create_connection((self.target.ip_address, self.target.port),
                                          timeout=settings.ssh_connect_timeout):
                res["reachable"] = True
        except OSError as e:
            res["error"] = f"TCP connect to port {self.target.port} failed: {e}"
            return res
        try:
            with self._connect() as conn:
                res["ssh_auth"] = True
                res["privileged"] = conn.check_enable_mode() if self.target.enable_secret else conn.find_prompt().endswith("#")
                res["platform"] = identify_platform(conn.send_command(C.STATE_COMMANDS["version"]))
        except DeviceError as e:
            res["error"] = f"{e.code}: {e}"
        return res

    def get_config(self, config_type: str) -> str:
        cmd = C.CONFIG_COMMANDS[config_type]
        with self._connect() as conn:
            out = conn.send_command(cmd, read_timeout=settings.ssh_command_timeout)
        return validate_config_output(out, config_type)

    def collect_state(self) -> dict[str, str]:
        data: dict[str, str] = {}
        with self._connect() as conn:
            for key, cmd in C.STATE_COMMANDS.items():
                try:
                    data[key] = conn.send_command(cmd, read_timeout=settings.ssh_command_timeout)
                except Exception as e:  # one unsupported command must not lose the rest
                    data[key] = f"<unavailable: {e}>"
        return data

    def apply_config(self, text: str, mode: str) -> ApplyResult:
        if mode == "replace":
            return self._apply_replace(text)
        lines = sanitize_for_merge(text)
        with self._connect() as conn:
            out = conn.send_config_set(lines, cmd_verify=False, read_timeout=settings.ssh_command_timeout)
        errors = [l.strip() for l in out.splitlines() if l.strip().startswith("%")]
        return ApplyResult(errors=errors, output="")

    def _apply_replace(self, text: str) -> ApplyResult:
        from netmiko.scp_functions import file_transfer

        fd, path = tempfile.mkstemp(suffix=".cfg")
        try:
            with os.fdopen(fd, "w", newline="\n") as f:
                f.write(text)
            with self._connect() as conn:
                res = file_transfer(conn, source_file=path, dest_file=C.REPLACE_FILE,
                                    file_system="flash:", direction="put", overwrite_file=True)
                if not res.get("file_verified"):
                    raise DeviceCommandError("Config file transfer to flash: could not be verified")
                out = conn.send_command(C.REPLACE_COMMAND, read_timeout=300, expect_string=r"[#>]")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        errors = [l.strip() for l in out.splitlines() if re.match(r"\s*%|.*fail", l, re.I)]
        return ApplyResult(errors=errors, output="")

    def save_config(self) -> None:
        with self._connect() as conn:
            conn.send_command_timing(C.SAVE_COMMAND)
