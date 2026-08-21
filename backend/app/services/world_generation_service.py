"""
World generation (World Phase 2).

Turns the authored world (cities + districts, from World Phase 1) into the
concrete geometry the 3D map renders: every building, every road, and the link
from each citizen to a city, a district and a house.

--------------------------------------------------------------------------
WHY THIS IS A SEPARATE SERVICE FROM world_service.py
--------------------------------------------------------------------------
world_service.py is the READ path — it answers "what does the world look like
right now" and is hit on every map load. This module is the WRITE path: it runs
rarely (first boot, an admin regeneration, or when a new citizen needs a home)
and it is the only thing in the app allowed to create buildings and roads.
Keeping them apart means a bug in generation can't be triggered by someone
merely viewing the map.

--------------------------------------------------------------------------
IDEMPOTENCE AND SAFETY
--------------------------------------------------------------------------
* `ensure_world_generated()` is a no-op the moment any building exists, exactly
  like world_service.ensure_seed_world and simulation.seed_shops. That is what
  makes it safe to call on every startup.
* Regeneration requires `force=True` from an admin endpoint, and only ever
  deletes rows in `buildings` / `roads` — never a city, a district, a citizen,
  a shop, a wallet or a post.
* Everything happens in ONE transaction with a single commit, so a failure
  halfway through can't leave half a city standing.
* Because placement is deterministic (see simulation/world_generator.py), a
  forced regeneration puts every house back exactly where it was.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.citizen import Citizen
from app.repositories import building_repo, citizen_repo, shop_repo, world_repo
from app.simulation.building_types import (
    BUILDING_HOUSE,
    BUILDING_SHOP,
    spec_for,
)
from app.simulation.world_generator import (
    HOUSING_DISTRICT_TYPES,
    distribute_citizens,
    grid_slots,
    house_footprint_for,
    housing_capacity,
    plan_city_roads,
    plan_district_buildings,
    plan_highways,
    stable_rng,
)
from app.simulation.world_layout import DISTRICT_COMMERCIAL

# NOTE: which building types count as a workplace is NOT defined here — it lives
# in simulation/building_types.VENUE_TYPES_BY_ACTIVITY, keyed by the same
# `current_activity` strings the tick engine already writes. Keeping one copy
# means the read path (world_service) and this generator can never disagree
# about where a working citizen should be standing.


def _city_to_dict(city) -> dict:
    return {
        "id": city.id,
        "name": city.name,
        "world_x": city.world_x,
        "world_z": city.world_z,
        "radius": city.radius,
        "is_capital": city.is_capital,
    }


def _district_to_dict(district) -> dict:
    return {
        "id": district.id,
        "city_id": district.city_id,
        "name": district.name,
        "type": district.type,
        "offset_x": district.offset_x,
        "offset_z": district.offset_z,
        "width": district.width,
        "depth": district.depth,
    }


# --------------------------------------------------------------- entry points

def ensure_world_generated(db: Session) -> dict:
    """
    Generate the world's geometry if it hasn't been generated yet.

    Called from the app lifespan on every boot; a single `count_buildings`
    check makes it free after the first run.
    """
    if building_repo.count_buildings(db) > 0:
        return {
            "created_buildings": 0,
            "created_roads": 0,
            "assigned_citizens": 0,
            "housed_citizens": 0,
            "deleted_buildings": 0,
            "deleted_roads": 0,
            "detail": "World geometry already generated — skipped (existing data is the source of truth).",
        }
    return generate_world(db, force=False)


def generate_world(db: Session, force: bool = False) -> dict:
    """
    Build every building and road, and place every citizen.

    `force=True` wipes the existing geometry first and rebuilds it. Because
    generation is deterministic, that is a safe repair operation: buildings
    land back in the same coordinates. It is still admin-gated, because it
    resets which house a citizen owns if the population changed.
    """
    deleted_buildings = 0
    deleted_roads = 0

    if building_repo.count_buildings(db) > 0 or building_repo.count_roads(db) > 0:
        if not force:
            return {
                "created_buildings": 0,
                "created_roads": 0,
                "assigned_citizens": 0,
                "housed_citizens": 0,
                "deleted_buildings": 0,
                "deleted_roads": 0,
                "detail": "World geometry already exists. Pass force=true to rebuild it.",
            }
        # commit=False: the wipe and the rebuild share one transaction, so a
        # failure mid-rebuild rolls the deletion back too.
        deleted_buildings = building_repo.delete_all_buildings(db, commit=False)
        deleted_roads = building_repo.delete_all_roads(db, commit=False)

    cities = world_repo.list_cities(db)
    if not cities:
        return {
            "created_buildings": 0,
            "created_roads": 0,
            "assigned_citizens": 0,
            "housed_citizens": 0,
            "deleted_buildings": deleted_buildings,
            "deleted_roads": deleted_roads,
            "detail": "No cities exist yet — seed the world first (POST /api/v1/world/seed).",
        }

    districts = world_repo.list_neighborhoods(db)
    districts_by_city: dict[int, list] = {}
    for district in districts:
        districts_by_city.setdefault(district.city_id, []).append(district)

    # ---- 1. place citizens into housing districts ----
    housing_districts = [d for d in districts if d.type in HOUSING_DISTRICT_TYPES]
    citizens = citizen_repo.list_all(db)
    assignment = distribute_citizens(
        [c.id for c in citizens], [d.id for d in housing_districts]
    )

    district_by_id = {d.id: d for d in districts}
    citizens_by_district: dict[int, list[Citizen]] = {}
    assigned_citizens = 0

    for citizen in sorted(citizens, key=lambda c: c.id):
        district_id = assignment.get(citizen.id)
        if district_id is None:
            continue
        district = district_by_id[district_id]
        citizen.city_id = district.city_id
        citizen.neighborhood_id = district.id
        citizens_by_district.setdefault(district.id, []).append(citizen)
        assigned_citizens += 1

    # ---- 2. shops get a real building to trade from ----
    # Shops are distributed round-robin across every commercial district so no
    # city ends up with all the commerce. Sorted by id => deterministic.
    shops = sorted(shop_repo.list_shops(db), key=lambda s: s.id)
    commercial_districts = sorted(
        [d for d in districts if d.type == DISTRICT_COMMERCIAL], key=lambda d: d.id
    )
    shops_by_district: dict[int, list] = {d.id: [] for d in commercial_districts}
    if commercial_districts:
        for i, shop in enumerate(shops):
            target = commercial_districts[i % len(commercial_districts)]
            shops_by_district[target.id].append(shop)

    # ---- 3. buildings ----
    created_buildings = 0
    housed_citizens = 0

    for city in cities:
        for district in districts_by_city.get(city.id, []):
            residents = citizens_by_district.get(district.id, [])
            district_shops = shops_by_district.get(district.id, [])

            blueprints = plan_district_buildings(
                _district_to_dict(district),
                city_id=city.id,
                house_count=len(residents),
                shop_names=[s.name for s in district_shops],
            )

            resident_cursor = 0
            shop_cursor = 0

            for blueprint in blueprints:
                owner_citizen_id = None
                shop_id = None
                name = blueprint["name"]

                if blueprint["type"] == BUILDING_HOUSE and resident_cursor < len(residents):
                    owner = residents[resident_cursor]
                    owner_citizen_id = owner.id
                    resident_cursor += 1
                    housed_citizens += 1
                    # name stays NULL on purpose — the map labels a house with
                    # its owner's CURRENT name, read live from `citizens`, so a
                    # citizen rename never leaves a stale label behind.

                elif blueprint["type"] == BUILDING_SHOP and shop_cursor < len(district_shops):
                    shop = district_shops[shop_cursor]
                    shop_id = shop.id
                    name = shop.name
                    shop_cursor += 1

                building_repo.create_building(
                    db,
                    city_id=city.id,
                    neighborhood_id=district.id,
                    type=blueprint["type"],
                    name=name,
                    owner_citizen_id=owner_citizen_id,
                    shop_id=shop_id,
                    offset_x=blueprint["offset_x"],
                    offset_z=blueprint["offset_z"],
                    width=blueprint["width"],
                    depth=blueprint["depth"],
                    height=blueprint["height"],
                    rotation=blueprint["rotation"],
                    is_landmark=blueprint["is_landmark"],
                    commit=False,
                )
                created_buildings += 1

    # ---- 4. roads ----
    created_roads = 0

    for city in cities:
        city_districts = [
            _district_to_dict(d) for d in districts_by_city.get(city.id, [])
        ]
        for road in plan_city_roads(_city_to_dict(city), city_districts):
            building_repo.create_road(
                db,
                city_id=city.id,
                name=road["name"],
                kind=road["kind"],
                start_x=road["start_x"],
                start_z=road["start_z"],
                end_x=road["end_x"],
                end_z=road["end_z"],
                width=road["width"],
                commit=False,
            )
            created_roads += 1

    for road in plan_highways([_city_to_dict(c) for c in cities]):
        building_repo.create_road(
            db,
            city_id=None,  # a highway belongs to no single city
            name=road["name"],
            kind=road["kind"],
            start_x=road["start_x"],
            start_z=road["start_z"],
            end_x=road["end_x"],
            end_z=road["end_z"],
            width=road["width"],
            commit=False,
        )
        created_roads += 1

    db.commit()

    return {
        "created_buildings": created_buildings,
        "created_roads": created_roads,
        "assigned_citizens": assigned_citizens,
        "housed_citizens": housed_citizens,
        "deleted_buildings": deleted_buildings,
        "deleted_roads": deleted_roads,
        "detail": (
            f"Generated {created_buildings} buildings and {created_roads} roads; "
            f"placed {assigned_citizens} citizens ({housed_citizens} with a house)."
        ),
    }


# --------------------------------------------------- incremental placement

def assign_citizen_to_world(db: Session, citizen: Citizen) -> Optional[int]:
    """
    Give a single, newly created citizen a city, a district and a house.

    Called after citizen creation so a citizen added at runtime appears on the
    map immediately instead of waiting for a full regeneration. Deliberately
    cheap and total-failure-tolerant:

      * picks the housing district with the fewest residents (ties broken by
        lowest id, so it stays deterministic)
      * reuses an existing empty house if there is one, otherwise builds a new
        house on the edge of the district
      * returns None and changes nothing if the world hasn't been generated yet

    The CALLER is responsible for swallowing exceptions — see
    citizen_service.create_citizen. Placement must never be able to stop a
    citizen from being created.
    """
    districts = [d for d in world_repo.list_neighborhoods(db) if d.type in HOUSING_DISTRICT_TYPES]
    if not districts:
        return None

    populations = world_repo.count_citizens_by_neighborhood(db)
    target = min(districts, key=lambda d: (populations.get(d.id, 0), d.id))

    citizen.city_id = target.city_id
    citizen.neighborhood_id = target.id

    vacant = building_repo.list_unowned_houses(db, target.id)
    if vacant:
        building = vacant[0]
        building.owner_citizen_id = citizen.id
        db.commit()
        return building.id

    # No empty house — extend the district by one. Re-planning the whole
    # district for one person would move everyone else's house, which the spec
    # forbids, so the new house is appended at the next slot in the SAME
    # deterministic grid the generator used (same rng_key, same footprint
    # helper, capacity rounded the same coarse way).
    existing = building_repo.list_buildings(
        db, neighborhood_id=target.id, types=[BUILDING_HOUSE]
    )
    wanted = housing_capacity(len(existing) + 1)

    slots = grid_slots(
        target.width, target.depth, wanted, house_footprint_for(target.type),
        rng_key=f"district-{target.city_id}-{target.id}",
    )
    if len(slots) <= len(existing):
        # District is genuinely full. The citizen still belongs to it (marker
        # renders at the district centre) — they just have no house yet.
        db.commit()
        return None

    slot_x, slot_z = slots[-1]
    rng = stable_rng("house", target.city_id, target.id, len(slots) - 1)
    spec = spec_for(BUILDING_HOUSE)
    wobble = rng.uniform(0.88, 1.14)

    building = building_repo.create_building(
        db,
        city_id=target.city_id,
        neighborhood_id=target.id,
        type=BUILDING_HOUSE,
        owner_citizen_id=citizen.id,
        offset_x=target.offset_x + slot_x,
        offset_z=target.offset_z + slot_z,
        width=round(spec["width"] * wobble, 3),
        depth=round(spec["depth"] * wobble, 3),
        height=round(spec["height"] * rng.uniform(0.82, 1.26), 3),
        rotation=round(rng.uniform(-0.09, 0.09), 4),
        is_landmark=False,
        commit=True,
    )
    return building.id
