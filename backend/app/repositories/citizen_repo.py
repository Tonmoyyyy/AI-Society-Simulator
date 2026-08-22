from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Query, Session

from app.models.citizen import Citizen

# ---------------------------------------------------------------------------
# THE ALIVE-BY-DEFAULT RULE
# ---------------------------------------------------------------------------
# Death is a flag, not a delete (see models/citizen.py), which means every query
# in this file has to take a position on whether the dead are included. They are
# NOT, by default, everywhere. "The population" means living people — a
# leaderboard, a population count, the tick engine and the candidate picker all
# want the living, and every one of those would be subtly wrong if the default
# went the other way.
#
# `include_dead=True` is the explicit opt-in for the two places that genuinely
# need everyone: the admin roster (so an admin can find and revive someone) and
# the demographics endpoint (which reports living and dead side by side).
#
# `get_by_id` is the deliberate exception — it never filters. A dead citizen's
# profile page, their posts and their timeline entries must all still resolve, or
# recording the death would amount to hiding it.


def _base(db: Session, include_dead: bool) -> Query:
    q = db.query(Citizen)
    if not include_dead:
        q = q.filter(Citizen.is_alive.is_(True))
    return q


def count(db: Session, include_dead: bool = False) -> int:
    """Living citizens by default.

    This is what `citizen_service.create_citizen` checks against
    MAX_CITIZENS_V0, so the cap is a cap on the LIVING population: a death frees
    a slot, the way it would in a real society. Dead rows stay in the table
    forever and are intentionally not counted against the limit.
    """
    stmt = select(func.count()).select_from(Citizen)
    if not include_dead:
        stmt = stmt.where(Citizen.is_alive.is_(True))
    return db.scalar(stmt) or 0


def count_dead(db: Session) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(Citizen).where(Citizen.is_alive.is_(False))
        )
        or 0
    )


def count_by_gender(db: Session, include_dead: bool = False) -> dict[str, int]:
    """`{gender: count}` for the genders actually present.

    Counted with GROUP BY at request time and never cached in a column — the
    same rule that keeps `population` off `cities` and `balance` off `citizens`.
    A stored tally would drift the first time a gender was edited.

    Genders with no citizens are absent from the returned dict rather than
    present with 0. The service fills in the missing keys, because it is the
    layer that knows the full vocabulary; the repository only reports what the
    database contains.
    """
    stmt = select(Citizen.gender, func.count()).group_by(Citizen.gender)
    if not include_dead:
        stmt = stmt.where(Citizen.is_alive.is_(True))
    return {row[0]: row[1] for row in db.execute(stmt).all()}


def list_ages(db: Session, include_dead: bool = False) -> list[int]:
    """Just the age column, for bucketing into brackets in the service.

    One narrow query returning at most MAX_CITIZENS_V0 integers, rather than one
    COUNT query per bracket. The bracket boundaries are a presentation decision,
    so they belong in the service — encoding them as SQL CASE arms here would put
    a display choice in the data layer and need a repository change every time
    the chart's buckets were adjusted.
    """
    stmt = select(Citizen.age)
    if not include_dead:
        stmt = stmt.where(Citizen.is_alive.is_(True))
    return [row[0] for row in db.execute(stmt).all()]


def get_by_id(db: Session, citizen_id: int) -> Optional[Citizen]:
    """Never filters on `is_alive` — see the note at the top of this file."""
    return db.get(Citizen, citizen_id)


def get_by_national_id(db: Session, national_id: str) -> Optional[Citizen]:
    """Used to enforce uniqueness before an insert or an edit.

    The unique index is the real guarantee; this exists so the API can answer
    with a clear 409 instead of letting an IntegrityError surface as a 500.
    """
    return db.query(Citizen).filter(Citizen.national_id == national_id).first()


def list_all(db: Session, include_dead: bool = False) -> list[Citizen]:
    """Unpaginated — used by the tick engine to process every citizen each tick.
    Safe at v0.1 scale (capped at MAX_CITIZENS_V0=100).

    Living only by default, so the dead are not given turns to act.
    """
    return _base(db, include_dead).all()


def list_alive_adults(db: Session, min_age: int) -> list[Citizen]:
    """The eligible pool for public office, ordered by name for a picker UI.

    Ordered by name rather than id because this feeds a list a human reads and
    searches, not a paged API where a stable numeric order matters.
    """
    return (
        db.query(Citizen)
        .filter(Citizen.is_alive.is_(True), Citizen.age >= min_age)
        .order_by(Citizen.name)
        .all()
    )


def list_paginated(
    db: Session,
    offset: int,
    limit: int,
    include_dead: bool = False,
    gender: Optional[str] = None,
    search: Optional[str] = None,
) -> tuple[list[Citizen], int]:
    """`(items, total)` where `total` counts the same filtered set as `items`.

    The total is computed from the same query as the page, not from `count()` —
    otherwise adding a filter would produce a total that disagrees with the rows
    returned, which is exactly the class of bug that
    `test_timeline_total_matches_items_when_empty` was written for elsewhere in
    this project.
    """
    q = _base(db, include_dead)
    if gender is not None:
        q = q.filter(Citizen.gender == gender)
    if search:
        # Matches either identifier a human might type. `like` rather than a
        # full-text index: at 100 rows the difference is unmeasurable and a MySQL
        # full-text index would not work under the SQLite test engine.
        pattern = f"%{search}%"
        q = q.filter(Citizen.name.like(pattern) | Citizen.national_id.like(pattern))

    total = q.count()
    items = q.order_by(Citizen.id).offset(offset).limit(limit).all()
    return items, total


def create(
    db: Session,
    name: str,
    age: int,
    personality_json: dict,
    job: str = "unemployed",
    neighborhood: str = "Unknown",
    gender: Optional[str] = None,
    national_id: Optional[str] = None,
) -> Citizen:
    """`gender=None` and `national_id=None` fall through to the model default and
    to NULL respectively — the service resolves both before calling here, and
    leaving them optional keeps this signature backward compatible for any caller
    that predates them."""
    kwargs = {
        "name": name,
        "age": age,
        "personality_json": personality_json,
        "job": job,
        "neighborhood": neighborhood,
        # mood/happiness/energy/health/current_activity/is_alive use model defaults
    }
    if gender is not None:
        kwargs["gender"] = gender
    if national_id is not None:
        kwargs["national_id"] = national_id

    citizen = Citizen(**kwargs)
    db.add(citizen)
    db.commit()
    db.refresh(citizen)
    return citizen


def update(db: Session, citizen: Citizen, **fields) -> Citizen:
    """Applies only non-None values.

    KEPT AS-IS DELIBERATELY. Callers pass a fixed keyword set with None meaning
    "not supplied", so making this apply None would start clearing fields the
    caller never mentioned. The two operations that genuinely need to write NULL
    have their own functions below (`mark_dead` / `revive`), which is the same
    shape as `building_repo.set_building_owner` existing alongside
    `building_repo.update_building` for exactly this reason.

    Note this also means a boolean cannot be set to False through here — `False`
    passes the `is not None` check, but only because False is not None; anything
    intended to clear a value must not go through this function.
    """
    for key, value in fields.items():
        if value is not None:
            setattr(citizen, key, value)
    db.commit()
    db.refresh(citizen)
    return citizen


def set_national_id(db: Session, citizen: Citizen, national_id: str) -> Citizen:
    """Issued immediately after creation, when the id that seeds it finally exists.

    A separate function rather than a second argument to `create` because the
    number is derived from the primary key, which the database does not hand back
    until the INSERT has already happened.
    """
    citizen.national_id = national_id
    db.commit()
    db.refresh(citizen)
    return citizen


def mark_dead(
    db: Session,
    citizen: Citizen,
    tick_number: int,
    cause: str,
    commit: bool = True,
) -> Citizen:
    """Flip the liveness flag and record when and why.

    `commit=False` exists for the tick engine, which batches every mutation of a
    tick into a single commit and rolls the whole thing back on failure. Calling
    a committing repository function from inside that loop would break the batch
    and defeat the rollback — the same reason `timeline_repo.create` and
    `building_repo.create_building` take this flag.

    Does not touch the citizen's wallet, posts, memories or timeline entries.
    That is the entire point of a soft death.
    """
    citizen.is_alive = False
    citizen.died_at_tick = tick_number
    citizen.death_cause = cause
    # A dead citizen is not doing anything. Left as an explicit assignment
    # because `current_activity` is NOT NULL and would otherwise keep displaying
    # whatever they were last caught doing, which reads as a bug on the profile.
    citizen.current_activity = "deceased"
    db.add(citizen)
    if commit:
        db.commit()
        db.refresh(citizen)
    return citizen


def revive(db: Session, citizen: Citizen) -> Citizen:
    """Undo a death — for an admin who marked the wrong person.

    Writes NULL to `died_at_tick` and `death_cause`, which is precisely why this
    cannot go through `update()`. Not modelled as resurrection in the simulation's
    fiction; it is an undo button for a mistake.
    """
    citizen.is_alive = True
    citizen.died_at_tick = None
    citizen.death_cause = None
    citizen.current_activity = "idle"
    db.commit()
    db.refresh(citizen)
    return citizen


def delete(db: Session, citizen: Citizen) -> None:
    """HARD delete — the row and everything cascading from it.

    Still here on purpose and still the right tool for removing a row created by
    mistake. It is NOT how a death is recorded; see `mark_dead`.
    """
    db.delete(citizen)
    db.commit()
