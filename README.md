# AutoNetOps

**Automated network configuration & backup for Cisco IOS / IOS-XE.**
Back up device configurations over SSH, keep a verified version history, see what changed, and restore safely.

![Python](https://img.shields.io/badge/python-3.12%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-009688) ![React](https://img.shields.io/badge/React-18-61dafb) ![tests](https://img.shields.io/badge/tests-34%20passing-brightgreen)

## Features

- **Backups** — manual and scheduled (hourly / daily / weekly / monthly / cron, per-timezone), running + startup config
- **Versioning** — SHA-256 integrity, duplicate detection, encrypted-at-rest storage, retention policy
- **Diff & change detection** — line diff, volatile-line filtering, change categories, notifications
- **Safe restore** — validation, protected pre-restore backup, verification, optional second-person approval, rollback
- **Security** — JWT auth, roles (viewer / operator / admin), login lockout, encrypted credentials, audit log
- **Dashboard** — React UI for devices, history, compare, schedules, jobs, restores, reports
- **Mock mode** — try everything without any network device

## Quick start (mock devices, no lab needed)

**Windows, one step:** double-click **`run.bat`**. On first run it creates the Python environment, installs dependencies,
builds the dashboard, creates a demo `.env` (with a generated admin password shown in the console) and opens the app at
<http://localhost:8000>. Later runs just start the server. Needs Python 3.12+ and Node.js 20+.

**Manual setup:**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
cd ..\frontend; npm install; npm run build; cd ..

copy .env.example .env      # then set ADMIN_PASSWORD (min 10 chars) and DRIVER_MODE=mock
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Open <http://localhost:8000>, sign in as `admin`, add a device (any IP/credentials in mock mode), run a backup,
use **Simulate change (mock)**, back up again and compare the versions.

## Documentation

| Document | Content |
|---|---|
| [How it works](docs/HOW_IT_WORKS.md) | Plain-language explanation of the system, backup and restore flow |
| [User guide](docs/USER_GUIDE.md) | Using the dashboard: devices, backups, diff, schedules, restore, users |
| [Running the app](docs/RUNNING.md) | Setup, dev mode, migrations, modes, Docker, troubleshooting |
| [Project plan](docs/PROJECT_PLAN.md) | Original design and roadmap |

## Real Cisco devices

1. Set `DRIVER_MODE=cisco` in `.env`. Use **only devices you are authorised to administer** — start in an EVE-NG / GNS3 lab.
2. Enable SSH v2 on the device and create a least-privilege account.
3. Add the device host key (strict checking is on by default):
   `ssh-keyscan -p 22 <device-ip> >> secrets/known_hosts` — verify the fingerprint out-of-band.
4. Add the device in the UI → **Test connection** → **Backup**.

## Architecture

| Area | Implementation |
|---|---|
| API | FastAPI `/api/v1`, JWT, RBAC enforced server-side |
| Devices | Netmiko driver (`backend/app/network/`), mock driver for demos/tests |
| Jobs | Bounded thread pool, per-device locks, retries with back-off |
| Scheduler | APScheduler with duplicate-run guard |
| Database | SQLAlchemy 2 + Alembic, SQLite (dev) or PostgreSQL |
| Storage | Fernet-encrypted files in `backup_storage/` |
| Frontend | React + Vite, served by FastAPI from `frontend/dist` |

```
backend/    FastAPI app, services, network drivers, migrations
frontend/   React dashboard
tests/      pytest suite (mock driver)
docs/       user guide, run guide, project plan
```

## Testing

```powershell
backend\.venv\Scripts\python -m pytest
```

The 34 tests use the mock driver. They do **not** prove behaviour on real Cisco hardware.

## Docker

```bash
cp .env.example .env   # set POSTGRES_PASSWORD, SECRET_KEY, ENCRYPTION_KEY, ADMIN_PASSWORD, DRIVER_MODE=cisco
docker compose up -d --build
```

Binds to `127.0.0.1:8000`; put an HTTPS reverse proxy in front. Back up the volumes and keep `ENCRYPTION_KEY`
separately — without it credentials and backups cannot be decrypted.

## Limitations

- **Restore is not validated on real Cisco gear.** Merge mode cannot delete device-only lines; replace mode needs SCP and
  `configure replace`. Test in a lab on your exact IOS/IOS-XE release first.
- Change detection happens when a backup runs, not in real time.
- Run a single process (`--workers 1`): scheduler and device locks are in-process.
- Not implemented: device discovery, selective restore, MFA, NX-OS / ASA.
- Restrict `UPDATE/DELETE` on `audit_logs` at database level for tamper resistance.

## Security

Never commit `.env`, `secrets/`, databases or `backup_storage/` (already in `.gitignore`).
Report vulnerabilities privately to the repository owner rather than in a public issue.
