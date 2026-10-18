# AutoNetOps

Automated network configuration & backup for Cisco IOS / IOS-XE: SSH backups (manual + scheduled),
versioned history with SHA-256 integrity, diff & change detection, controlled restore with a
pre-restore backup and verification, RBAC, audit log, notifications, retention, dashboard.

**User guide: [USER_GUIDE.md](USER_GUIDE.md)** · Full design: [AutoNetOps_Full_Project_Plan.md](AutoNetOps_Full_Project_Plan.md).

## Quick start (Windows, no lab needed — mock devices)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
cd ..\frontend; npm install; npm run build; cd ..
# .env already has DRIVER_MODE=mock and a generated ADMIN_PASSWORD (see .env)
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Open <http://localhost:8000>, sign in as `admin` with the `ADMIN_PASSWORD` from `.env`.
In mock mode, add any device (e.g. `192.0.2.10`, any username/password), press **Backup running**,
then **Simulate change (mock)** and back up again to see change detection and diff.

Frontend dev server with hot reload: `cd frontend; npm run dev` (proxies `/api` to port 8000).

## Running the app

### Prerequisites
Python 3.12+ (tested on 3.14), Node.js 20+ (only to build the dashboard), Git optional. Docker is only needed for the production setup.

### First-time setup (once)
```powershell
cd "E:\my tools\AutoNetOps\backend"
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
cd ..\frontend
npm install
npm run build        # creates frontend/dist, which the API serves
```
Copy `.env.example` to `.env` and edit it (the existing `.env` is a mock-mode demo config). The first start creates the database, the encryption/JWT keys in `secrets/`, and the admin user from `ADMIN_USERNAME` / `ADMIN_PASSWORD`. If `ADMIN_PASSWORD` is empty, create one with `cd backend; .\.venv\Scripts\python -m app.cli create-admin`.

### Start (everything in one process)
```powershell
cd "E:\my tools\AutoNetOps\backend"
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```
- Dashboard: <http://localhost:8000> — API docs: <http://localhost:8000/docs> — health: <http://localhost:8000/api/v1/health>
- Stop with `Ctrl+C`. Jobs that were running when the process stopped are marked `FAILED` (backups) or `UNCERTAIN` (restores) on the next start; pending jobs are re-queued.
- Run **one** process only (scheduler and device locks are in-process). To reach it from other machines use `--host 0.0.0.0` behind an HTTPS reverse proxy; never expose it plain over a network.

### Development mode (hot reload)
Two terminals:
```powershell
# 1) API with auto-reload
cd "E:\my tools\AutoNetOps\backend"
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload
# 2) Dashboard with hot reload (proxies /api to :8000)
cd "E:\my tools\AutoNetOps\frontend"
npm run dev          # http://localhost:5173
```
After changing the frontend, run `npm run build` again if you use the single-process mode.

### Switching modes
| Goal | `.env` setting |
|---|---|
| Demo without any device | `DRIVER_MODE=mock`, `SSH_STRICT_HOST_KEY=false` |
| Real Cisco devices | `DRIVER_MODE=cisco`, `SSH_STRICT_HOST_KEY=true` + `secrets/known_hosts` |
| Production database | `DATABASE_URL=postgresql+psycopg://…` and `alembic upgrade head` (run in `backend/`) |

Restart the app after editing `.env`.

### Database migrations
SQLite dev databases are created automatically. For PostgreSQL (or after model changes):
```powershell
cd backend
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m alembic revision --autogenerate -m "describe change"   # when you change models
```

### Reset the demo
Stop the app, then delete `autonetops.db` and the contents of `backup_storage/`. Keep `secrets/` unless you delete the database too: the keys encrypt the stored credentials and backups.

### Docker (production)
`docker compose up -d --build` (see "Docker / production" below), then open <http://localhost:8000>. Logs: `docker compose logs -f app`. Stop: `docker compose down` (volumes are kept).

### Common start-up problems
| Problem | Fix |
|---|---|
| `No users exist and ADMIN_PASSWORD is unset` in the log | Set `ADMIN_PASSWORD` (≥10 chars) in `.env`, or run `python -m app.cli create-admin` |
| Blank page / 404 at `/` | `frontend/dist` missing — run `npm run build` |
| `Address already in use` | Another process uses port 8000 — stop it or pass `--port 8001` |
| `ModuleNotFoundError: app` | Start uvicorn from the `backend` folder (or use `--app-dir backend`) |
| `Cannot decrypt value` | `secrets/` or `ENCRYPTION_KEY` changed after devices were added — restore the old key or re-add the devices |
| Login says "Invalid credentials" | Wrong password or account locked for 15 min after 5 failures |

## Using real Cisco devices

1. In `.env` set `DRIVER_MODE=cisco`. Use **only devices you are authorised to administer** — start with an EVE-NG/GNS3 lab.
2. On the device: management IP, `ip ssh version 2`, a user with the least privilege that can run `show running-config`
   (restore additionally needs configuration rights).
3. Host keys are verified (`SSH_STRICT_HOST_KEY=true`). Add each device key first:
   `ssh-keyscan -p 22 <device-ip> >> secrets/known_hosts` and compare the fingerprint out-of-band.
   For a throw-away lab only, you may set `SSH_STRICT_HOST_KEY=false`.
4. Add the device in the UI → **Test connection** (reports reachability, SSH auth, privilege, platform separately) → backup.

## Tests

```powershell
backend\.venv\Scripts\python -m pytest
```

34 tests cover auth/RBAC/lockout, credential encryption, backups (changed/unchanged/failed/timeout/auth/invalid output),
integrity, path traversal, diff, restore (success, merge, abort, connection loss, approval, warnings, blocked commands),
schedules, retention, reports. They use the in-memory mock driver — **they do not prove behaviour on real Cisco
hardware** (see Limitations).

## Docker / production

```bash
cp .env.example .env   # set POSTGRES_PASSWORD, SECRET_KEY, ENCRYPTION_KEY, ADMIN_PASSWORD, DRIVER_MODE=cisco
docker compose up -d --build
```

Put a TLS reverse proxy (nginx/Caddy) in front: the app binds to `127.0.0.1:8000`. PostgreSQL is not published.
Back up the `pgdata` and `appdata` volumes **and keep `ENCRYPTION_KEY` separately** — without it credentials and
backup files cannot be decrypted. Test restoring AutoNetOps itself.

## Architecture (as built)

| Plan item | Implementation |
|---|---|
| API | FastAPI, `/api/v1`, JWT bearer, RBAC (`viewer < operator < admin`) enforced on the backend |
| Cisco automation | Netmiko driver (`backend/app/network/cisco_ios.py`); all CLI strings in `commands.py`; mock driver for demos/tests |
| Jobs | Bounded thread pool + per-device locks (`workers/executor.py`); API returns job IDs (202) |
| Scheduler | APScheduler (hourly / every N hours / daily / weekly / monthly / cron, per-schedule IANA timezone), duplicate-run guard |
| DB | SQLAlchemy 2 + Alembic; SQLite (dev) or PostgreSQL |
| Storage | Fernet-encrypted `.cfg.enc` files under `backup_storage/<id>_<name>/YYYY/MM/`; paths built from internal IDs |
| Diff | `difflib`, normalised view hides volatile lines, heuristic categories (interfaces, VLANs, routing, ACL, NAT…) |
| Frontend | React + Vite; served by FastAPI from `frontend/dist` |

Redis/Celery from the plan are **not** used: the plan itself says to start with APScheduler and add Celery when
volume demands it.

## Safety design (restore)

Validate (checksum, same device, running-config only, completeness, blocked commands such as `reload`/`write erase`,
management-IP warning) → **protected pre-restore backup** (abort if it fails) → apply → re-collect and verify →
`SUCCESS` / `NEEDS_REVIEW` / `FAILED` / `UNCERTAIN`. Connection loss never counts as success. Roll-back is an explicit
admin action that restores the pre-restore version. Optional second-person approval (`RESTORE_REQUIRES_APPROVAL=true`).

## Known limitations (read before production)

* **Restore on real Cisco gear is unvalidated.** *Merge* mode replays lines and cannot delete lines that exist only on
  the device (verification reports them as `NEEDS_REVIEW`). *Replace* mode uses SCP + `configure replace` and needs
  `ip scp server enable` and a platform that supports it. Validate both on your exact IOS/IOS-XE release in a lab first.
* Roll-back in *merge* mode has the same limitation; prefer *replace* where supported.
* Change detection happens when a backup runs — it is not real-time.
* Per-device locks and the scheduler are in-process: run **one** API process (`--workers 1`). To scale out, move locks
  to the database/Redis and run the scheduler separately.
* JWTs are stateless: logout discards the token client-side (tokens expire after `ACCESS_TOKEN_MINUTES`).
  The token is kept in `sessionStorage`; serve the app over HTTPS and keep dependencies updated.
* Device discovery (plan §5.4), selective restore, NX-OS/ASA and MFA are not implemented.
* Audit logs are append-only through the API; for tamper resistance also restrict `UPDATE/DELETE` on `audit_logs`
  at the database level.
