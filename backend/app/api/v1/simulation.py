from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.simulation import TickResult, TickOut, SchedulerStatus
from app.services import simulation_service
from app.tasks import tick_scheduler

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"])


@router.post("/tick", response_model=TickResult)
def trigger_tick(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually runs one simulation tick — useful for testing/demoing without
    waiting for the scheduler interval."""
    return simulation_service.trigger_tick(db)


@router.get("/ticks", response_model=list[TickOut])
def list_ticks(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public — tick history is simulation observability, not sensitive data."""
    return simulation_service.get_recent_ticks(db, limit=limit)


@router.post("/scheduler/start", response_model=SchedulerStatus)
def start_scheduler(current_user: User = Depends(get_current_user)):
    tick_scheduler.start_scheduler()
    return {"running": tick_scheduler.is_running()}


@router.post("/scheduler/stop", response_model=SchedulerStatus)
def stop_scheduler(current_user: User = Depends(get_current_user)):
    tick_scheduler.stop_scheduler()
    return {"running": tick_scheduler.is_running()}


@router.get("/scheduler/status", response_model=SchedulerStatus)
def scheduler_status():
    return {"running": tick_scheduler.is_running()}
