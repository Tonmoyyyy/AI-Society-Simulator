"""
World READ logic — the single service the 3D map talks to.

Responsibilities:
  * expose cities / districts / buildings / roads / citizen markers
  * count population from `citizens` (never a cached column)
  * seed the default cities+districts once (World Phase 1)
  * let an admin rename cities and districts
  * resolve where each citizen's marker stands, from their live
    `current_activity` (World Phase 7)

The WRITE side — generating buildings, roads and citizen homes — deliberately
lives in world_generation_service.py, so a bug in generation can't be triggered
by someone merely viewing the map. See that module's docstring.

Everything here returns plain dicts; the schemas in schemas/world.py are what
shape the HTTP response.
"""

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.building import Building
from app.models.citizen import Citizen
from app.models.city import City
from app.models.neighborhood import Neighborhood
from app.models.road import Road
from app.repositories import (
    building_repo,
    citizen_repo,
    shop_repo,
    simulation_tick_repo,
    timeline_repo,
    world_repo,
)
from app.services import dashboard_service
from app.simulation.building_types import (
    BUILDING_TYPE_SPECS,
    BUILDING_TYPES,
    ROAD_KIND_SPECS,
    ROAD_KINDS,
    VENUE_TYPES_BY_ACTIVITY,
    WORK_ACTIVITIES,
    spec_for,
)
from app.simulation.world_generator import marker_offset
from app.simulation.world_layout import (
    DEFAULT_WORLD,
    DISTRICT_PRESIDENTIAL,
    DISTRICT_TYPE_LABELS,
    DISTRICT_TYPES,
)

# SDD §5: 1 tick = 1 simulated hour. Day 1 is ticks 0-23.
TICKS_PER_DAY = 24

# Default cap on how many citizen markers GET /api/v1/world returns. The
# renderer draws them with a single InstancedMesh so it can handle far more than
# this; the cap exists to bound the JSON payload, not the graphics. Raise it
# with ?citizen_limit=.
DEFAULT_CITIZEN_LIMIT = 1500


class WorldError(Exception):
    """Raised for world business-rule failures the API layer maps to HTTP."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CityNotFound(WorldError):
    pass


class NeighborhoodNotFound(WorldError):
    pass


class BuildingNotFound(WorldError):
    pass


class DuplicateCityName(WorldError):
    pass


class DuplicateNeighborhoodName(WorldError):
    pass


# ------------------------------------------------------------------ seeding

def ensure_seed_world(db: Session) -> dict:
    """
    Create the default cities/districts if — and only if — the world is empty.

    Idempotent: a single `count_cities` check makes this a no-op on every boot
    after the first, which is what makes admin renames permanent. Same
    resilience pattern as simulation/seed_shops.ensure_seed_shops.

    Commits once at the end rather than per row, so a failure halfway through
    can't leave a half-built world behind.
    """
    if world_repo.count_cities(db) > 0:
        return {
            "created_cities": 0,
            "created_neighborhoods": 0,
            "detail": "World already exists — seed skipped (existing data is the source of truth).",
        }

    created_cities = 0
    created_neighborhoods = 0

    for city_blueprint in DEFAULT_WORLD:
        city = world_repo.create_city(
            db,
            name=city_blueprint["name"],
            region=city_blueprint["region"],
            description=city_blueprint["description"],
            world_x=city_blueprint["world_x"],
            world_z=city_blueprint["world_z"],
            radius=city_blueprint["radius"],
            is_capital=city_blueprint["is_capital"],
            commit=False,
        )
        # flush (not commit) to get city.id for the FK below while keeping
        # the whole seed inside one transaction.
        db.flush()
        created_cities += 1

        for district in city_blueprint["neighborhoods"]:
            world_repo.create_neighborhood(
                db,
                city_id=city.id,
                name=district["name"],
                type=district["type"],
                description=district["description"],
                offset_x=district["offset_x"],
                offset_z=district["offset_z"],
                width=district["width"],
                depth=district["depth"],
                commit=False,
            )
            created_neighborhoods += 1

    db.commit()
    return {
        "created_cities": created_cities,
        "created_neighborhoods": created_neighborhoods,
        "detail": f"Seeded {created_cities} cities and {created_neighborhoods} districts.",
    }


# ------------------------------------------------------------- serialization

def _serialize_city(city: City, population: int, neighborhood_count: int) -> dict:
    return {
        "id": city.id,
        "name": city.name,
        "region": city.region,
        "description": city.description,
        "world_x": city.world_x,
        "world_z": city.world_z,
        "radius": city.radius,
        "is_capital": city.is_capital,
        "population": population,
        "neighborhood_count": neighborhood_count,
        "created_at": city.created_at,
    }


def _serialize_neighborhood(neighborhood: Neighborhood, city: Optional[City], population: int) -> dict:
    """Absolute world position = city centre + district offset. Computed here
    so the renderer never has to join these two records itself."""
    base_x = city.world_x if city else 0.0
    base_z = city.world_z if city else 0.0
    return {
        "id": neighborhood.id,
        "city_id": neighborhood.city_id,
        "name": neighborhood.name,
        "type": neighborhood.type,
        "description": neighborhood.description,
        "offset_x": neighborhood.offset_x,
        "offset_z": neighborhood.offset_z,
        "world_x": base_x + neighborhood.offset_x,
        "world_z": base_z + neighborhood.offset_z,
        "width": neighborhood.width,
        "depth": neighborhood.depth,
        "population": population,
    }


def _serialize_building(
    building: Building,
    city: Optional[City],
    owner_name: Optional[str] = None,
    shop_name: Optional[str] = None,
) -> dict:
    """
    Same offset -> absolute conversion as districts, plus the type's render
    hints (label / icon / colour) so the frontend holds no palette of its own —
    adding a building type is then a backend-only change.
    """
    base_x = city.world_x if city else 0.0
    base_z = city.world_z if city else 0.0
    spec = spec_for(building.type)

    return {
        "id": building.id,
        "city_id": building.city_id,
        "neighborhood_id": building.neighborhood_id,
        "type": building.type,
        "name": building.name,
        "label": spec["label"],
        "icon": spec["icon"],
        "color": spec["color"],
        "offset_x": building.offset_x,
        "offset_z": building.offset_z,
        "world_x": base_x + building.offset_x,
        "world_z": base_z + building.offset_z,
        "width": building.width,
        "depth": building.depth,
        "height": building.height,
        "rotation": building.rotation,
        "is_landmark": building.is_landmark,
        "owner_citizen_id": building.owner_citizen_id,
        "owner_name": owner_name,
        "shop_id": building.shop_id,
        "shop_name": shop_name,
    }


def _serialize_road(road: Road) -> dict:
    """Roads are already absolute (see models/road.py), so there's no offset
    conversion — only the kind's render hints get attached."""
    spec = ROAD_KIND_SPECS.get(road.kind, ROAD_KIND_SPECS["district"])
    return {
        "id": road.id,
        "city_id": road.city_id,
        "name": road.name,
        "kind": road.kind,
        "label": spec["label"],
        "color": spec["color"],
        "start_x": road.start_x,
        "start_z": road.start_z,
        "end_x": road.end_x,
        "end_z": road.end_z,
        "width": road.width,
    }


# ---------------------------------------------------------------- read paths

def list_cities(db: Session) -> list[dict]:
    cities = world_repo.list_cities(db)
    populations = world_repo.count_citizens_by_city(db)
    neighborhoods = world_repo.list_neighborhoods(db)

    counts_per_city: dict[int, int] = {}
    for neighborhood in neighborhoods:
        counts_per_city[neighborhood.city_id] = counts_per_city.get(neighborhood.city_id, 0) + 1

    return [
        _serialize_city(city, populations.get(city.id, 0), counts_per_city.get(city.id, 0))
        for city in cities
    ]


def get_city_detail(db: Session, city_id: int) -> dict:
    city = world_repo.get_city(db, city_id)
    if city is None:
        raise CityNotFound(f"City {city_id} not found")

    districts = world_repo.list_neighborhoods(db, city_id=city.id)
    city_populations = world_repo.count_citizens_by_city(db)
    district_populations = world_repo.count_citizens_by_neighborhood(db)

    payload = _serialize_city(city, city_populations.get(city.id, 0), len(districts))
    payload["neighborhoods"] = [
        _serialize_neighborhood(d, city, district_populations.get(d.id, 0)) for d in districts
    ]
    return payload


def list_neighborhoods(db: Session, city_id: Optional[int] = None) -> list[dict]:
    if city_id is not None and world_repo.get_city(db, city_id) is None:
        raise CityNotFound(f"City {city_id} not found")

    districts = world_repo.list_neighborhoods(db, city_id=city_id)
    cities = {city.id: city for city in world_repo.list_cities(db)}
    populations = world_repo.count_citizens_by_neighborhood(db)

    return [
        _serialize_neighborhood(d, cities.get(d.city_id), populations.get(d.id, 0))
        for d in districts
    ]


def get_neighborhood_detail(db: Session, neighborhood_id: int) -> dict:
    neighborhood = world_repo.get_neighborhood(db, neighborhood_id)
    if neighborhood is None:
        raise NeighborhoodNotFound(f"Neighborhood {neighborhood_id} not found")

    city = world_repo.get_city(db, neighborhood.city_id)
    populations = world_repo.count_citizens_by_neighborhood(db)
    return _serialize_neighborhood(neighborhood, city, populations.get(neighborhood.id, 0))


def list_district_types() -> list[dict]:
    """Legend data — backend-owned so the map legend can't drift from the
    types the DB actually accepts."""
    return [
        {
            "type": type_,
            "label": DISTRICT_TYPE_LABELS[type_]["label"],
            "icon": DISTRICT_TYPE_LABELS[type_]["icon"],
            "color": DISTRICT_TYPE_LABELS[type_]["color"],
        }
        for type_ in DISTRICT_TYPES
    ]


# --------------------------------------------------- buildings & roads (P2)

def _owner_names(db: Session, buildings: Iterable[Building]) -> dict[int, str]:
    """
    Resolve owner ids -> live citizen names in ONE query.

    Houses are stored with `name = NULL` on purpose (see models/building.py):
    a house's label is whatever its owner is called *right now*, so renaming a
    citizen renames their house on the map with no regeneration.
    """
    owner_ids = {b.owner_citizen_id for b in buildings if b.owner_citizen_id is not None}
    if not owner_ids:
        return {}

    rows = (
        db.query(Citizen.id, Citizen.name)
        .filter(Citizen.id.in_(owner_ids))
        .all()
    )
    return {citizen_id: name for citizen_id, name in rows}


def _shop_names(db: Session, buildings: Iterable[Building]) -> dict[int, str]:
    """Same idea for shops. `shop_repo.list_shops` is a small unfiltered select
    and the shop count is tiny (v0.1 seeds a handful), so one call beats N
    `get_shop` lookups."""
    shop_ids = {b.shop_id for b in buildings if b.shop_id is not None}
    if not shop_ids:
        return {}
    return {
        shop.id: shop.name
        for shop in shop_repo.list_shops(db)
        if shop.id in shop_ids
    }


def list_buildings(
    db: Session,
    city_id: Optional[int] = None,
    neighborhood_id: Optional[int] = None,
    types: Optional[Iterable[str]] = None,
) -> list[dict]:
    if city_id is not None and world_repo.get_city(db, city_id) is None:
        raise CityNotFound(f"City {city_id} not found")
    if neighborhood_id is not None and world_repo.get_neighborhood(db, neighborhood_id) is None:
        raise NeighborhoodNotFound(f"Neighborhood {neighborhood_id} not found")

    buildings = building_repo.list_buildings(
        db, city_id=city_id, neighborhood_id=neighborhood_id, types=types
    )
    cities = {city.id: city for city in world_repo.list_cities(db)}
    owners = _owner_names(db, buildings)
    shops = _shop_names(db, buildings)

    return [
        _serialize_building(
            building,
            cities.get(building.city_id),
            owner_name=owners.get(building.owner_citizen_id),
            shop_name=shops.get(building.shop_id),
        )
        for building in buildings
    ]


def get_building_detail(db: Session, building_id: int) -> dict:
    building = building_repo.get_building(db, building_id)
    if building is None:
        raise BuildingNotFound(f"Building {building_id} not found")

    city = world_repo.get_city(db, building.city_id)
    owners = _owner_names(db, [building])
    shops = _shop_names(db, [building])
    return _serialize_building(
        building,
        city,
        owner_name=owners.get(building.owner_citizen_id),
        shop_name=shops.get(building.shop_id),
    )


def list_roads(db: Session, city_id: Optional[int] = None) -> list[dict]:
    if city_id is not None and world_repo.get_city(db, city_id) is None:
        raise CityNotFound(f"City {city_id} not found")
    return [_serialize_road(road) for road in building_repo.list_roads(db, city_id=city_id)]


def list_building_types() -> list[dict]:
    return [
        {
            "type": type_,
            "label": BUILDING_TYPE_SPECS[type_]["label"],
            "icon": BUILDING_TYPE_SPECS[type_]["icon"],
            "color": BUILDING_TYPE_SPECS[type_]["color"],
            "is_landmark": BUILDING_TYPE_SPECS[type_]["is_landmark"],
        }
        for type_ in BUILDING_TYPES
    ]


def list_road_kinds() -> list[dict]:
    return [
        {
            "kind": kind,
            "label": ROAD_KIND_SPECS[kind]["label"],
            "color": ROAD_KIND_SPECS[kind]["color"],
        }
        for kind in ROAD_KINDS
    ]


def get_legend() -> dict:
    """One request for the whole legend (§11), so the frontend never hardcodes
    a label, an icon or a colour."""
    return {
        "districts": list_district_types(),
        "buildings": list_building_types(),
        "roads": list_road_kinds(),
    }


# ------------------------------------------------- citizen markers (P2 / P7)

def _venue_index(buildings: Iterable[Building]) -> dict[int, dict[str, list[Building]]]:
    """
    Group buildings as city_id -> type -> [buildings], in one pass.

    Built once per request and then reused for every citizen, which is what
    keeps marker resolution O(citizens) instead of O(citizens x buildings).
    Insertion order follows `list_buildings`' ORDER BY id, so the index is
    deterministic and `citizen.id % len(candidates)` picks the same venue on
    every request.
    """
    index: dict[int, dict[str, list[Building]]] = {}
    for building in buildings:
        index.setdefault(building.city_id, {}).setdefault(building.type, []).append(building)
    return index


def _pick_venue(
    citizen: Citizen, venue_index: dict[int, dict[str, list[Building]]]
) -> Optional[Building]:
    """
    Where does this citizen go for what they're currently doing?

    Reads `citizens.current_activity`, which the tick engine already writes —
    no movement system, no pathfinding, no new column (§16, §18). An activity
    that isn't in VENUE_TYPES_BY_ACTIVITY (sleeping / eating / posting / idle)
    means "stay home", so this returns None.

    The choice is `citizen.id % len(candidates)`: stable across requests and
    server restarts, spreads citizens over the available venues, and needs no
    stored assignment. Preference follows the order in VENUE_TYPES_BY_ACTIVITY —
    a worker fills shops and factories before offices.
    """
    venue_types = VENUE_TYPES_BY_ACTIVITY.get(citizen.current_activity)
    if not venue_types or citizen.city_id is None:
        return None

    by_type = venue_index.get(citizen.city_id)
    if not by_type:
        return None

    candidates: list[Building] = []
    for type_ in venue_types:
        candidates.extend(by_type.get(type_, ()))
    if not candidates:
        return None

    return candidates[citizen.id % len(candidates)]


def _serialize_world_citizen(
    citizen: Citizen,
    city: Optional[City],
    neighborhood: Optional[Neighborhood],
    home: Optional[Building],
    venue: Optional[Building],
) -> dict:
    """
    Resolve one marker's position, then return only the fields the marker and
    its popup use.

    Position falls back gracefully: venue -> home -> district centre -> city
    centre -> world origin. A citizen created before the world was generated
    therefore still gets drawn (in their city centre) instead of vanishing.

    `marker_offset` scatters co-located citizens around a small circle so that
    a family sharing a house, or twenty workers in one factory, don't stack into
    a single dot. It's seeded from the citizen id, so a citizen's spot inside
    their house never changes between requests.
    """
    base = venue or home
    if base is not None:
        base_x = (city.world_x if city else 0.0) + base.offset_x
        base_z = (city.world_z if city else 0.0) + base.offset_z
    elif neighborhood is not None:
        base_x = (city.world_x if city else 0.0) + neighborhood.offset_x
        base_z = (city.world_z if city else 0.0) + neighborhood.offset_z
    elif city is not None:
        base_x = city.world_x
        base_z = city.world_z
    else:
        base_x = 0.0
        base_z = 0.0

    jitter_x, jitter_z = marker_offset(citizen.id)

    return {
        "id": citizen.id,
        "name": citizen.name,
        "age": citizen.age,
        "job": citizen.job,
        "current_activity": citizen.current_activity,
        "mood": citizen.mood,
        "happiness": citizen.happiness,
        "city_id": citizen.city_id,
        "city_name": city.name if city else None,
        "neighborhood_id": citizen.neighborhood_id,
        "neighborhood_name": neighborhood.name if neighborhood else None,
        "home_building_id": home.id if home else None,
        "marker_x": base_x + jitter_x,
        "marker_z": base_z + jitter_z,
        "at_work": venue is not None and citizen.current_activity in WORK_ACTIVITIES,
        # Wired up with the Government system — same single-point-of-change rule
        # as get_government_summary(). Never hardcoded to a name.
        "is_president": False,
        "is_first_lady": False,
    }


def list_world_citizens(
    db: Session,
    city_id: Optional[int] = None,
    limit: Optional[int] = DEFAULT_CITIZEN_LIMIT,
) -> tuple[list[dict], bool]:
    """
    Every citizen marker to draw, plus a flag saying whether the list was cut
    off by `limit`.

    Fixed query count regardless of population: citizens, cities, districts,
    buildings, homes. Nothing in here is per-citizen.
    """
    if city_id is not None and world_repo.get_city(db, city_id) is None:
        raise CityNotFound(f"City {city_id} not found")

    citizens = citizen_repo.list_all(db)
    citizens.sort(key=lambda c: c.id)
    if city_id is not None:
        citizens = [c for c in citizens if c.city_id == city_id]

    truncated = False
    if limit is not None and len(citizens) > limit:
        citizens = citizens[:limit]
        truncated = True

    cities = {city.id: city for city in world_repo.list_cities(db)}
    districts = {d.id: d for d in world_repo.list_neighborhoods(db)}
    homes = building_repo.map_homes_by_citizen(db)
    venue_index = _venue_index(building_repo.list_buildings(db, city_id=city_id))

    payload = []
    for citizen in citizens:
        home = homes.get(citizen.id)
        payload.append(
            _serialize_world_citizen(
                citizen,
                cities.get(citizen.city_id),
                districts.get(citizen.neighborhood_id),
                home,
                _pick_venue(citizen, venue_index),
            )
        )
    return payload, truncated


# ------------------------------------------------------------ government hook

def get_government_summary(db: Session) -> dict:
    """
    THE ONE PLACE to wire the Government/President/First Lady system into the
    3D map.

    Right now this codebase has no government models (no president / first
    lady / parliament / marriage tables exist yet), so this returns
    `system_available: False` plus the location of the presidential district,
    which IS already known from the world data. The map can render the
    Presidential District correctly today and simply hide the
    president/first-lady labels until the system lands.

    WHEN THE GOVERNMENT SYSTEM IS FINISHED, edit only this function:
        from app.repositories import government_repo
        gov = government_repo.get_current_government(db)
        ...populate president_name / first_lady_name / tax_rate / curfew...
        payload["system_available"] = True

    Because names are read from the DB here and never cached or hardcoded,
    renaming the President from "Tonmoy" to "Alex" changes the map label with
    zero frontend changes — which is the requirement.
    """
    capital = world_repo.get_capital(db)
    presidential_district = None
    if capital is not None:
        presidential_district = world_repo.get_neighborhood_by_type(
            db, capital.id, DISTRICT_PRESIDENTIAL
        )

    return {
        "president_name": None,
        "first_lady_name": None,
        "capital_city_id": capital.id if capital else None,
        "capital_city_name": capital.name if capital else None,
        "presidential_neighborhood_id": presidential_district.id if presidential_district else None,
        "presidential_neighborhood_name": presidential_district.name if presidential_district else None,
        "tax_rate": None,
        "curfew_enabled": None,
        "system_available": False,
    }


# -------------------------------------------------------------- world summary

def get_simulation_summary(db: Session) -> dict:
    """Reuses the existing dashboard + tick layers rather than re-querying —
    one definition of "average happiness" for the whole app.

    Public (not underscore-prefixed) because the map polls this on its own via
    GET /world/simulation to refresh its header between ticks. Re-fetching the
    whole overview for six numbers would re-send every building and road.
    """
    stats = dashboard_service.get_stats(db)

    recent = simulation_tick_repo.list_recent(db, limit=1)
    tick_number = recent[0].tick_number if recent else 0

    # The newest timeline event, reusing the existing paginated repo (it orders
    # by id desc, so page 0 / size 1 is the latest). The milestone detectors
    # already write these rows — the map just displays the most recent one.
    latest_events, _total = timeline_repo.list_paginated(db, 0, 1)
    current_event = latest_events[0].title if latest_events else None

    return {
        "tick_number": tick_number,
        "day": (tick_number // TICKS_PER_DAY) + 1,
        "population": stats["population"],
        "city_count": world_repo.count_cities(db),
        "neighborhood_count": world_repo.count_neighborhoods(db),
        "average_happiness": stats["average_happiness"],
        "current_event": current_event,
    }


def get_world_overview(
    db: Session,
    city_id: Optional[int] = None,
    include_citizens: bool = True,
    citizen_limit: Optional[int] = DEFAULT_CITIZEN_LIMIT,
) -> dict:
    """
    GET /api/v1/world — everything the frontend needs to build the world in one
    round trip: cities, districts, buildings, roads, citizen markers, the
    government summary and live simulation stats.

    Bounded on purpose (§14, §19). The building and road lists are fixed-size
    for a given world, but the citizen list grows with the population, so:
      * `city_id`          -> restrict the whole payload to one city
      * `include_citizens` -> drop the markers entirely (terrain-only load)
      * `citizen_limit`    -> cap the markers, with `citizens_truncated` set

    `world_generated` is False when no buildings exist, which lets the map show
    a "generate the world" hint instead of an empty green plane.
    """
    if city_id is not None and world_repo.get_city(db, city_id) is None:
        raise CityNotFound(f"City {city_id} not found")

    cities = list_cities(db)
    if city_id is not None:
        cities = [city for city in cities if city["id"] == city_id]
    neighborhoods = list_neighborhoods(db, city_id=city_id)

    citizens: list[dict] = []
    citizens_truncated = False
    if include_citizens:
        citizens, citizens_truncated = list_world_citizens(
            db, city_id=city_id, limit=citizen_limit
        )

    return {
        "cities": cities,
        "neighborhoods": neighborhoods,
        "buildings": list_buildings(db, city_id=city_id),
        "roads": list_roads(db, city_id=city_id),
        "citizens": citizens,
        "government": get_government_summary(db),
        "simulation": get_simulation_summary(db),
        "unassigned_citizens": world_repo.count_unassigned_citizens(db),
        "citizens_truncated": citizens_truncated,
        "world_generated": building_repo.count_buildings(db) > 0,
    }


# --------------------------------------------------------------- admin writes

def update_city(
    db: Session,
    city_id: int,
    name: Optional[str] = None,
    region: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Admin/President rename. Guards the unique constraint with a friendly
    409 instead of leaking a raw IntegrityError."""
    city = world_repo.get_city(db, city_id)
    if city is None:
        raise CityNotFound(f"City {city_id} not found")

    if name is not None and name != city.name:
        existing = world_repo.get_city_by_name(db, name)
        if existing is not None and existing.id != city.id:
            raise DuplicateCityName(f"A city named '{name}' already exists")

    city = world_repo.update_city(db, city, name=name, region=region, description=description)

    districts = world_repo.list_neighborhoods(db, city_id=city.id)
    populations = world_repo.count_citizens_by_city(db)
    return _serialize_city(city, populations.get(city.id, 0), len(districts))


def update_neighborhood(
    db: Session,
    neighborhood_id: int,
    name: Optional[str] = None,
    type: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    neighborhood = world_repo.get_neighborhood(db, neighborhood_id)
    if neighborhood is None:
        raise NeighborhoodNotFound(f"Neighborhood {neighborhood_id} not found")

    if name is not None and name != neighborhood.name:
        existing = world_repo.get_neighborhood_by_name(db, neighborhood.city_id, name)
        if existing is not None and existing.id != neighborhood.id:
            raise DuplicateNeighborhoodName(
                f"A district named '{name}' already exists in this city"
            )

    neighborhood = world_repo.update_neighborhood(
        db, neighborhood, name=name, type=type, description=description
    )

    city = world_repo.get_city(db, neighborhood.city_id)
    populations = world_repo.count_citizens_by_neighborhood(db)
    return _serialize_neighborhood(neighborhood, city, populations.get(neighborhood.id, 0))
