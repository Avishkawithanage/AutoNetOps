import ipaddress
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Credential, Device
from app.network.base_driver import DeviceTarget
from app.network.connection import get_driver
from app.security.crypto import decrypt_text, encrypt_text

_NAME_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
PLATFORMS = ("cisco_ios", "cisco_xe")


def validate_device_fields(name: str, ip: str, port: int, platform: str) -> None:
    if not _NAME_RX.match(name):
        raise ValueError("Device name may contain letters, digits, '_', '.', '-' (max 100 chars)")
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError("Invalid management IP address")
    if not 1 <= port <= 65535:
        raise ValueError("SSH port must be 1-65535")
    if platform not in PLATFORMS:
        raise ValueError(f"Unsupported platform; use one of {PLATFORMS}")


def set_credentials(device: Device, username: str, password: str, enable_secret: str = "") -> None:
    if device.credential is None:
        device.credential = Credential(username_enc="", password_enc="", enable_enc="")
    device.credential.username_enc = encrypt_text(username)
    device.credential.password_enc = encrypt_text(password)
    device.credential.enable_enc = encrypt_text(enable_secret) if enable_secret else ""


def build_target(device: Device) -> DeviceTarget:
    c = device.credential
    return DeviceTarget(
        name=device.name, ip_address=device.ip_address, port=device.ssh_port, platform=device.platform,
        username=decrypt_text(c.username_enc) if c else "",
        password=decrypt_text(c.password_enc) if c else "",
        enable_secret=decrypt_text(c.enable_enc) if c else "",
    )


def test_connection(db: Session, device: Device) -> dict:
    result = get_driver(build_target(device)).test_connection()
    result["platform_matches"] = result.get("platform") in (None, "unknown", device.platform) if result["ssh_auth"] else None
    device.last_test_at = datetime.now(timezone.utc)
    device.last_test_ok = bool(result["reachable"] and result["ssh_auth"] and not result["error"])
    device.last_test_result = result
    db.commit()
    return result
