import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.api import auth, configurations, devices, jobs, reports, schedules
from app.config import BASE_DIR, settings
from app.db.session import Base, SessionLocal, engine
from app.models import User
from app.security.auth import hash_password
from app.services import scheduler_service
from app.workers.recovery import recover_stale_jobs

log = logging.getLogger("autonetops")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def bootstrap_admin() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(func.count()).select_from(User)) == 0:
            if not settings.admin_password:
                log.warning("No users exist and ADMIN_PASSWORD is unset. Run: python -m app.cli create-admin")
                return
            db.add(User(username=settings.admin_username, role="admin",
                        password_hash=hash_password(settings.admin_password)))
            db.commit()
            log.info("Bootstrap admin '%s' created", settings.admin_username)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        Base.metadata.create_all(engine)
    bootstrap_admin()
    log.info("Recovered stale jobs: %s", recover_stale_jobs())
    if settings.scheduler_enabled:
        scheduler_service.start()
    yield
    scheduler_service.stop()


app = FastAPI(title="AutoNetOps", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error")  # details stay in server logs, never in the response
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Cache-Control", "no-store" if request.url.path.startswith("/api") else "no-cache")
    return resp


for r in (auth.router, devices.router, configurations.router, jobs.router, schedules.router, reports.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "driver_mode": settings.driver_mode}


# Serve the built React app (if present) so one process runs everything
_dist = BASE_DIR / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (_dist / path).resolve()
        if path and _dist.resolve() in f.parents and f.is_file():
            return FileResponse(f)
        return FileResponse(_dist / "index.html")
