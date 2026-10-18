"""Bounded worker pool + per-device locks (serialises backup/restore on one device).

Locks are in-process. If you run several API/worker processes, add a DB/Redis lock
(see README "Scaling out").
"""
import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from app.config import settings

log = logging.getLogger("autonetops.worker")
_pool = ThreadPoolExecutor(max_workers=settings.max_concurrent_jobs, thread_name_prefix="anops-job")
_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception:  # a crashing job must never take the pool down
        log.exception("Job crashed: %s%s", getattr(fn, "__name__", fn), args)


def submit(fn, *args) -> None:
    if settings.run_jobs_inline:
        _safe(fn, *args)
    else:
        _pool.submit(_safe, fn, *args)


@contextmanager
def device_lock(device_id: int, timeout: float | None = None):
    with _locks_guard:
        lock = _locks[device_id]
    if not lock.acquire(timeout=settings.device_lock_timeout if timeout is None else timeout):
        raise TimeoutError(f"Device {device_id} is busy with another operation")
    try:
        yield
    finally:
        lock.release()
