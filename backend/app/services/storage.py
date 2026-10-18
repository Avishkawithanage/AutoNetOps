"""Protected, encrypted-at-rest configuration storage. Paths derive from internal IDs only."""
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.security.crypto import decrypt_bytes, encrypt_bytes


def root() -> Path:
    p = Path(settings.backup_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:60] or "device"


def _resolve(storage_key: str) -> Path:
    p = (root() / storage_key).resolve()
    if root() not in p.parents:  # blocks path traversal via a tampered storage_key
        raise ValueError("Invalid storage key")
    return p


def write_config(device_id: int, device_name: str, version: int, config_type: str, content: str) -> str:
    now = datetime.now(timezone.utc)
    key = (f"{device_id}_{_safe(device_name)}/{now:%Y}/{now:%m}/"
           f"{_safe(device_name)}_{now:%Y-%m-%dT%H%M%SZ}_v{version:03d}_{config_type}.cfg.enc")
    path = _resolve(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(encrypt_bytes(content.encode("utf-8")))
    tmp.replace(path)  # atomic: never leaves a half-written version
    return key


def read_config(storage_key: str) -> str:
    return decrypt_bytes(_resolve(storage_key).read_bytes()).decode("utf-8")


def delete_config(storage_key: str) -> None:
    try:
        _resolve(storage_key).unlink(missing_ok=True)
    except ValueError:
        pass


def usage_bytes() -> int:
    return sum(f.stat().st_size for f in root().rglob("*") if f.is_file())
