"""
APScheduler-driven background tick loop (see SDD — Celery/Redis explicitly
deferred for v0.1; a single in-process scheduler is enough at this scale).

The scheduler is NOT started automatically on app startup — it's opt-in via
POST /api/v1/simulation/scheduler/start. This keeps `pytest` and one-off API
usage from silently running background ticks against the real database.
"""

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.db.session import SessionLocal
from app.simulation import engine

_scheduler: BackgroundScheduler | None = None


def _tick_job() -> None:
    db = SessionLocal()
    try:
        engine.run_tick(db)
    finally:
        db.close()


def start_scheduler() -> bool:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return False  # already running, no-op

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _tick_job,
        "interval",
        seconds=settings.TICK_INTERVAL_SECONDS,
        id="simulation_tick",
        replace_existing=True,
    )
    _scheduler.start()
    return True


def stop_scheduler() -> bool:
    global _scheduler
    if _scheduler is None:
        return False
    _scheduler.shutdown(wait=False)
    _scheduler = None
    return True


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running
