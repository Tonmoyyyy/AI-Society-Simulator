import random
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.citizen import Citizen
from app.repositories import citizen_repo
from app.simulation.jobs import JOB_NAMES
from app.simulation.name_generator import generate_name
from app.simulation.personality import generate_personality

# New citizens are employed 75% of the time (a random job from the
# catalog), unemployed the rest — a real city isn't 100% employed, and an
# all-unemployed starting population made the economy/social features feel
# dead until someone manually assigned jobs (see discussion that led to
# this fix).
_EMPLOYMENT_RATE = 0.75


class CitizenError(Exception):
    """Raised for citizen business-rule failures the API layer maps to HTTP."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CitizenNotFound(CitizenError):
    pass


class CitizenLimitReached(CitizenError):
    pass


def _assign_starting_job() -> str:
    if random.random() < _EMPLOYMENT_RATE:
        return random.choice(JOB_NAMES)
    return "unemployed"


def create_citizen(db: Session, name: Optional[str], age: Optional[int]) -> Citizen:
    current_count = citizen_repo.count(db)
    if current_count >= settings.MAX_CITIZENS_V0:
        raise CitizenLimitReached(
            f"Citizen limit reached ({settings.MAX_CITIZENS_V0} for v0.1) — cannot create more."
        )

    resolved_name = name or generate_name()
    resolved_age = age if age is not None else random.randint(18, 70)
    personality = generate_personality()
    job = _assign_starting_job()

    return citizen_repo.create(
        db,
        name=resolved_name,
        age=resolved_age,
        personality_json=personality,
        job=job,
    )


def get_citizen(db: Session, citizen_id: int) -> Citizen:
    citizen = citizen_repo.get_by_id(db, citizen_id)
    if citizen is None:
        raise CitizenNotFound(f"Citizen {citizen_id} not found")
    return citizen


def list_citizens(db: Session, page: int, page_size: int) -> tuple[list[Citizen], int]:
    offset = (page - 1) * page_size
    return citizen_repo.list_paginated(db, offset=offset, limit=page_size)


def update_citizen(
    db: Session,
    citizen_id: int,
    name: Optional[str],
    job: Optional[str],
    current_activity: Optional[str],
) -> Citizen:
    citizen = get_citizen(db, citizen_id)
    return citizen_repo.update(
        db, citizen, name=name, job=job, current_activity=current_activity
    )


def delete_citizen(db: Session, citizen_id: int) -> None:
    citizen = get_citizen(db, citizen_id)
    citizen_repo.delete(db, citizen)
