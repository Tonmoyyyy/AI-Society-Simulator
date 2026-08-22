from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from typing import Optional

from app.core.deps import get_db, get_current_user, require_admin
from app.models.user import User
from app.schemas.citizen import (
    CitizenCreate,
    CitizenDeathOut,
    CitizenDeathRequest,
    CitizenDemographicsOut,
    CitizenUpdate,
    CitizenOut,
    CitizenListResponse,
)
from app.schemas.simulation import MemoryOut
from app.services import citizen_service, simulation_service
from app.services.citizen_service import (
    CitizenAlreadyDead,
    CitizenLimitReached,
    CitizenNotDead,
    CitizenNotFound,
    DuplicateNationalId,
)
from app.simulation.genders import GENDER_NAMES, label_for
from app.simulation.jobs import JOB_NAMES
from app.simulation.neighborhoods import NEIGHBORHOOD_NAMES
from app.simulation.personality import TRAITS as TRAIT_NAMES

router = APIRouter(prefix="/api/v1/citizens", tags=["citizens"])

# ---------------------------------------------------------------------------
# ROUTE ORDER MATTERS. Starlette matches in registration order, first match
# wins, so every literal path (`/options`, `/demographics`) must be declared
# BEFORE `/{citizen_id}`. Registered the other way round, a request for
# /api/v1/citizens/demographics would be matched by `/{citizen_id}` and fail
# validation trying to parse "demographics" as an int. Same rule the world
# router documents.
# ---------------------------------------------------------------------------


@router.post("", response_model=CitizenOut, status_code=status.HTTP_201_CREATED)
def create_citizen(
    payload: CitizenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # citizen creation is an authenticated action
):
    """Create a citizen. An empty body randomizes everything; any field you send
    overrides just that field.

    `name` and `gender` are resolved together, so a citizen never ends up with a
    name from one pool and a gender from the other. `national_id` is normally
    omitted — one is issued from the new citizen's id."""
    try:
        citizen = citizen_service.create_citizen(
            db,
            name=payload.name,
            age=payload.age,
            job=payload.job,
            neighborhood=payload.neighborhood,
            personality_json=payload.personality_json,
            gender=payload.gender,
            national_id=payload.national_id,
        )
    except CitizenLimitReached as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except DuplicateNationalId as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    return citizen


@router.get("", response_model=CitizenListResponse)
def list_citizens(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_dead: bool = Query(
        default=False,
        description="Include deceased citizens. Off by default so 'the population' means the living.",
    ),
    gender: Optional[str] = Query(
        default=None,
        description="Filter to one gender. Values from GET /api/v1/citizens/options.",
    ),
    search: Optional[str] = Query(
        default=None,
        max_length=100,
        description="Substring match on name or national ID.",
    ),
    db: Session = Depends(get_db),
):
    """Public read — spectators can browse citizens without logging in.

    LIVING CITIZENS ONLY unless `include_dead=true`. That default is what keeps
    every existing consumer of this route — the citizens page, the leaderboards —
    showing a population rather than a cemetery. The admin roster passes
    `include_dead=true` so a death can be found and, if it was a mistake, undone.

    `total` always counts the same filtered set as `items`, so a filtered page's
    pagination is correct rather than reporting the unfiltered population."""
    items, total = citizen_service.list_citizens(
        db,
        page=page,
        page_size=page_size,
        include_dead=include_dead,
        gender=gender,
        search=search,
    )
    return {"total": total, "items": items}


@router.get("/options", response_model=dict)
def get_citizen_options():
    """Public — the valid job/neighborhood/gender/personality-trait values, so the
    frontend's "customize" form never hardcodes a list that could drift
    from the backend's actual validation rules.

    `genders` carries both the stored value and its display label, for the same
    reason the world map reads its labels from GET /api/v1/world/legend: one
    source of truth for what things are called."""
    return {
        "jobs": ["unemployed"] + JOB_NAMES,
        "neighborhoods": NEIGHBORHOOD_NAMES,
        "traits": TRAIT_NAMES,
        "genders": [
            {"value": g, "label": label_for(g)} for g in GENDER_NAMES
        ],
    }


@router.get("/demographics", response_model=CitizenDemographicsOut)
def get_demographics(db: Session = Depends(get_db)):
    """Public — how many men and women are in the society, plus age brackets and
    the living/deceased split.

    Every number is counted at request time. Nothing is cached in a column, so this
    cannot drift out of agreement with the citizens table the way a stored tally
    would the first time a gender was corrected or a death recorded.

    Declared before `/{citizen_id}` on purpose — see the note at the top of this
    file."""
    return citizen_service.get_demographics(db)


@router.get("/{citizen_id}", response_model=CitizenOut)
def get_citizen(citizen_id: int, db: Session = Depends(get_db)):
    """Public — one citizen, alive or dead.

    Deliberately resolves deceased citizens too. Their profile, posts and timeline
    entries must still open, or recording a death would amount to erasing the
    person. `is_alive` in the response is how a UI knows to render it as a
    memorial."""
    try:
        citizen = citizen_service.get_citizen(db, citizen_id)
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return citizen


@router.patch("/{citizen_id}", response_model=CitizenOut)
def update_citizen(
    citizen_id: int,
    payload: CitizenUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full profile edit — name, gender, age, job, neighborhood, national ID,
    personality and wellbeing.

    `exclude_unset=True` so an omitted field is left alone rather than cleared.
    Editing `personality_json` genuinely changes how that citizen decides from the
    next tick onward — that is the intent, not a side effect. Setting `health` at or
    below settings.CRITICAL_HEALTH will kill them on the next tick.

    Not editable here: `city_id`/`neighborhood_id` (relocation has to move the house
    too, or the 3D map draws the marker and the home in different districts), `id`
    (immutable primary key — `national_id` is the identifier you customize), and
    `is_alive` (use POST /{id}/death, which also records when and why and vacates
    any office held)."""
    try:
        citizen = citizen_service.update_citizen(
            db,
            citizen_id,
            **payload.model_dump(exclude_unset=True),
        )
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except DuplicateNationalId as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    return citizen


@router.post(
    "/{citizen_id}/death",
    response_model=CitizenDeathOut,
    status_code=status.HTTP_200_OK,
)
def record_citizen_death(
    citizen_id: int,
    payload: CitizenDeathRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — record a death.

    A SOFT DEATH, NOT A DELETE. The citizen row stays, and so do their wallet,
    posts, comments, memories and every timeline event that mentions them. What
    changes is that they stop counting as population, stop being given turns by the
    tick engine, stop appearing in the citizens list and on the map, and lose any
    office they held. That last part is why the response includes
    `vacated_offices` — marking the President dead also empties the presidency, and
    an admin who was not told would read the relabelled palace as a bug.

    Admin-only, unlike PATCH: ending a life in the simulation is not something an
    ordinary logged-in spectator should be able to do. Reversible via
    POST /{id}/revive if it was a mistake.

    Use DELETE /{citizen_id} instead when you want the row genuinely gone — for
    example one created in error. The two are different operations on purpose."""
    try:
        return citizen_service.mark_citizen_dead(db, citizen_id, cause=payload.cause)
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except CitizenAlreadyDead as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.post("/{citizen_id}/revive", response_model=CitizenOut)
def revive_citizen(
    citizen_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — undo a death.

    A mistake-correction tool, not resurrection as a simulation mechanic. Clears
    the recorded tick and cause and puts the citizen back in the population.

    Does NOT restore any office they held. Vacating was a real change with real
    consequences — someone else may already sit in that seat — so re-appointing is
    a separate, explicit act via PATCH /api/v1/government or the parliament
    routes."""
    try:
        return citizen_service.revive_citizen(db, citizen_id)
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except CitizenNotDead as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.delete("/{citizen_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_citizen(
    citizen_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently remove a citizen and everything cascading from them.

    For rows created by mistake. To record that someone DIED, use
    POST /{citizen_id}/death — that preserves their history, which is what makes
    the society's past readable."""
    try:
        citizen_service.delete_citizen(db, citizen_id)
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/{citizen_id}/memories", response_model=list[MemoryOut])
def get_citizen_memories(
    citizen_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public — a citizen's memory log, most recent first."""
    try:
        citizen_service.get_citizen(db, citizen_id)  # 404s if the citizen doesn't exist
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return simulation_service.get_citizen_memories(db, citizen_id, limit=limit)
