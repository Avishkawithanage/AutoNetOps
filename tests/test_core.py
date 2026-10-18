"""End-to-end tests against the API using the mock Cisco driver."""
import pytest
from sqlalchemy import select

from conftest import login, make_user

from app.db.session import SessionLocal
from app.models import AuditLog, Configuration, Credential
from app.network import mock_driver
from app.services import diff_service, storage

API = "/api/v1"


def backup(client, hdr, dev, types=("running",)):
    r = client.post(f"{API}/devices/{dev['id']}/backup", headers=hdr, json={"config_types": list(types)})
    assert r.status_code == 202, r.text
    return r.json()


# ---------- auth / RBAC ----------
def test_unauthenticated_rejected(client):
    assert client.get(f"{API}/devices").status_code == 401
    assert client.get(f"{API}/audit-logs").status_code == 401


def test_login_failure_lockout_and_audit(client):
    for _ in range(3):
        assert client.post(f"{API}/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    # now locked: even the right password is refused, with the same generic error
    r = client.post(f"{API}/auth/login", json={"username": "admin", "password": "Admin-Test-Pass-1"})
    assert r.status_code == 401 and r.json()["detail"] == "Invalid credentials"
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "login", AuditLog.result == "FAILED"))


def test_rbac_matrix(client, admin, device):
    viewer = make_user(client, admin, "vera", "viewer")
    operator = make_user(client, admin, "oscar", "operator")
    assert client.get(f"{API}/devices", headers=viewer).status_code == 200
    assert client.post(f"{API}/devices/{device['id']}/backup", headers=viewer).status_code == 403
    assert client.post(f"{API}/devices", headers=operator, json={}).status_code == 403
    assert client.get(f"{API}/users", headers=operator).status_code == 403
    assert client.get(f"{API}/audit-logs", headers=viewer).status_code == 403
    assert client.post(f"{API}/devices/{device['id']}/backup", headers=operator).status_code == 202


def test_credentials_encrypted_and_never_returned(client, device):
    assert "password" not in device and "username" not in device
    with SessionLocal() as db:
        c = db.scalar(select(Credential))
        assert "lab-password" not in c.password_enc and "netops" not in c.username_enc


def test_device_validation(client, admin):
    base = {"name": "R2", "ip_address": "192.0.2.11", "username": "u", "password": "p"}
    assert client.post(f"{API}/devices", headers=admin, json={**base, "ip_address": "999.1.1.1"}).status_code == 422
    assert client.post(f"{API}/devices", headers=admin, json={**base, "name": "../etc"}).status_code == 422
    assert client.post(f"{API}/devices", headers=admin, json={**base, "ssh_port": 0}).status_code == 422
    assert client.post(f"{API}/devices", headers=admin, json={**base, "platform": "juniper"}).status_code == 422


# ---------- connection test ----------
def test_connection_test_stages(client, admin, device):
    r = client.post(f"{API}/devices/{device['id']}/test-connection", headers=admin).json()
    assert r["reachable"] and r["ssh_auth"] and r["privileged"]
    mock_driver.FAILURES["CORE-R1"] = "auth"
    r = client.post(f"{API}/devices/{device['id']}/test-connection", headers=admin).json()
    assert r["reachable"] and not r["ssh_auth"] and "AUTH_FAILED" in r["error"]


# ---------- backup / versioning ----------
def test_backup_versioning_and_duplicate_detection(client, admin, device):
    j = backup(client, admin, device)[0]
    assert j["status"] == "SUCCESS" and j["change_status"] == "NOT_COMPARABLE"
    # volatile header lines change on every collection; must NOT create a new version
    mock_driver.STORE["CORE-R1"]["running"] = mock_driver.STORE["CORE-R1"]["running"].replace(
        "! Last configuration change at", "! Last configuration change at 99:99 ")
    j2 = backup(client, admin, device)[0]
    assert j2["status"] == "SUCCESS" and j2["change_status"] == "UNCHANGED"
    assert j2["configuration_id"] == j["configuration_id"]
    # real change -> new version
    mock_driver.mutate(_target(), "snmp-server community lab RO")
    j3 = backup(client, admin, device)[0]
    assert j3["change_status"] == "CHANGED"
    versions = client.get(f"{API}/devices/{device['id']}/backups", headers=admin).json()
    assert sorted(v["version_number"] for v in versions) == [1, 2]


def _target():
    from app.network.base_driver import DeviceTarget
    return DeviceTarget(name="CORE-R1", ip_address="192.0.2.10")


def test_startup_and_running_are_separate(client, admin, device):
    jobs = backup(client, admin, device, ("running", "startup"))
    assert {j["config_type"] for j in jobs} == {"running", "startup"}
    assert all(j["status"] == "SUCCESS" for j in jobs)


@pytest.mark.parametrize("failure,status,code", [
    ("timeout", "TIMEOUT", "TIMEOUT"), ("auth", "FAILED", "AUTH_FAILED"),
    ("unreachable", "FAILED", "UNREACHABLE"), ("bad_output", "FAILED", "INVALID_OUTPUT"),
])
def test_backup_failures_recorded_without_version(client, admin, device, failure, status, code):
    mock_driver.FAILURES["CORE-R1"] = failure
    j = backup(client, admin, device)[0]
    assert (j["status"], j["error_code"]) == (status, code)
    if failure in ("timeout", "unreachable"):
        assert j["retry_count"] == 2  # transient: bounded retries
    if failure == "auth":
        assert j["retry_count"] == 0  # auth failures are never retried
    assert client.get(f"{API}/devices/{device['id']}/backups", headers=admin).json() == []
    notes = client.get(f"{API}/notifications", headers=admin).json()
    assert any(n["event"] == "backup_failed" for n in notes)


def test_failure_of_one_device_does_not_block_another(client, admin, device):
    r = client.post(f"{API}/devices", headers=admin, json={
        "name": "SW-01", "ip_address": "192.0.2.20", "username": "u", "password": "p"})
    other = r.json()
    mock_driver.FAILURES["CORE-R1"] = "timeout"
    assert backup(client, admin, device)[0]["status"] == "TIMEOUT"
    assert backup(client, admin, other)[0]["status"] == "SUCCESS"


def test_disabled_device_not_backed_up(client, admin, device):
    client.put(f"{API}/devices/{device['id']}", headers=admin, json={"is_enabled": False})
    assert client.post(f"{API}/devices/{device['id']}/backup", headers=admin).status_code == 409


# ---------- integrity ----------
def _corrupt(cfg_id):
    with SessionLocal() as db:
        cfg = db.get(Configuration, cfg_id)
        p = storage._resolve(cfg.storage_key)
        from app.security.crypto import encrypt_bytes
        p.write_bytes(encrypt_bytes(b"tampered\nconfig\nhostname evil\nx\nend\n"))


def test_integrity_check_blocks_read_and_restore(client, admin, device):
    cid = backup(client, admin, device)[0]["configuration_id"]
    assert client.get(f"{API}/configurations/{cid}/integrity", headers=admin).json()["ok"] is True
    _corrupt(cid)
    assert client.get(f"{API}/configurations/{cid}/integrity", headers=admin).json()["ok"] is False
    assert client.get(f"{API}/configurations/{cid}/content", headers=admin).status_code == 409
    r = client.post(f"{API}/configurations/{cid}/restore", headers=admin, json={"confirm": True})
    assert r.status_code == 422 and "Integrity" in str(r.json())
    notes = client.get(f"{API}/notifications", headers=admin).json()
    assert any(n["event"] == "integrity_failure" for n in notes)


def test_storage_blocks_path_traversal(client):
    with pytest.raises(ValueError):
        storage._resolve("../../etc/passwd")


def test_backup_files_encrypted_at_rest(client, admin, device):
    cid = backup(client, admin, device)[0]["configuration_id"]
    with SessionLocal() as db:
        raw = storage._resolve(db.get(Configuration, cid).storage_key).read_bytes()
    assert b"hostname" not in raw


# ---------- diff ----------
def test_diff_lines_and_categories():
    a = "hostname R1\ninterface Gi0/0\n ip address 192.0.2.1 255.255.255.0\n no shutdown\nend\n"
    b = "hostname R1\ninterface Gi0/0\n ip address 192.0.2.10 255.255.255.0\n no shutdown\nend\n"
    d = diff_service.compute_diff(a, b)
    assert (d["added"], d["removed"]) == (1, 1)
    assert d["categories"] == {"Interfaces": 2}
    assert "-" in d["unified"] and "+" in d["unified"]
    assert diff_service.compute_diff(a, a)["identical"]


def test_compare_api_and_cross_device_rejected(client, admin, device):
    c1 = backup(client, admin, device)[0]["configuration_id"]
    mock_driver.mutate(_target(), "ntp server 192.0.2.99")
    c2 = backup(client, admin, device)[0]["configuration_id"]
    d = client.get(f"{API}/compare?source_id={c1}&target_id={c2}", headers=admin).json()
    assert d["added"] == 1 and d["removed"] == 0 and d["categories"] == {"NTP": 1}
    other = client.post(f"{API}/devices", headers=admin, json={
        "name": "SW-01", "ip_address": "192.0.2.20", "username": "u", "password": "p"}).json()
    c3 = backup(client, admin, other)[0]["configuration_id"]
    assert client.get(f"{API}/compare?source_id={c1}&target_id={c3}", headers=admin).status_code == 422


# ---------- restore ----------
def _two_versions(client, admin, device):
    v1 = backup(client, admin, device)[0]["configuration_id"]
    mock_driver.mutate(_target(), "snmp-server community lab RO")
    v2 = backup(client, admin, device)[0]["configuration_id"]
    return v1, v2


def test_restore_requires_confirmation_and_admin(client, admin, device):
    v1, _ = _two_versions(client, admin, device)
    operator = make_user(client, admin, "oscar", "operator")
    assert client.post(f"{API}/configurations/{v1}/restore", headers=operator, json={"confirm": True}).status_code == 403
    assert client.post(f"{API}/configurations/{v1}/restore", headers=admin, json={}).status_code == 422


def test_restore_replace_success_flow(client, admin, device):
    v1, v2 = _two_versions(client, admin, device)
    r = client.post(f"{API}/configurations/{v1}/restore", headers=admin,
                    json={"confirm": True, "mode": "replace", "save_startup": True})
    assert r.status_code == 202, r.text
    job = client.get(f"{API}/restores/{r.json()['id']}", headers=admin).json()
    assert job["status"] == "SUCCESS", job
    assert job["pre_restore_configuration_id"] is not None
    assert job["verification_result"]["missing_count"] == 0
    pre = client.get(f"{API}/configurations/{job['pre_restore_configuration_id']}", headers=admin).json()
    assert pre["is_protected"] is True
    # device really changed back, and startup saved
    assert "snmp-server community" not in mock_driver.STORE["CORE-R1"]["running"]
    assert "snmp-server community" not in mock_driver.STORE["CORE-R1"]["startup"]
    acts = [a["action"] for a in client.get(f"{API}/audit-logs?device_id={device['id']}", headers=admin).json()]
    assert "restore" in acts and "restore_request" in acts


def test_restore_merge_leaves_extra_lines_needs_review_then_recover(client, admin, device):
    v1, v2 = _two_versions(client, admin, device)
    r = client.post(f"{API}/configurations/{v1}/restore", headers=admin, json={"confirm": True, "mode": "merge"})
    job = client.get(f"{API}/restores/{r.json()['id']}", headers=admin).json()
    assert job["status"] == "NEEDS_REVIEW"  # merge cannot delete the extra SNMP line
    assert job["verification_result"]["extra_count"] >= 1
    assert job["recovery_status"] == "ROLLBACK_AVAILABLE"
    rec = client.post(f"{API}/restores/{job['id']}/recover", headers=admin)
    assert rec.status_code == 202 and rec.json()["is_recovery"] is True


def test_restore_aborts_when_pre_restore_backup_fails(client, admin, device):
    v1, _ = _two_versions(client, admin, device)
    mock_driver.FAILURES["CORE-R1"] = "timeout"
    r = client.post(f"{API}/configurations/{v1}/restore", headers=admin, json={"confirm": True, "mode": "replace"})
    job = client.get(f"{API}/restores/{r.json()['id']}", headers=admin).json()
    assert job["status"] == "FAILED" and "nothing was applied" in job["error_message"]


def test_restore_connection_lost_is_not_assumed_successful(client, admin, device):
    v1, _ = _two_versions(client, admin, device)
    mock_driver.FAILURES["CORE-R1"] = "drop_on_apply"
    r = client.post(f"{API}/configurations/{v1}/restore", headers=admin, json={"confirm": True, "mode": "replace"})
    job = client.get(f"{API}/restores/{r.json()['id']}", headers=admin).json()
    assert job["status"] in ("FAILED", "UNCERTAIN", "NEEDS_REVIEW") and job["status"] != "SUCCESS"


def test_restore_warns_when_management_ip_missing(client, admin, device):
    v1 = backup(client, admin, device)[0]["configuration_id"]
    # rewrite the stored version so it lacks the management IP (recompute checksums so integrity passes)
    text = storage.read_config(_key(v1)).replace("192.0.2.10", "198.51.100.5")
    with SessionLocal() as db:
        cfg = db.get(Configuration, v1)
        from app.security.crypto import encrypt_bytes
        storage._resolve(cfg.storage_key).write_bytes(encrypt_bytes(text.encode()))
        cfg.checksum_sha256 = diff_service.sha256_text(text)
        db.commit()
    r = client.post(f"{API}/configurations/{v1}/restore", headers=admin, json={"confirm": True, "mode": "replace"})
    assert r.status_code == 409 and "management IP" in str(r.json())
    r = client.post(f"{API}/configurations/{v1}/restore", headers=admin,
                    json={"confirm": True, "mode": "replace", "acknowledge_risks": True})
    assert r.status_code == 202


def _key(cid):
    with SessionLocal() as db:
        return db.get(Configuration, cid).storage_key


def test_dangerous_commands_blocked(client, admin, device):
    v1 = backup(client, admin, device)[0]["configuration_id"]
    text = storage.read_config(_key(v1)).replace("\nend\n", "\nreload\nend\n")
    with SessionLocal() as db:
        cfg = db.get(Configuration, v1)
        from app.security.crypto import encrypt_bytes
        storage._resolve(cfg.storage_key).write_bytes(encrypt_bytes(text.encode()))
        cfg.checksum_sha256 = diff_service.sha256_text(text)
        db.commit()
    r = client.post(f"{API}/configurations/{v1}/restore", headers=admin, json={"confirm": True})
    assert r.status_code == 422 and "blocked command" in str(r.json())


def test_approval_workflow_needs_second_person(client, admin, device, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "restore_requires_approval", True)
    v1, _ = _two_versions(client, admin, device)
    operator = make_user(client, admin, "oscar", "operator")
    r = client.post(f"{API}/configurations/{v1}/restore", headers=operator, json={"confirm": True, "mode": "replace"})
    assert r.status_code == 202 and r.json()["status"] == "PENDING_APPROVAL"
    rid = r.json()["id"]
    assert "snmp-server community" in mock_driver.STORE["CORE-R1"]["running"]  # nothing applied yet
    assert client.post(f"{API}/restores/{rid}/approve", headers=operator).status_code == 403
    assert client.post(f"{API}/restores/{rid}/approve", headers=admin).status_code == 202
    assert client.get(f"{API}/restores/{rid}", headers=admin).json()["status"] == "SUCCESS"


# ---------- schedules ----------
def test_schedule_validation_and_run(client, admin, device):
    bad = {"name": "bad", "frequency": "weekly", "days_of_week": "funday"}
    assert client.post(f"{API}/schedules", headers=admin, json=bad).status_code == 422
    assert client.post(f"{API}/schedules", headers=admin,
                       json={"name": "tz", "frequency": "daily", "timezone": "Mars/Base"}).status_code == 422
    ok = client.post(f"{API}/schedules", headers=admin, json={
        "name": "Nightly", "frequency": "daily", "time_of_day": "02:00", "timezone": "Asia/Colombo",
        "config_types": "running,startup"})
    assert ok.status_code == 201, ok.text
    sid = ok.json()["id"]
    assert client.post(f"{API}/schedules/{sid}/run", headers=admin).json()["jobs_created"] == 2
    # same minute again -> duplicate execution prevented
    assert client.post(f"{API}/schedules/{sid}/run", headers=admin).json()["jobs_created"] == 0
    jobs = client.get(f"{API}/jobs?schedule_id={sid}", headers=admin).json()
    assert len(jobs) == 2 and all(j["status"] == "SUCCESS" and j["job_type"] == "scheduled" for j in jobs)


def test_disabled_schedule_creates_no_jobs(client, admin, device):
    s = client.post(f"{API}/schedules", headers=admin, json={
        "name": "Off", "frequency": "hourly", "enabled": False}).json()
    assert client.post(f"{API}/schedules/{s['id']}/run", headers=admin).json()["jobs_created"] == 0


def test_trigger_builders():
    from app.models import Schedule
    from app.services.scheduler_service import build_trigger
    for kw in ({"frequency": "hourly"}, {"frequency": "every_n_hours", "interval_hours": 6},
               {"frequency": "weekly", "days_of_week": "mon,thu"}, {"frequency": "monthly", "day_of_month": 15},
               {"frequency": "cron", "cron_expression": "*/15 * * * *"}):
        build_trigger(Schedule(name="x", time_of_day="02:00", timezone="Asia/Colombo", **kw))
    with pytest.raises(ValueError):
        build_trigger(Schedule(name="x", frequency="monthly", day_of_month=31, timezone="UTC", time_of_day="02:00"))


# ---------- retention / reports / misc ----------
def test_retention_keeps_latest_and_protected(client, admin, device):
    ids = []
    for i in range(4):
        ids.append(backup(client, admin, device)[0]["configuration_id"])
        mock_driver.mutate(_target(), f"ntp server 192.0.2.{50 + i}")
    ids.append(backup(client, admin, device)[0]["configuration_id"])
    client.post(f"{API}/configurations/{ids[0]}/protect", headers=admin)
    client.put(f"{API}/settings/retention", headers=admin, json={"max_versions_per_device": 2, "max_age_days": 0})
    dry = client.post(f"{API}/settings/retention/run?dry_run=true", headers=admin).json()
    assert ids[0] not in dry["deleted_configuration_ids"] and ids[-1] not in dry["deleted_configuration_ids"]
    client.post(f"{API}/settings/retention/run?dry_run=false", headers=admin)
    left = {v["id"] for v in client.get(f"{API}/devices/{device['id']}/backups", headers=admin).json()}
    assert ids[0] in left and ids[-1] in left and len(left) == 3


def test_dashboard_reports_and_snapshot(client, admin, device):
    backup(client, admin, device)
    backup(client, admin, device)
    d = client.get(f"{API}/reports/dashboard", headers=admin).json()
    assert d["backups_success_today"] == 2 and d["unchanged_today"] == 1
    assert client.get(f"{API}/reports/daily-backups?format=csv", headers=admin).text.startswith("date,")
    assert client.get(f"{API}/reports/storage", headers=admin).json()["per_device"][0]["versions"] == 1
    snap = client.post(f"{API}/devices/{device['id']}/snapshot", headers=admin)
    assert snap.status_code == 201 and "interfaces" in snap.json()["data"]


def test_cannot_delete_device_with_backups(client, admin, device):
    backup(client, admin, device)
    assert client.delete(f"{API}/devices/{device['id']}", headers=admin).status_code == 409


def test_stale_job_recovery(client, admin, device):
    from app.models import BackupJob, RestoreJob
    from app.workers.recovery import recover_stale_jobs
    with SessionLocal() as db:
        db.add(BackupJob(device_id=device["id"], status="RUNNING"))
        db.commit()
    assert recover_stale_jobs()["failed_backups"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(BackupJob).where(BackupJob.error_code == "WORKER_INTERRUPTED"))
