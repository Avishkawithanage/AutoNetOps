"""Key management + symmetric encryption (Fernet) for credentials and backup files.

In production set SECRET_KEY / ENCRYPTION_KEY via the environment or a secrets manager.
In development, missing keys are generated once into the (git-ignored) secrets/ directory.
"""
import os
import secrets
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _load_or_create(name: str, env_value: str, generator) -> str:
    if env_value:
        return env_value
    if settings.environment == "production":
        raise RuntimeError(f"{name} must be set in production")
    d = Path(settings.secrets_dir)
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    if not f.exists():
        f.write_text(generator())
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass
    return f.read_text().strip()


@lru_cache
def jwt_secret() -> str:
    return _load_or_create("secret_key", settings.secret_key, lambda: secrets.token_urlsafe(48))


@lru_cache
def _fernet() -> Fernet:
    return Fernet(_load_or_create("encryption_key", settings.encryption_key, lambda: Fernet.generate_key().decode()))


def encrypt_text(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_text(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Cannot decrypt value (wrong ENCRYPTION_KEY?)") from e


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    return _fernet().decrypt(data)
