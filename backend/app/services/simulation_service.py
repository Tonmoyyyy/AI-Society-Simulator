from sqlalchemy.orm import Session

from app.repositories import memory_repo, simulation_tick_repo
from app.simulation import engine


def trigger_tick(db: Session) -> dict:
    return engine.run_tick(db)


def get_recent_ticks(db: Session, limit: int = 20):
    return simulation_tick_repo.list_recent(db, limit=limit)


def get_citizen_memories(db: Session, citizen_id: int, limit: int = 20):
    return memory_repo.list_for_citizen(db, citizen_id, limit=limit)
