import random
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.citizen import Citizen
from app.repositories import citizen_repo, simulation_tick_repo
from app.services import government_service, world_generation_service
from app.simulation.genders import (
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_NAMES,
    GENDER_OTHER,
    GENDER_UNKNOWN,
    label_for,
)
from app.simulation.jobs import JOB_NAMES
from app.simulation.neighborhoods import NEIGHBORHOOD_NAMES
from app.simulation.name_generator import generate_person, infer_gender_from_name
from app.simulation.personality import generate_personality

# New citizens are employed 75% of the time (a random job from the
# catalog), unemployed the rest — a real city isn't 100% employed, and an
# all-unemployed starting population made the economy/social features feel
# dead until someone manually assigned jobs (see discussion that led to
# this fix).
_EMPLOYMENT_RATE = 0.75

# Which fields `update_citizen` is allowed to write. A whitelist rather than
# "whatever the caller passed" so that a future schema change, or a caller that
# hands over a raw request body, can never reach `id`, `is_alive`, `created_at`
# or the world-location FKs. The schema layer validates the VALUES; this
# validates the KEYS, and the two checks catch different mistakes.
_EDITABLE_FIELDS = frozenset(
    {
        "name",
        "gender",
        "age",
        "job",
        "neighborhood",
        "current_activity",
        "national_id",
        "personality_json",
        "mood",
        "happiness",
        "energy",
        "health",
    }
)

# The buckets the demographics chart draws. A presentation decision, so it lives
# in the service rather than in SQL — see citizen_repo.list_ages.
# (lower_inclusive, upper_inclusive_or_None, label)
_AGE_BRACKETS: tuple[tuple[int, Optional[int], str], ...] = (
    (0, 17, "Under 18"),
    (18, 29, "18-29"),
    (30, 44, "30-44"),
    (45, 59, "45-59"),
    (60, 74, "60-74"),
    (75, None, "75+"),
)


class CitizenError(Exception):
    """Raised for citizen business-rule failures the API layer maps to HTTP."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CitizenNotFound(CitizenError):
    pass


class CitizenLimitReached(CitizenError):
    pass


class DuplicateNationalId(CitizenError):
    """The requested national_id already belongs to someone else."""
    pass


class CitizenAlreadyDead(CitizenError):
    """Recording a death for someone already recorded dead."""
    pass


class CitizenNotDead(CitizenError):
    """Reviving someone who is alive."""
    pass


def _assign_starting_job() -> str:
    if random.random() < _EMPLOYMENT_RATE:
        return random.choice(JOB_NAMES)
    return "unemployed"


def _current_tick(db: Session) -> int:
    """The most recent tick number, or 0 if the simulation has never run.

    Same lookup `government_service.ensure_government` uses. Ticks are 1-BASED
    (`simulation_tick_repo.next_tick_number` returns `(max or 0) + 1`), so 0
    genuinely means "before the first tick" and is not an off-by-one.
    """
    recent = simulation_tick_repo.list_recent(db, limit=1)
    return recent[0].tick_number if recent else 0


def issue_national_id(citizen_id: int) -> str:
    """The human-facing number for a citizen, derived from their primary key.

    Deterministic on purpose: the same citizen always yields the same number, so
    the migration's backfill and this function agree and nobody has to reconcile
    two numbering schemes. Uniqueness follows from the primary key being unique,
    and the unique index on the column is the backstop for a hand-edited value.
    """
    return f"{settings.NATIONAL_ID_PREFIX}-{citizen_id:06d}"


def _reject_duplicate_national_id(
    db: Session, national_id: str, allow_citizen_id: Optional[int] = None
) -> None:
    existing = citizen_repo.get_by_national_id(db, national_id)
    if existing is not None and existing.id != allow_citizen_id:
        raise DuplicateNationalId(
            f"national_id {national_id} already belongs to citizen {existing.id}"
        )


def create_citizen(
    db: Session,
    name: Optional[str],
    age: Optional[int],
    job: Optional[str] = None,
    neighborhood: Optional[str] = None,
    personality_json: Optional[dict] = None,
    gender: Optional[str] = None,
    national_id: Optional[str] = None,
) -> Citizen:
    """Every field is independently overridable — pass any subset and the
    rest still get randomized. Validation of job/neighborhood/personality/gender
    values already happened at the schema layer (schemas/citizen.py); this
    layer only fills in what wasn't provided.

    NAME AND GENDER ARE RESOLVED TOGETHER so the two never contradict each other:
    a citizen called "Maya" is not silently recorded as male, and asking for a
    female citizen without naming her does not produce a male-pool name. See
    simulation/name_generator.generate_person.
    """
    current_count = citizen_repo.count(db)
    if current_count >= settings.MAX_CITIZENS_V0:
        raise CitizenLimitReached(
            f"Citizen limit reached ({settings.MAX_CITIZENS_V0} for v0.1) — cannot create more."
        )

    if name and gender:
        resolved_name, resolved_gender = name, gender
    elif name:
        resolved_name, resolved_gender = name, infer_gender_from_name(name)
    else:
        resolved_name, resolved_gender = generate_person(gender)

    resolved_age = age if age is not None else random.randint(18, 70)
    resolved_personality = personality_json or generate_personality()
    resolved_job = job if job is not None else _assign_starting_job()
    resolved_neighborhood = neighborhood if neighborhood is not None else random.choice(NEIGHBORHOOD_NAMES)

    if national_id is not None:
        _reject_duplicate_national_id(db, national_id)

    citizen = citizen_repo.create(
        db,
        name=resolved_name,
        age=resolved_age,
        personality_json=resolved_personality,
        job=resolved_job,
        neighborhood=resolved_neighborhood,
        gender=resolved_gender,
        national_id=national_id,
    )

    if citizen.national_id is None:
        citizen_repo.set_national_id(db, citizen, issue_national_id(citizen.id))

    try:
        world_generation_service.assign_citizen_to_world(db, citizen)
    except Exception as exc:  # noqa: BLE001
        print(f"[citizens] Could not place citizen {citizen.id} in the world: {exc}")
        db.rollback()

    return citizen


def get_citizen(db: Session, citizen_id: int) -> Citizen:
    """Resolves dead citizens too — a death must not make someone's profile,
    posts or timeline entries 404, or recording it would amount to hiding it."""
    citizen = citizen_repo.get_by_id(db, citizen_id)
    if citizen is None:
        raise CitizenNotFound(f"Citizen {citizen_id} not found")
    return citizen


def list_citizens(
    db: Session,
    page: int,
    page_size: int,
    include_dead: bool = False,
    gender: Optional[str] = None,
    search: Optional[str] = None,
) -> tuple[list[Citizen], int]:
    """Living citizens by default."""
    offset = (page - 1) * page_size
    return citizen_repo.list_paginated(
        db,
        offset=offset,
        limit=page_size,
        include_dead=include_dead,
        gender=gender,
        search=search,
    )


def update_citizen(db: Session, citizen_id: int, **fields) -> Citizen:
    """Full profile edit."""
    citizen = get_citizen(db, citizen_id)

    clean = {
        key: value
        for key, value in fields.items()
        if key in _EDITABLE_FIELDS and value is not None
    }

    if "national_id" in clean:
        _reject_duplicate_national_id(
            db, clean["national_id"], allow_citizen_id=citizen.id
        )

    if not clean:
        return citizen
    return citizen_repo.update(db, citizen, **clean)


def mark_citizen_dead(
    db: Session, citizen_id: int, cause: Optional[str] = None
) -> dict:
    """Record a death: soft flag, history preserved, offices vacated."""
    citizen = get_citizen(db, citizen_id)
    if not citizen.is_alive:
        raise CitizenAlreadyDead(
            f"Citizen {citizen_id} is already recorded as deceased"
        )

    citizen_repo.mark_dead(
        db,
        citizen,
        tick_number=_current_tick(db),
        cause=cause or "recorded by admin",
    )

    vacated = government_service.vacate_offices_for_citizen(db, citizen.id)
    return {"citizen": citizen, "vacated_offices": vacated}


def revive_citizen(db: Session, citizen_id: int) -> Citizen:
    """Undo a death."""
    citizen = get_citizen(db, citizen_id)
    if citizen.is_alive:
        raise CitizenNotDead(f"Citizen {citizen_id} is not deceased")
    return citizen_repo.revive(db, citizen)


def delete_citizen(db: Session, citizen_id: int) -> None:
    """HARD delete — the row and every cascade from it."""
    citizen = get_citizen(db, citizen_id)

    # Temporary bypass of Foreign Key checks for nested/self-referencing constraints
    db.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

    try:
        db.execute(text("DELETE FROM comments WHERE citizen_id = :id"), {"id": citizen_id})
        db.execute(text("DELETE FROM posts WHERE citizen_id = :id"), {"id": citizen_id})
        db.execute(text("DELETE FROM reactions WHERE citizen_id = :id"), {"id": citizen_id})
        db.execute(text("DELETE FROM parliament_members WHERE citizen_id = :id"), {"id": citizen_id})
        db.execute(text("DELETE FROM wallets WHERE citizen_id = :id"), {"id": citizen_id})

        citizen_repo.delete(db, citizen)
        db.commit()
    finally:
        db.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))


# ------------------------------------------------------------- demographics

def _gender_rows(counts: dict[str, int]) -> list[dict]:
    return [
        {"gender": g, "label": label_for(g), "count": counts.get(g, 0)}
        for g in GENDER_NAMES
    ]


def _age_bracket_rows(ages: list[int]) -> list[dict]:
    rows = []
    for low, high, label in _AGE_BRACKETS:
        if high is None:
            count = sum(1 for a in ages if a >= low)
        else:
            count = sum(1 for a in ages if low <= a <= high)
        rows.append({"label": label, "count": count})
    return rows


def get_demographics(db: Session) -> dict:
    """Population makeup, computed from the current rows on every call."""
    living_by_gender = citizen_repo.count_by_gender(db, include_dead=False)
    all_by_gender = citizen_repo.count_by_gender(db, include_dead=True)

    living = citizen_repo.count(db)
    deceased = citizen_repo.count_dead(db)

    ages = citizen_repo.list_ages(db, include_dead=False)

    return {
        "living": living,
        "deceased": deceased,
        "total_ever": living + deceased,
        "gender_breakdown": _gender_rows(living_by_gender),
        "gender_breakdown_all_time": _gender_rows(all_by_gender),
        "male": living_by_gender.get(GENDER_MALE, 0),
        "female": living_by_gender.get(GENDER_FEMALE, 0),
        "other": living_by_gender.get(GENDER_OTHER, 0),
        "unknown": living_by_gender.get(GENDER_UNKNOWN, 0),
        "age_brackets": _age_bracket_rows(ages),
        "average_age": round(sum(ages) / len(ages), 1) if ages else None,
    }