from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.simulation.building_types import BUILDING_TYPES
from app.simulation.world_layout import DISTRICT_TYPES

_VALID_DISTRICT_TYPES = set(DISTRICT_TYPES)
_VALID_BUILDING_TYPES = set(BUILDING_TYPES)

# Sanity bounds on hand-entered geometry. Generous on purpose — the point is to
# catch a typo or a unit mix-up (a 5000-wide school), not to second-guess an
# admin's taste. The world is roughly 2000 units across, so anything past a few
# hundred is certainly a mistake.
MIN_BUILDING_SIZE = 1.0
MAX_BUILDING_SIZE = 300.0


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
    is_manual: bool = Field(
        default=False,
        description="True when an admin placed this building by hand. Such buildings survive world regeneration; the map's build mode uses this to decide what may be moved or demolished.",
    )

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


# ------------------------------------------------ admin building placement
#
# TWO WAYS TO SAY WHERE, AND EXACTLY ONE MUST BE USED
# ---------------------------------------------------
# `buildings` stores offsets from the city centre, but the map's build mode gets
# a click as an ABSOLUTE point on the ground plane from the Three.js raycaster.
# Making the frontend convert would mean it had to hold a copy of every city's
# world_x/world_z and redo the arithmetic the backend already does in reverse —
# the sort of duplicated maths that drifts. So both spellings are accepted and
# the service converts; `_require_one_position` below makes sure a request never
# supplies both and never leaves the position ambiguous.


class _BuildingGeometryMixin(BaseModel):
    """Shared position/size fields and their cross-field checks.

    A mixin rather than inheritance from BuildingCreate, because create and
    update disagree about what is required — everything is optional on a PATCH,
    including the position.
    """

    offset_x: Optional[float] = Field(
        default=None, description="X offset from the parent city's centre. Use with offset_z."
    )
    offset_z: Optional[float] = Field(
        default=None, description="Z offset from the parent city's centre. Use with offset_x."
    )
    world_x: Optional[float] = Field(
        default=None,
        description="Absolute X on the ground plane — what a map click gives you. The service converts it to an offset. Use with world_z.",
    )
    world_z: Optional[float] = Field(
        default=None, description="Absolute Z on the ground plane. Use with world_x."
    )

    width: Optional[float] = Field(
        default=None, ge=MIN_BUILDING_SIZE, le=MAX_BUILDING_SIZE
    )
    depth: Optional[float] = Field(
        default=None, ge=MIN_BUILDING_SIZE, le=MAX_BUILDING_SIZE
    )
    height: Optional[float] = Field(
        default=None, ge=MIN_BUILDING_SIZE, le=MAX_BUILDING_SIZE
    )
    # Radians, one full turn either way. Y-axis rotation, matching
    # models/building.py — the ground is the XZ plane.
    rotation: Optional[float] = Field(default=None, ge=-6.29, le=6.29)

    @model_validator(mode="after")
    def _positions_are_not_mixed(self):
        """Reject a half-specified or double-specified position.

        A request carrying only `offset_x` is almost always a client bug, and
        silently keeping the old Z would put the building somewhere nobody asked
        for. Likewise `offset_*` together with `world_*`: the two would have to
        agree, and if they didn't there would be no defensible winner.
        """
        has_offset = self.offset_x is not None or self.offset_z is not None
        has_world = self.world_x is not None or self.world_z is not None

        if has_offset and has_world:
            raise ValueError(
                "Give either offset_x/offset_z or world_x/world_z, not both."
            )
        if has_offset and (self.offset_x is None or self.offset_z is None):
            raise ValueError("offset_x and offset_z must be given together.")
        if has_world and (self.world_x is None or self.world_z is None):
            raise ValueError("world_x and world_z must be given together.")
        return self


class BuildingCreate(_BuildingGeometryMixin):
    """
    Admin — place one building by hand (map build mode).

    Size, height and `is_landmark` are optional: omitted, they come from the
    type's entry in simulation/building_types.py, which is what lets the frontend
    place a school by sending a type and a click position and nothing else. That
    is also why the defaults are NOT repeated here — one source of truth for what
    a school is, and it is the same one the generator uses.

    `owner_citizen_id` and `shop_id` are deliberately absent. Home ownership is
    assigned by `world_generation_service`, and a shop's building is chosen at
    generation time; letting a placement request claim either would allow two
    buildings to be one citizen's house.
    """

    type: str = Field(description="One of the types from GET /api/v1/world/building-types.")

    city_id: Optional[int] = Field(
        default=None,
        description="Parent city. Optional if neighborhood_id is given — the service derives it from the district.",
    )
    neighborhood_id: Optional[int] = Field(
        default=None,
        description="District to place it in. Null puts it on city land between districts, which skips the district-bounds check.",
    )
    name: Optional[str] = Field(default=None, max_length=120)
    is_landmark: Optional[bool] = Field(
        default=None,
        description="Draw with special geometry and a name label. Defaults to the type's own setting.",
    )

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v):
        if v not in _VALID_BUILDING_TYPES:
            raise ValueError(f"type must be one of {sorted(_VALID_BUILDING_TYPES)}")
        return v

    @field_validator("name")
    @classmethod
    def _blank_name_is_no_name(cls, v):
        """An empty string from a form field means "no name", not a building
        called "". Houses legitimately have NULL names — the map labels those with
        their owner's name instead."""
        if v is None:
            return None
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def _needs_a_place_and_a_position(self):
        if self.city_id is None and self.neighborhood_id is None:
            raise ValueError("Give city_id, neighborhood_id, or both.")
        if self.offset_x is None and self.world_x is None:
            raise ValueError(
                "A position is required: give offset_x/offset_z or world_x/world_z."
            )
        return self


class BuildingUpdate(_BuildingGeometryMixin):
    """
    Admin — move, resize, rename, retype or re-district one building.

    EVERY FIELD IS OPTIONAL AND OMISSION IS MEANINGFUL. The service reads this
    with `model_dump(exclude_unset=True)`, so a key that isn't in the request body
    is left untouched, while `"name": null` genuinely clears the name and
    `"neighborhood_id": null` moves the building out onto city land. Pydantic
    cannot express that distinction through the type alone — it comes from
    `exclude_unset`, which is why the service must not drop it.

    `city_id` is NOT editable. Offsets are relative to the city centre, so
    changing the parent would teleport the building by the distance between two
    cities while its stored numbers stayed the same. Demolish and re-place instead.
    """

    type: Optional[str] = Field(
        default=None,
        description="Retype the building. Refused while it is somebody's house or a shop's premises — see the API docs.",
    )
    neighborhood_id: Optional[int] = Field(
        default=None, description="Move to a different district; null means city land."
    )
    name: Optional[str] = Field(default=None, max_length=120)
    is_landmark: Optional[bool] = None

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v):
        if v is not None and v not in _VALID_BUILDING_TYPES:
            raise ValueError(f"type must be one of {sorted(_VALID_BUILDING_TYPES)}")
        return v

    @field_validator("name")
    @classmethod
    def _blank_name_is_no_name(cls, v):
        if v is None:
            return None
        v = v.strip()
        return v or None


class BuildingDeleteResultOut(BaseModel):
    """Demolition result. Returns the freed citizen id rather than nothing, so the
    frontend knows whose marker just lost its house without re-fetching."""

    deleted_building_id: int
    former_owner_citizen_id: Optional[int] = None
    detail: str
