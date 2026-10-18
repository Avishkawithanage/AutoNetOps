# Running AutoNetOps

## Prerequisites
Python 3.12+ (tested on 3.14), Node.js 20+ (only to build the dashboard), Git optional. Docker is only needed for the production setup.

## First-time setup (once)
```powershell
cd "E:\my tools\AutoNetOps\backend"
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
cd ..\frontend
npm install
npm run build        # creates frontend/dist, which the API serves
```
Copy `.env.example` to `.env` and edit it (the existing `.env` is a mock-mode demo config). The first start creates the database, the encryption/JWT keys in `secrets/`, and the admin user from `ADMIN_USERNAME` / `ADMIN_PASSWORD`. If `ADMIN_PASSWORD` is empty, create one with `cd backend; .\.venv\Scripts\python -m app.cli create-admin`.

## Start (everything in one process)
```powershell
cd "E:\my tools\AutoNetOps\backend"
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```
- Dashboard: <http://localhost:8000> — API docs: <http://localhost:8000/docs> — health: <http://localhost:8000/api/v1/health>
- Stop with `Ctrl+C`. Jobs that were running when the process stopped are marked `FAILED` (backups) or `UNCERTAIN` (restores) on the next start; pending jobs are re-queued.
- Run **one** process only (scheduler and device locks are in-process). To reach it from other machines use `--host 0.0.0.0` behind an HTTPS reverse proxy; never expose it plain over a network.

## Development mode (hot reload)
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

## Switching modes
| Goal | `.env` setting |
|---|---|
| Demo without any device | `DRIVER_MODE=mock`, `SSH_STRICT_HOST_KEY=false` |
| Real Cisco devices | `DRIVER_MODE=cisco`, `SSH_STRICT_HOST_KEY=true` + `secrets/known_hosts` |
| Production database | `DATABASE_URL=postgresql+psycopg://…` and `alembic upgrade head` (run in `backend/`) |

Restart the app after editing `.env`.

## Database migrations
SQLite dev databases are created automatically. For PostgreSQL (or after model changes):
```powershell
cd backend
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m alembic revision --autogenerate -m "describe change"   # when you change models
```

## Reset the demo
Stop the app, then delete `autonetops.db` and the contents of `backup_storage/`. Keep `secrets/` unless you delete the database too: the keys encrypt the stored credentials and backups.

## Docker (production)
`docker compose up -d --build` (see the README), then open <http://localhost:8000>. Logs: `docker compose logs -f app`. Stop: `docker compose down` (volumes are kept).

## Common start-up problems
| Problem | Fix |
|---|---|
| `No users exist and ADMIN_PASSWORD is unset` in the log | Set `ADMIN_PASSWORD` (≥10 chars) in `.env`, or run `python -m app.cli create-admin` |
| Blank page / 404 at `/` | `frontend/dist` missing — run `npm run build` |
| `Address already in use` | Another process uses port 8000 — stop it or pass `--port 8001` |
| `ModuleNotFoundError: app` | Start uvicorn from the `backend` folder (or use `--app-dir backend`) |
| `Cannot decrypt value` | `secrets/` or `ENCRYPTION_KEY` changed after devices were added — restore the old key or re-add the devices |
| Login says "Invalid credentials" | Wrong password or account locked for 15 min after 5 failures |
