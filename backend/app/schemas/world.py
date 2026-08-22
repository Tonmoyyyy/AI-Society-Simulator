from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.simulation.world_layout import DISTRICT_TYPES

_VALID_DISTRICT_TYPES = set(DISTRICT_TYPES)


# ---------------------------------------------------------------- outputs

class NeighborhoodOut(BaseModel):
    """A district. Carries BOTH its offset from the city centre and its
    absolute world position: the offset is what's stored, the absolute
    position is computed by the service so the renderer can drop these
    numbers straight into a Three.js scene without redoing the maths."""

    id: int
    city_id: int
    name: str
    type: str
    description: Optional[str] = None

    offset_x: float
    offset_z: float
    world_x: float
    world_z: float
    width: float
    depth: float

    population: int


class CityOut(BaseModel):
    id: int
    name: str
    region: str
    description: Optional[str] = None

    world_x: float
    world_z: float
    radius: float
    is_capital: bool

    # Counted from citizens.city_id at request time — not a stored column.
    population: int
    neighborhood_count: int

    created_at: datetime


class CityDetailOut(CityOut):
    """GET /world/cities/{id} — the city plus its districts, so the frontend
    can render or inspect one city in a single request."""
    neighborhoods: list[NeighborhoodOut] = []


# --------------------------------------------------- buildings & roads (P2)

class BuildingOut(BaseModel):
    """
    One structure to draw.

    Like NeighborhoodOut this carries BOTH the stored offset (relative to the
    city centre) and the absolute world position computed by the service, so
    the renderer can use the numbers directly.

    `owner_name` / `shop_name` are resolved live from `citizens` / `shops`
    rather than copied into `buildings` at generation time — that is what makes
    renaming a citizen or a shop update its label on the map with no
    regeneration and no frontend change.
    """

    id: int
    city_id: int
    neighborhood_id: Optional[int] = None

    type: str
    name: Optional[str] = None
    label: str = Field(description="Human-readable type label for the info panel.")
    icon: str = Field(description="Legend/pane icon for this building type.")
    color: str = Field(description="Suggested hex colour, so the renderer holds no palette of its own.")

    offset_x: float
    offset_z: float
    world_x: float
    world_z: float
    width: float
    depth: float
    height: float
    rotation: float
    is_landmark: bool

    owner_citizen_id: Optional[int] = None
    owner_name: Optional[str] = None
    shop_id: Optional[int] = None
    shop_name: Optional[str] = None


class RoadOut(BaseModel):
    """A straight road segment in ABSOLUTE world coordinates (see
    models/road.py for why roads don't use city-relative offsets)."""

    id: int
    city_id: Optional[int] = None
    name: Optional[str] = None
    kind: str
    label: str
    color: str

    start_x: float
    start_z: float
    end_x: float
    end_z: float
    width: float


class WorldCitizenOut(BaseModel):
    """
    A citizen as the MAP needs them — deliberately not the same shape as
    CitizenOut.

    Only the fields the marker and its popup actually use are included (§8),
    plus the resolved position. Reusing CitizenOut here would ship personality
    JSON, energy and health for every marker, which is exactly the
    "do not return unnecessary database fields" the spec warns against.

    `marker_x` / `marker_z` is where to draw the marker right now: at their
    workplace while `current_activity` is work-like, at home otherwise (§16).
    It is DERIVED at read time from stored building positions — never written
    to the DB — so it follows the simulation without a migration.
    """

    id: int
    name: str
    age: int
    job: str
    current_activity: str
    mood: float
    happiness: float

    city_id: Optional[int] = None
    city_name: Optional[str] = None
    neighborhood_id: Optional[int] = None
    neighborhood_name: Optional[str] = None

    home_building_id: Optional[int] = None
    marker_x: float
    marker_z: float
    at_work: bool = Field(
        default=False,
        description="True when the marker is standing at a workplace rather than at home.",
    )
    is_president: bool = False
    is_first_lady: bool = False


class BuildingTypeOut(BaseModel):
    """Powers the map legend and the renderer's palette from backend data."""
    type: str
    label: str
    icon: str
    color: str
    is_landmark: bool


class RoadKindOut(BaseModel):
    kind: str
    label: str
    color: str


class DistrictTypeOut(BaseModel):
    """Powers the map legend from backend data instead of hardcoded HTML."""
    type: str
    label: str
    icon: str
    color: str = Field(description="Flat plate colour for this district's ground.")


class WorldLegendOut(BaseModel):
    """Everything the legend (§11) needs, in one request, all backend-owned so
    the legend can never drift from what the map actually draws."""
    districts: list[DistrictTypeOut] = []
    buildings: list[BuildingTypeOut] = []
    roads: list[RoadKindOut] = []


class WorldGenerateResultOut(BaseModel):
    created_buildings: int
    created_roads: int
    assigned_citizens: int
    housed_citizens: int
    deleted_buildings: int
    deleted_roads: int
    detail: str


class WorldGovernmentOut(BaseModel):
    """
    Government summary for the map's Presidential Palace panel.

    Every field is Optional and the whole object is nullable, because a
    government is not guaranteed to exist or to be fully staffed. Three states
    the map has to tell apart:

      * no government row at all -> `system_available` False, everything null.
        A database that was never seeded, which includes the test suite.
      * a government exists but an office is vacant -> `system_available` True
        with `president_name` still null.
      * a President is in office -> `system_available` True and a real name.

    Government facts (names, tax, curfew) come from `government_service`;
    location facts (capital, presidential district) come from the world.
    `world_service.get_government_summary` is the one place they are merged, and
    it is the only function that has to change if either side moves.

    Names are never hardcoded anywhere: they are resolved from `citizens` on
    every request via the FK on `governments`, so renaming the President updates
    the map with no regeneration and no frontend change.
    """

    president_name: Optional[str] = None
    first_lady_name: Optional[str] = None
    capital_city_id: Optional[int] = None
    capital_city_name: Optional[str] = None
    presidential_neighborhood_id: Optional[int] = None
    presidential_neighborhood_name: Optional[str] = None
    tax_rate: Optional[float] = None
    curfew_enabled: Optional[bool] = None
    system_available: bool = Field(
        default=False,
        description=(
            "False when no government has been established at all; the map hides "
            "government-only UI when this is false. True does NOT imply a sitting "
            "President — check president_name for that."
        ),
    )


class WorldSimulationOut(BaseModel):
    """Header stats for the map UI (population / cities / day / tick)."""

    tick_number: int
    day: int
    population: int
    city_count: int
    neighborhood_count: int
    average_happiness: float
    current_event: Optional[str] = None


class WorldOverviewOut(BaseModel):
    """
    GET /api/v1/world — one request that returns everything needed to build
    the world: cities, districts, every building, every road, every citizen
    marker, the government summary and live simulation stats.

    ON RESPONSE SIZE (§14 "do not return unnecessary database fields", §19)
    ----------------------------------------------------------------------
    `citizens` uses WorldCitizenOut, not CitizenOut — a short list of
    render-relevant fields instead of the full row with its personality JSON. Even so, this response grows
    with the population, so it is capped and paginated at the edges:

      * `?city_id=` restricts everything to one city
      * `?include_citizens=false` drops the citizen list entirely
      * `citizen_limit` caps how many markers come back, and
        `citizens_truncated` tells the frontend it happened

    That keeps the default map load one round trip while leaving a documented
    escape hatch for a 10,000-citizen world later.
    """

    cities: list[CityOut] = []
    neighborhoods: list[NeighborhoodOut] = []
    buildings: list[BuildingOut] = []
    roads: list[RoadOut] = []
    citizens: list[WorldCitizenOut] = []
    government: Optional[WorldGovernmentOut] = None
    simulation: WorldSimulationOut

    unassigned_citizens: int = Field(
        description="Citizens not yet linked to a city. Should be 0 once world generation has run; a non-zero value means POST /api/v1/world/generate hasn't been run since those citizens were created."
    )
    citizens_truncated: bool = Field(
        default=False,
        description="True when the citizen list was cut off by citizen_limit.",
    )
    world_generated: bool = Field(
        default=False,
        description="False when no buildings exist yet — the map should show a 'generate the world' hint instead of an empty plane.",
    )


class WorldSeedResultOut(BaseModel):
    created_cities: int
    created_neighborhoods: int
    detail: str


# ---------------------------------------------------------------- inputs

class CityUpdate(BaseModel):
    """
    Partial update — this is the President/Admin rename flow.

    Position fields (world_x/world_z/radius) are deliberately NOT editable
    here: moving a city would invalidate every building/home coordinate that
    Phase 2 derives from it. Re-layout belongs to a dedicated Phase 2
    regeneration endpoint, not a casual PATCH.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    region: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)


class NeighborhoodUpdate(BaseModel):
    """Partial update — district rename / retype, admin only."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    type: Optional[str] = Field(default=None, max_length=30)
    description: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v):
        if v is not None and v not in _VALID_DISTRICT_TYPES:
            raise ValueError(f"type must be one of {sorted(_VALID_DISTRICT_TYPES)}")
        return v
