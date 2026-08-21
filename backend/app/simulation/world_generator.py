"""
Deterministic world layout maths (World Phase 2).

PURE FUNCTIONS ONLY — no Session, no models, no imports from app.services or
app.repositories. Everything here takes plain numbers/dicts and returns plain
dicts. That keeps the geometry unit-testable without a database and keeps this
module in the same family as simulation/jobs.py and simulation/world_layout.py.

--------------------------------------------------------------------------
DETERMINISM — THE WHOLE POINT OF THIS FILE
--------------------------------------------------------------------------
The spec: "The world generation should be deterministic where possible. Do not
use meaningless random coordinates every time the server restarts. A citizen's
house should not randomly move every time."

Two things guarantee that:

1. Every random number comes from `stable_rng(...)`, which seeds a private
   random.Random from a SHA-256 of a stable key (city id, district id, slot
   index). It NEVER touches the global `random` module, so it is unaffected by
   anything else the app does, and the same key always produces the same
   numbers on every machine and every Python version.

   NOTE: `hash()` is deliberately NOT used — CPython salts string hashing per
   process (PYTHONHASHSEED), so `hash("x")` differs between restarts. That is
   exactly the bug this file exists to avoid.

2. The result is written to the `buildings` / `roads` tables once and read back
   from the DB afterwards. Even if this file's algorithm is later improved,
   already-generated worlds keep the positions they have.

--------------------------------------------------------------------------
COORDINATE CONVENTIONS
--------------------------------------------------------------------------
Everything is on the Three.js XZ ground plane (Y is the up axis).

  * building offsets returned here are relative to the CITY centre
    (district offset + slot offset), matching models/building.py
  * road coordinates returned here are ABSOLUTE, matching models/road.py
"""

import hashlib
import math
import random
from typing import Optional

from app.simulation.building_types import (
    BUILDING_FACTORY,
    BUILDING_GOVERNMENT_OFFICE,
    BUILDING_HOUSE,
    BUILDING_MONUMENT,
    BUILDING_OFFICE,
    BUILDING_PARK_FEATURE,
    BUILDING_PARLIAMENT,
    BUILDING_PRESIDENTIAL_PALACE,
    BUILDING_SHOP,
    ROAD_DISTRICT,
    ROAD_GOVERNMENT,
    ROAD_HIGHWAY,
    ROAD_MAIN,
    spec_for,
)
from app.simulation.world_layout import (
    DISTRICT_CENTRAL,
    DISTRICT_COMMERCIAL,
    DISTRICT_GOVERNMENT,
    DISTRICT_INDUSTRIAL,
    DISTRICT_PARK,
    DISTRICT_PRESIDENTIAL,
    DISTRICT_RESIDENTIAL,
    DISTRICT_WORKER,
)

# Districts whose job is to hold citizen houses. Citizens are distributed
# across these; every other district type gets civic/commercial buildings.
HOUSING_DISTRICT_TYPES = (DISTRICT_RESIDENTIAL, DISTRICT_WORKER)

# Keep buildings this far inside the district's edge so the ground plate always
# reads as a boundary rather than being hidden under the buildings.
DISTRICT_MARGIN = 9.0

# Half-width of the clear strip kept down the middle of a district for its
# road. Slots that fall inside it are dropped.
DISTRICT_CORRIDOR_HALF = 5.0

# A district always gets at least this many buildings, even with no citizens
# assigned yet — an empty-looking city reads as "broken" rather than "new".
MIN_BUILDINGS_PER_DISTRICT = 6

# Housing capacity is rounded UP to a multiple of this. See housing_capacity().
HOUSING_CAPACITY_STEP = 8

# Densification floor. If a district still can't fit every citizen at this
# cell size we place fewer houses rather than overlapping them; the service
# reports those citizens as housed-in-district-but-no-building.
MIN_FOOTPRINT = 4.0


# ------------------------------------------------------------------ RNG

def stable_rng(*parts) -> random.Random:
    """
    A private, reproducible RNG derived from a stable key.

    Example: stable_rng("house", city_id, district_id, slot_index) always
    yields the same sequence, forever, on any machine.
    """
    key = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _jitter(rng: random.Random, amount: float) -> float:
    return rng.uniform(-amount, amount)


# -------------------------------------------------------- housing capacity

def housing_capacity(resident_count: int) -> int:
    """
    How many houses a district should contain for `resident_count` residents,
    rounded UP to a multiple of HOUSING_CAPACITY_STEP.

    WHY ROUND UP INSTEAD OF BUILDING EXACTLY ONE HOUSE PER CITIZEN
    -------------------------------------------------------------
    grid_slots() shrinks its cell size to fit the requested count. If the
    requested count moved by one every time a citizen was born, the cell size
    would eventually change and EVERY house in the district would shift — which
    is exactly the "a citizen's house should not randomly move" failure this
    design exists to prevent.

    Rounding to a coarse step means the grid geometry is stable across many
    population changes, and the spare slots become genuine empty houses that a
    newly created citizen can simply move into (see
    world_generation_service.assign_citizen_to_world). A town with a few vacant
    houses also just looks more like a town.
    """
    wanted = max(MIN_BUILDINGS_PER_DISTRICT, resident_count)
    steps = math.ceil(wanted / HOUSING_CAPACITY_STEP)
    return steps * HOUSING_CAPACITY_STEP


def house_footprint_for(district_type: str) -> float:
    """Grid cell size for houses in a district. Worker housing is denser —
    that's the whole character of it. Shared by the generator and the
    incremental placement path so both produce the same grid."""
    footprint = spec_for(BUILDING_HOUSE)["footprint"]
    if district_type == DISTRICT_WORKER:
        footprint *= 0.82
    return footprint


# ------------------------------------------------------------------ grid

def _grid_shape(usable_w: float, usable_d: float, count: int, footprint: float):
    """
    Pick a column/row count that fits `count` slots inside the usable area,
    shrinking the cell if needed.

    Returns (cols, rows, footprint). Shrinking is multiplicative and floored at
    MIN_FOOTPRINT so this always terminates.
    """
    cols = max(1, int(usable_w // footprint))
    rows = max(1, int(usable_d // footprint))

    while cols * rows < count and footprint > MIN_FOOTPRINT:
        footprint *= 0.88
        cols = max(1, int(usable_w // footprint))
        rows = max(1, int(usable_d // footprint))

    return cols, rows, footprint


def grid_slots(
    width: float,
    depth: float,
    count: int,
    footprint: float,
    margin: float = DISTRICT_MARGIN,
    corridor_half: float = DISTRICT_CORRIDOR_HALF,
    rng_key: str = "slots",
) -> list[tuple[float, float]]:
    """
    Lay out up to `count` building slots inside a `width` x `depth` district,
    centred on (0, 0), leaving a clear road corridor along z = 0.

    Slots come back in a stable row-major order (front rows first) so that
    citizen #1 always gets the same house. A small per-slot jitter — seeded
    from `rng_key` plus the slot index — stops the result looking like a
    spreadsheet while staying reproducible.
    """
    usable_w = max(footprint, width - 2 * margin)
    usable_d = max(footprint, depth - 2 * margin)

    cols, rows, cell = _grid_shape(usable_w, usable_d, count, footprint)

    span_w = cols * cell
    span_d = rows * cell
    start_x = -span_w / 2 + cell / 2
    start_z = -span_d / 2 + cell / 2

    jitter_amount = max(0.0, (cell - 6.0) * 0.18)

    # How far from z=0 a slot must sit to clear the road corridor.
    threshold = corridor_half + cell * 0.25

    # GUARD: never let the corridor swallow the entire district.
    #
    # The corridor test drops any row within `threshold` of the centre line, and
    # rows sit at start_z + row*cell. Two cases wipe out every row:
    #   * rows == 1 -> the single row sits at EXACTLY z = 0, so it is always
    #     inside the corridor.
    #   * rows == 2 -> the rows sit at ±cell/2, which is inside the corridor
    #     whenever cell/2 < corridor_half + cell/4, i.e. cell < 4*corridor_half.
    #     With corridor_half = 5.0 that is any cell under 20 units — which
    #     includes the 18-unit shop grid, so commercial districts came back
    #     completely empty.
    #
    # An empty district is far worse than a district without its road strip, so
    # when no row can clear the corridor we drop the corridor instead of the
    # buildings. Districts that already had at least one clear row are
    # unaffected, so this changes no existing building's position.
    if not any(abs(start_z + row * cell) >= threshold for row in range(rows)):
        threshold = 0.0

    slots: list[tuple[float, float]] = []
    index = 0
    for row in range(rows):
        for col in range(cols):
            base_x = start_x + col * cell
            base_z = start_z + row * cell

            # Keep the middle strip clear for the district road.
            if abs(base_z) < threshold:
                index += 1
                continue

            rng = stable_rng(rng_key, index)
            slots.append(
                (
                    base_x + _jitter(rng, jitter_amount),
                    base_z + _jitter(rng, jitter_amount),
                )
            )
            index += 1
            if len(slots) >= count:
                return slots

    return slots


# ------------------------------------------------------- building blueprints

def _blueprint(
    type_: str,
    district_offset_x: float,
    district_offset_z: float,
    slot_x: float,
    slot_z: float,
    rng: random.Random,
    name: Optional[str] = None,
    scale: float = 1.0,
    rotate: bool = True,
) -> dict:
    """
    One building, positioned relative to the CITY centre.

    Size comes from the type spec with a small deterministic variation so a
    street of houses isn't eleven identical boxes.
    """
    spec = spec_for(type_)
    wobble = rng.uniform(0.88, 1.14)
    height_wobble = rng.uniform(0.82, 1.26)

    return {
        "type": type_,
        "name": name,
        "offset_x": district_offset_x + slot_x,
        "offset_z": district_offset_z + slot_z,
        "width": round(spec["width"] * scale * wobble, 3),
        "depth": round(spec["depth"] * scale * wobble, 3),
        "height": round(spec["height"] * scale * height_wobble, 3),
        # Landmarks stay square to the world — a crooked Parliament looks like
        # a bug, not variety.
        "rotation": round(rng.uniform(-0.09, 0.09), 4) if rotate else 0.0,
        "is_landmark": bool(spec["is_landmark"]),
    }


def plan_presidential_district(district: dict, city_id: int) -> list[dict]:
    """
    The hand-placed layout for the Presidential District (§5, §17).

    Not grid-generated: this is the visual centre of political power, so the
    Palace, the Parliament and the flanking government offices are positioned
    explicitly and symmetrically about the district's axis. The Palace sits at
    the far end, the Parliament in front of it, and the ceremonial government
    road (added by plan_city_roads) runs up the middle toward them.
    """
    dx = district["offset_x"]
    dz = district["offset_z"]
    width = district["width"]
    depth = district["depth"]

    rng = stable_rng("presidential", city_id, district["id"])
    buildings: list[dict] = []

    # Palace: deepest point of the district, the thing you see first.
    buildings.append(
        _blueprint(
            BUILDING_PRESIDENTIAL_PALACE,
            dx, dz,
            0.0, -depth * 0.20,
            rng, name="Presidential Palace", scale=1.0, rotate=False,
        )
    )

    # Parliament: in front of the Palace, on the same axis.
    buildings.append(
        _blueprint(
            BUILDING_PARLIAMENT,
            dx, dz,
            0.0, depth * 0.22,
            rng, name="Parliament", scale=1.0, rotate=False,
        )
    )

    # Government offices flanking the axis, two per side.
    flank_x = width * 0.30
    for i, (ox, oz) in enumerate(
        [
            (-flank_x, -depth * 0.16),
            (flank_x, -depth * 0.16),
            (-flank_x, depth * 0.24),
            (flank_x, depth * 0.24),
        ]
    ):
        buildings.append(
            _blueprint(
                BUILDING_GOVERNMENT_OFFICE,
                dx, dz, ox, oz,
                stable_rng("gov-office", city_id, district["id"], i),
                name=f"Government Office {i + 1}",
                rotate=False,
            )
        )

    return buildings


def plan_district_buildings(
    district: dict,
    city_id: int,
    house_count: int = 0,
    shop_names: Optional[list[str]] = None,
) -> list[dict]:
    """
    Every building for one district, positioned relative to the city centre.

    `house_count` is how many citizens have been assigned to this district —
    housing districts generate exactly that many houses (plus a few spares so
    the street doesn't end abruptly), other district types ignore it.
    """
    d_type = district["type"]

    if d_type == DISTRICT_PRESIDENTIAL:
        return plan_presidential_district(district, city_id)

    dx = district["offset_x"]
    dz = district["offset_z"]
    width = district["width"]
    depth = district["depth"]
    key = f"district-{city_id}-{district['id']}"

    if d_type in HOUSING_DISTRICT_TYPES:
        wanted = housing_capacity(house_count)
        slots = grid_slots(
            width, depth, wanted, house_footprint_for(d_type), rng_key=key
        )
        return [
            _blueprint(
                BUILDING_HOUSE, dx, dz, sx, sz,
                stable_rng("house", city_id, district["id"], i),
            )
            for i, (sx, sz) in enumerate(slots)
        ]

    if d_type == DISTRICT_COMMERCIAL:
        names = shop_names or []
        wanted = max(MIN_BUILDINGS_PER_DISTRICT, len(names))
        slots = grid_slots(width, depth, wanted, spec_for(BUILDING_SHOP)["footprint"], rng_key=key)
        out = []
        for i, (sx, sz) in enumerate(slots):
            out.append(
                _blueprint(
                    BUILDING_SHOP, dx, dz, sx, sz,
                    stable_rng("shop", city_id, district["id"], i),
                    name=names[i] if i < len(names) else None,
                )
            )
        return out

    if d_type == DISTRICT_INDUSTRIAL:
        slots = grid_slots(
            width, depth, MIN_BUILDINGS_PER_DISTRICT,
            spec_for(BUILDING_FACTORY)["footprint"], rng_key=key,
        )
        return [
            _blueprint(
                BUILDING_FACTORY, dx, dz, sx, sz,
                stable_rng("factory", city_id, district["id"], i),
                name=f"Factory {i + 1}",
            )
            for i, (sx, sz) in enumerate(slots)
        ]

    if d_type == DISTRICT_GOVERNMENT:
        slots = grid_slots(
            width, depth, MIN_BUILDINGS_PER_DISTRICT,
            spec_for(BUILDING_GOVERNMENT_OFFICE)["footprint"], rng_key=key,
        )
        return [
            _blueprint(
                BUILDING_GOVERNMENT_OFFICE, dx, dz, sx, sz,
                stable_rng("govdist", city_id, district["id"], i),
                name=f"Government Office {i + 1}",
                rotate=False,
            )
            for i, (sx, sz) in enumerate(slots)
        ]

    if d_type == DISTRICT_PARK:
        slots = grid_slots(
            width, depth, 14,
            spec_for(BUILDING_PARK_FEATURE)["footprint"], rng_key=key,
        )
        out = [
            _blueprint(
                BUILDING_PARK_FEATURE, dx, dz, sx, sz,
                stable_rng("park", city_id, district["id"], i),
            )
            for i, (sx, sz) in enumerate(slots)
        ]
        # One monument so the park is a recognisable landmark from above.
        out.append(
            _blueprint(
                BUILDING_MONUMENT, dx, dz, 0.0, -depth * 0.30,
                stable_rng("park-monument", city_id, district["id"]),
                name=f"{district['name']} Monument", rotate=False,
            )
        )
        return out

    # DISTRICT_CENTRAL and anything added later: offices around a monument.
    slots = grid_slots(
        width, depth, MIN_BUILDINGS_PER_DISTRICT + 2,
        spec_for(BUILDING_OFFICE)["footprint"], rng_key=key,
    )
    out = [
        _blueprint(
            BUILDING_OFFICE, dx, dz, sx, sz,
            stable_rng("office", city_id, district["id"], i),
        )
        for i, (sx, sz) in enumerate(slots)
    ]
    if d_type == DISTRICT_CENTRAL:
        out.append(
            _blueprint(
                BUILDING_MONUMENT, dx, dz, 0.0, 0.0,
                stable_rng("monument", city_id, district["id"]),
                name=f"{district['name']} Monument", rotate=False,
            )
        )
    return out


# ------------------------------------------------------------ road blueprints

def plan_city_roads(city: dict, districts: list[dict]) -> list[dict]:
    """
    Roads for one city, in ABSOLUTE world coordinates:

      * one MAIN road from the city centre out to each district centre
        (the presidential district gets a wider GOVERNMENT road instead — §5's
        "roads leading toward it" / "Main Government Road")
      * one DISTRICT spine running east-west through each district, along the
        corridor that grid_slots() kept clear
    """
    cx = city["world_x"]
    cz = city["world_z"]
    roads: list[dict] = []

    for district in districts:
        d_abs_x = cx + district["offset_x"]
        d_abs_z = cz + district["offset_z"]
        is_presidential = district["type"] == DISTRICT_PRESIDENTIAL

        kind = ROAD_GOVERNMENT if is_presidential else ROAD_MAIN
        roads.append(
            {
                "kind": kind,
                "name": (
                    "Main Government Road"
                    if is_presidential
                    else f"{district['name']} Road"
                ),
                "start_x": cx,
                "start_z": cz,
                "end_x": d_abs_x,
                "end_z": d_abs_z,
                "width": 12.0 if is_presidential else 7.0,
            }
        )

        half = max(0.0, district["width"] / 2 - DISTRICT_MARGIN * 0.5)
        roads.append(
            {
                "kind": ROAD_DISTRICT,
                "name": None,
                "start_x": d_abs_x - half,
                "start_z": d_abs_z,
                "end_x": d_abs_x + half,
                "end_z": d_abs_z,
                "width": 4.5,
            }
        )

    return roads


def plan_highways(cities: list[dict]) -> list[dict]:
    """
    Highways from the capital to every other city, so the world reads as one
    connected society rather than four unrelated islands. Falls back to the
    lowest-id city as the hub if nothing is flagged as capital.
    """
    if len(cities) < 2:
        return []

    hub = next((c for c in cities if c.get("is_capital")), cities[0])
    roads: list[dict] = []

    for city in cities:
        if city["id"] == hub["id"]:
            continue
        roads.append(
            {
                "kind": ROAD_HIGHWAY,
                "name": f"{hub['name']} – {city['name']} Highway",
                "start_x": hub["world_x"],
                "start_z": hub["world_z"],
                "end_x": city["world_x"],
                "end_z": city["world_z"],
                "width": 9.0,
            }
        )

    return roads


# ------------------------------------------------------- citizen distribution

def distribute_citizens(
    citizen_ids: list[int],
    housing_district_ids: list[int],
) -> dict[int, int]:
    """
    Map citizen id -> housing district id, deterministically.

    Plain round-robin over districts sorted by id. Deliberately not weighted or
    randomised: it is stable (citizen 7 always lands in the same district), it
    spreads population evenly so no district renders empty, and re-running it
    after new citizens are added never moves anyone who was already placed.

    Returns {} when there is nowhere to put anyone, so callers can no-op.
    """
    if not housing_district_ids:
        return {}

    ordered = sorted(housing_district_ids)
    return {
        citizen_id: ordered[i % len(ordered)]
        for i, citizen_id in enumerate(sorted(citizen_ids))
    }


def marker_offset(citizen_id: int, radius: float = 3.0) -> tuple[float, float]:
    """
    A small stable offset so several citizen markers standing at the same
    building don't render inside one another. Angle is derived from the citizen
    id, so a citizen's marker never jitters between requests.
    """
    rng = stable_rng("marker", citizen_id)
    angle = rng.uniform(0.0, math.tau)
    distance = radius * (0.45 + 0.55 * rng.random())
    return (math.cos(angle) * distance, math.sin(angle) * distance)
