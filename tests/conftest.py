import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="anops-test-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{Path(_tmp, 'test.db').as_posix()}",
    "DRIVER_MODE": "mock",
    "RUN_JOBS_INLINE": "true",
    "SCHEDULER_ENABLED": "false",
    "BACKUP_DIR": str(Path(_tmp, "backups")),
    "SECRETS_DIR": str(Path(_tmp, "secrets")),
    "RETRY_BACKOFF_SECONDS": "0",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "Admin-Test-Pass-1",
    "MAX_FAILED_LOGINS": "3",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.network import mock_driver  # noqa: E402

ADMIN = ("admin", "Admin-Test-Pass-1")


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    mock_driver.reset()
    with TestClient(app) as c:  # lifespan creates tables + bootstrap admin
        yield c


def login(client, username, password) -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def admin(client):
    return login(client, *ADMIN)


def make_user(client, admin, username, role):
    r = client.post("/api/v1/users", headers=admin,
                    json={"username": username, "password": "Long-Enough-Pass-1", "role": role})
    assert r.status_code == 201, r.text
    return login(client, username, "Long-Enough-Pass-1")


@pytest.fixture()
def device(client, admin):
    r = client.post("/api/v1/devices", headers=admin, json={
        "name": "CORE-R1", "ip_address": "192.0.2.10", "platform": "cisco_xe",
        "username": "netops", "password": "lab-password", "enable_secret": "lab-enable"})
    assert r.status_code == 201, r.text
    return r.json()
