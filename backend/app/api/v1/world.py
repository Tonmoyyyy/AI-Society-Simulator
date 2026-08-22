from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.models.user import User
from app.schemas.world import (
    BuildingOut,
    BuildingTypeOut,
    CityDetailOut,
    CityOut,
    CityUpdate,
    DistrictTypeOut,
    NeighborhoodOut,
    NeighborhoodUpdate,
    RoadKindOut,
    RoadOut,
    WorldCitizenOut,
    WorldGenerateResultOut,
    WorldGovernmentOut,
    WorldLegendOut,
    WorldOverviewOut,
    WorldSeedResultOut,
    WorldSimulationOut,
)
from app.services import world_generation_service, world_service
from app.services.world_service import (
    BuildingNotFound,
    CityNotFound,
    DuplicateCityName,
    DuplicateNeighborhoodName,
    NeighborhoodNotFound,
)
from app.simulation.building_types import BUILDING_TYPES

# Built once at import, not per request. The membership test below runs for
# every value in `?type=`, and rebuilding the set inside that comprehension
# rebuilt it once per value — mirrors `_VALID_DISTRICT_TYPES` in schemas/world.py.
_VALID_BUILDING_TYPES = frozenset(BUILDING_TYPES)

router = APIRouter(prefix="/api/v1/world", tags=["world"])


# ------------------------------------------------------------------ reads
# Public, matching the existing read-is-public convention used by
# citizens / posts / shops / dashboard — a spectator can observe the
# civilization without logging in.


@router.get("", response_model=WorldOverviewOut)
def get_world(
    city_id: Optional[int] = Query(
        default=None, description="Restrict the whole payload to a single city"
    ),
    include_citizens: bool = Query(
        default=True, description="Set false for a terrain-only load (no citizen markers)"
    ),
    citizen_limit: int = Query(
        default=world_service.DEFAULT_CITIZEN_LIMIT,
        ge=1,
        le=20000,
        description="Cap on returned citizen markers; `citizens_truncated` reports if it was hit.",
    ),
    db: Session = Depends(get_db),
):
    """Public — everything needed to build the world in one request: cities,
    districts, buildings, roads, citizen markers, the government summary and
    live simulation stats.

    The three query params exist so this response stays bounded as the
    population grows; the defaults are what the map uses on a normal load."""
    try:
        return world_service.get_world_overview(
            db,
            city_id=city_id,
            include_citizens=include_citizens,
            citizen_limit=citizen_limit,
        )
    except CityNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/cities", response_model=list[CityOut])
def list_cities(db: Session = Depends(get_db)):
    """Public — every city with its counted population. Powers the city
    selector dropdown."""
    return world_service.list_cities(db)


@router.get("/district-types", response_model=list[DistrictTypeOut])
def list_district_types():
    """Public — the valid district types with their legend label/icon, so the
    map legend is generated from backend data instead of hardcoded HTML.
    Mirrors the existing /api/v1/citizens/options pattern.

    ORDERING MATTERS: this and every other literal path under /cities... must
    stay declared BEFORE /cities/{city_id}. Starlette matches routes in
    registration order and takes the first match, so moving the parameterised
    route above the literal ones would make /district-types try to parse
    "district-types" as an int city_id and 422."""
    return world_service.list_district_types()


@router.get("/simulation", response_model=WorldSimulationOut)
def get_world_simulation(db: Session = Depends(get_db)):
    """Public — just the header numbers (day, tick, population, happiness, the
    latest timeline event).

    This exists so the map can refresh its header on every tick without
    re-requesting the full overview, which would re-send every building and road
    for the sake of six integers."""
    return world_service.get_simulation_summary(db)


@router.get("/government", response_model=WorldGovernmentOut)
def get_government(db: Session = Depends(get_db)):
    """Public — President / First Lady / capital / presidential district.

    Returns `system_available: false` when no government has been established,
    so the map can hide its government-only labels instead of erroring. Note
    that `true` does not imply a sitting President — an established government
    can have vacant offices, in which case the names are null.

    Names come from the `citizens` rows the government points at, resolved on
    every request and never hardcoded or cached, so a rename is reflected here
    automatically. The map polls this endpoint, so an appointment shows up
    without a page reload.

    See also GET /api/v1/government, which returns the government in full
    (office holder ids, term start, timestamps) rather than this flat,
    render-oriented summary."""
    return world_service.get_government_summary(db)


@router.get("/cities/{city_id}", response_model=CityDetailOut)
def get_city(city_id: int, db: Session = Depends(get_db)):
    """Public — one city plus all of its districts."""
    try:
        return world_service.get_city_detail(db, city_id)
    except CityNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/neighborhoods", response_model=list[NeighborhoodOut])
def list_neighborhoods(
    city_id: Optional[int] = Query(default=None, description="Filter to a single city"),
    db: Session = Depends(get_db),
):
    """Public — districts, optionally filtered to one city."""
    try:
        return world_service.list_neighborhoods(db, city_id=city_id)
    except CityNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/neighborhoods/{neighborhood_id}", response_model=NeighborhoodOut)
def get_neighborhood(neighborhood_id: int, db: Session = Depends(get_db)):
    """Public — a single district."""
    try:
        return world_service.get_neighborhood_detail(db, neighborhood_id)
    except NeighborhoodNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


# ------------------------------------------------- buildings, roads, citizens


@router.get("/building-types", response_model=list[BuildingTypeOut])
def list_building_types():
    """Public — every building type with its label / icon / colour, so the
    renderer and the legend hold no palette of their own. Adding a type is then
    a change in simulation/building_types.py only."""
    return world_service.list_building_types()


@router.get("/road-kinds", response_model=list[RoadKindOut])
def list_road_kinds():
    """Public — road kinds with their render hints."""
    return world_service.list_road_kinds()


@router.get("/legend", response_model=WorldLegendOut)
def get_legend():
    """Public — districts + buildings + roads legend data in one request."""
    return world_service.get_legend()


@router.get("/buildings", response_model=list[BuildingOut])
def list_buildings(
    city_id: Optional[int] = Query(default=None, description="Filter to a single city"),
    neighborhood_id: Optional[int] = Query(
        default=None, description="Filter to a single district"
    ),
    type: Optional[list[str]] = Query(
        default=None,
        description="Repeatable — filter to one or more building types (e.g. ?type=house&type=shop)",
    ),
    db: Session = Depends(get_db),
):
    """Public — generated structures, ordered by id so the renderer's
    InstancedMesh indices stay stable between requests.

    Useful on its own for lazy-loading one city's buildings, or for fetching
    just the landmarks (`?type=presidential_palace&type=parliament`)."""
    if type:
        unknown = [t for t in type if t not in _VALID_BUILDING_TYPES]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown building type(s): {', '.join(unknown)}",
            )
    try:
        return world_service.list_buildings(
            db, city_id=city_id, neighborhood_id=neighborhood_id, types=type
        )
    except (CityNotFound, NeighborhoodNotFound) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/buildings/{building_id}", response_model=BuildingOut)
def get_building(building_id: int, db: Session = Depends(get_db)):
    """Public — one building, for the info panel after a click (§13)."""
    try:
        return world_service.get_building_detail(db, building_id)
    except BuildingNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/roads", response_model=list[RoadOut])
def list_roads(
    city_id: Optional[int] = Query(default=None, description="Filter to a single city"),
    db: Session = Depends(get_db),
):
    """Public — road segments in absolute world coordinates. Filtering by city
    still includes highways, so a city is never drawn without its connections."""
    try:
        return world_service.list_roads(db, city_id=city_id)
    except CityNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/citizens", response_model=list[WorldCitizenOut])
def list_world_citizens(
    city_id: Optional[int] = Query(default=None, description="Filter to a single city"),
    limit: int = Query(
        default=world_service.DEFAULT_CITIZEN_LIMIT,
        ge=1,
        le=20000,
        description="Cap on returned markers",
    ),
    db: Session = Depends(get_db),
):
    """Public — citizen markers with their resolved position for the current
    tick. This is the endpoint the map re-polls to animate citizens moving
    between home and work, so it deliberately returns only render-relevant
    fields rather than the full citizen row."""
    try:
        citizens, _truncated = world_service.list_world_citizens(
            db, city_id=city_id, limit=limit
        )
        return citizens
    except CityNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


# ------------------------------------------------------------------ writes
# Admin-only. `require_admin` already exists in core/deps.py and is what the
# President/Admin rename flow should go through — renaming the nation's
# cities is not something a spectator account should be able to do.


@router.patch("/cities/{city_id}", response_model=CityOut)
def update_city(
    city_id: int,
    payload: CityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — rename a city / edit its region or description. This is why
    city names are never hardcoded in the frontend."""
    try:
        return world_service.update_city(
            db,
            city_id,
            name=payload.name,
            region=payload.region,
            description=payload.description,
        )
    except CityNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except DuplicateCityName as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.patch("/neighborhoods/{neighborhood_id}", response_model=NeighborhoodOut)
def update_neighborhood(
    neighborhood_id: int,
    payload: NeighborhoodUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — rename a district or change its type."""
    try:
        return world_service.update_neighborhood(
            db,
            neighborhood_id,
            name=payload.name,
            type=payload.type,
            description=payload.description,
        )
    except NeighborhoodNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except DuplicateNeighborhoodName as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.post("/seed", response_model=WorldSeedResultOut)
def seed_world(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — create the default world if it doesn't exist yet.

    Idempotent: a no-op once any city exists, so it can never overwrite
    renamed cities. Startup already calls this automatically; the endpoint is
    here for the case where the app first booted without a reachable DB."""
    return world_service.ensure_seed_world(db)


@router.post("/generate", response_model=WorldGenerateResultOut)
def generate_world(
    force: bool = Query(
        default=False,
        description="Delete and rebuild all buildings/roads. Without this, the call is refused when geometry already exists.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — lay out buildings, citizen homes and roads inside the existing
    cities and districts.

    Safe by default: without `?force=true` this refuses to run when geometry
    already exists, so nobody can accidentally re-roll the whole world. It only
    ever touches `buildings` and `roads` — cities, districts and their admin
    renames are never deleted.

    Deterministic: the same cities, districts and citizens always produce the
    same layout, because every position is derived from a SHA-256-seeded RNG
    keyed on database ids rather than an unseeded `random`. A citizen's house
    does not move when the server restarts.

    Returns zero counts plus an explanatory `detail` (not an error) when it
    declines to run, mirroring POST /seed."""
    return world_generation_service.generate_world(db, force=force)
