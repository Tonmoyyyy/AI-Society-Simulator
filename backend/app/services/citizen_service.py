import random
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.citizen import Citizen
from app.repositories import citizen_repo
from app.services import world_generation_service
from app.simulation.jobs import JOB_NAMES
from app.simulation.neighborhoods import NEIGHBORHOOD_NAMES
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


def create_citizen(
    db: Session,
    name: Optional[str],
    age: Optional[int],
    job: Optional[str] = None,
    neighborhood: Optional[str] = None,
    personality_json: Optional[dict] = None,
) -> Citizen:
    """Every field is independently overridable — pass any subset and the
    rest still get randomized. Validation of job/neighborhood/personality
    values already happened at the schema layer (schemas/citizen.py); this
    layer only fills in what wasn't provided."""
    current_count = citizen_repo.count(db)
    if current_count >= settings.MAX_CITIZENS_V0:
        raise CitizenLimitReached(
            f"Citizen limit reached ({settings.MAX_CITIZENS_V0} for v0.1) — cannot create more."
        )

    resolved_name = name or generate_name()
    resolved_age = age if age is not None else random.randint(18, 70)
    resolved_personality = personality_json or generate_personality()
    resolved_job = job if job is not None else _assign_starting_job()
    resolved_neighborhood = neighborhood if neighborhood is not None else random.choice(NEIGHBORHOOD_NAMES)

    citizen = citizen_repo.create(
        db,
        name=resolved_name,
        age=resolved_age,
        personality_json=resolved_personality,
        job=resolved_job,
        neighborhood=resolved_neighborhood,
    )

    # ---- World Phase 2 hook: give the new citizen a place to live ----
    #
    # Without this, a citizen created at runtime would have no city/district/
    # house and would be invisible on the 3D map until someone ran a full
    # regeneration. This assigns them the least-populated housing district and
    # moves them into a vacant house.
    #
    # Wrapped in a bare try/except ON PURPOSE — same defensive pattern as the
    # seeders in main.py. Placing a citizen on the map is a cosmetic
    # convenience; it must NEVER be able to fail citizen creation, which is a
    # core feature that predates the world system entirely. The citizen is
    # already committed by this point, so the worst case is an unplaced citizen
    # that the next `POST /api/v1/world/generate` picks up.
    try:
        world_generation_service.assign_citizen_to_world(db, citizen)
    except Exception as exc:  # noqa: BLE001 — intentionally broad, see above
        print(f"[citizens] Could not place citizen {citizen.id} in the world: {exc}")
        db.rollback()

    return citizen

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
    neighborhood: Optional[str],
    current_activity: Optional[str],
) -> Citizen:
    citizen = get_citizen(db, citizen_id)
    return citizen_repo.update(
        db, citizen, name=name, job=job, neighborhood=neighborhood, current_activity=current_activity
    )


def delete_citizen(db: Session, citizen_id: int) -> None:
    citizen = get_citizen(db, citizen_id)
    citizen_repo.delete(db, citizen)
