from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.citizen import Citizen


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Citizen)) or 0


def get_by_id(db: Session, citizen_id: int) -> Optional[Citizen]:
    return db.get(Citizen, citizen_id)


def list_all(db: Session) -> list[Citizen]:
    """Unpaginated — used by the tick engine to process every citizen each tick.
    Safe at v0.1 scale (capped at MAX_CITIZENS_V0=100)."""
    return db.query(Citizen).all()


def list_paginated(db: Session, offset: int, limit: int) -> tuple[list[Citizen], int]:
    total = count(db)
    items = (
        db.query(Citizen)
        .order_by(Citizen.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items, total


def create(
    db: Session,
    name: str,
    age: int,
    personality_json: dict,
    job: str = "unemployed",
) -> Citizen:
    citizen = Citizen(
        name=name,
        age=age,
        personality_json=personality_json,
        job=job,
        # mood/happiness/energy/health/current_activity use model defaults
    )
    db.add(citizen)
    db.commit()
    db.refresh(citizen)
    return citizen


def update(db: Session, citizen: Citizen, **fields) -> Citizen:
    for key, value in fields.items():
        if value is not None:
            setattr(citizen, key, value)
    db.commit()
    db.refresh(citizen)
    return citizen


def delete(db: Session, citizen: Citizen) -> None:
    db.delete(citizen)
    db.commit()
