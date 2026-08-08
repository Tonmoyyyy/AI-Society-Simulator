from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.simulation_tick import SimulationTick


def next_tick_number(db: Session) -> int:
    current_max = db.scalar(select(func.max(SimulationTick.tick_number)))
    return (current_max or 0) + 1


def start_tick(db: Session) -> SimulationTick:
    tick = SimulationTick(tick_number=next_tick_number(db), status="running", citizens_processed=0)
    db.add(tick)
    db.commit()
    db.refresh(tick)
    return tick


def finish_tick(db: Session, tick: SimulationTick, citizens_processed: int, status: str) -> SimulationTick:
    from datetime import datetime, timezone

    tick.citizens_processed = citizens_processed
    tick.status = status
    tick.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tick)
    return tick


def list_recent(db: Session, limit: int = 20) -> list[SimulationTick]:
    return (
        db.query(SimulationTick)
        .order_by(SimulationTick.tick_number.desc())
        .limit(limit)
        .all()
    )


def get_by_tick_number(db: Session, tick_number: int) -> Optional[SimulationTick]:
    return db.query(SimulationTick).filter(SimulationTick.tick_number == tick_number).first()
