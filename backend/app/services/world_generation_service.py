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
* `ensure_world_generated()` is a no-op the moment any GENERATED building exists,
  exactly like world_service.ensure_seed_world and simulation.seed_shops. That is
  what makes it safe to call on every startup.
* Regeneration requires `force=True` from an admin endpoint, and only ever
  deletes rows in `buildings` / `roads` — never a city, a district, a citizen,
  a shop, a wallet or a post.
* Everything happens in ONE transaction with a single commit, so a failure
  halfway through can't leave half a city standing.
* Because placement is deterministic (see simulation/world_generator.py), a
  forced regeneration puts every house back exactly where it was.

--------------------------------------------------------------------------
HAND-PLACED BUILDINGS ARE NOT REGENERATED DATA
--------------------------------------------------------------------------
Everything above assumes `buildings` is derived output that can be recomputed.
A building an admin placed through the map's build mode cannot be: no generator
input describes it. Those rows carry `is_manual = True` and get three exemptions:

  1. the forced delete skips them (`delete_generated_buildings`),
  2. the planner is told to treat them as occupied ground, so nothing is rebuilt
     on top of one (`plan_district_buildings(reserved=...)`),
  3. "has the world been generated?" counts generated rows only, so an admin
     placing a school on a freshly seeded world does not make startup believe the
     world is already built.

Everything else about them — how they render, how a citizen's marker finds a
workplace in one, how the info panel describes them — is identical to a generated
building. `is_manual` records who authored the row, nothing more.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.citizen import Citizen
from app.repositories import building_repo, citizen_repo, shop_repo, world_repo
from app.simulation.building_types import (
    BUILDING_HOUSE,
    BUILDING_SHOP,
)
from app.simulation.world_generator import (
    HOUSING_DISTRICT_TYPES,
    collides,
    distribute_citizens,
    grid_slots,
    house_blueprint,
    house_footprint_for,
    housing_capacity,
    plan_city_roads,
    plan_district_buildings,
    plan_highways,
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

    Called from the app lifespan on every boot; a single
    `count_generated_buildings` check makes it free after the first run.
    """
    if building_repo.count_generated_buildings(db) > 0:
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

    # `count_generated_buildings`, not `count_buildings`: a world where an admin
    # has hand-placed one school has NOT been generated, and counting their
    # building here would refuse to ever lay out the roads and houses.
    if building_repo.count_generated_buildings(db) > 0 or building_repo.count_roads(db) > 0:
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
        #
        # GENERATED ONLY. Hand-placed buildings (`is_manual`) are left standing and
        # are fed back into the planner below as ground that is already taken. An
        # admin's school is not recomputable from any generator input, so deleting
        # it would destroy work that nothing could restore.
        deleted_buildings = building_repo.delete_generated_buildings(db, commit=False)
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

    # THE DEAD ARE INCLUDED HERE ON PURPOSE — the one place in the codebase that
    # wants `include_dead=True`. Two reasons, and the first is the important one:
    #
    #   1. DETERMINISM. `distribute_citizens` allocates by position in the id list,
    #      so dropping one citizen shifts every later citizen into a different
    #      district. If the dead were excluded, a single death would silently
    #      relocate the houses of everyone created after them on the next forced
    #      regeneration — breaking this module's headline promise that regeneration
    #      "puts every house back exactly where it was".
    #   2. A dead citizen's house should keep standing and keep their name on it
    #      (see `_owner_names` in world_service.py). Excluding them here would
    #      demolish it.
    #
    # Nothing bad follows from it: the deceased get no MARKER on the map, because
    # markers come from `list_world_citizens`, which is living-only, and they get
    # no turns, because the tick engine filters separately. They just keep a house.
    citizens = citizen_repo.list_all(db, include_dead=True)
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

    # What survived the delete: the hand-placed buildings. Read AFTER the delete so
    # the list is exactly "what is still standing", and grouped by district because
    # that is the granularity the planner works at. City-land manual buildings
    # (neighborhood_id NULL) are not planned around — nothing is generated out
    # there, so there is nothing to collide with.
    manual_buildings = building_repo.list_manual_buildings(db)
    manual_by_district: dict[int, list] = {}
    for building in manual_buildings:
        if building.neighborhood_id is not None:
            manual_by_district.setdefault(building.neighborhood_id, []).append(building)

    # A citizen who still owns a surviving building already has a home, so they
    # must be skipped when owners are handed out below — otherwise they would end
    # up owning two houses and `get_home_for_citizen` would silently pick one.
    already_housed = {
        b.owner_citizen_id for b in manual_buildings if b.owner_citizen_id is not None
    }

    # Counted up front rather than starting at zero, because the loop below
    # deliberately skips these citizens and would otherwise report someone living
    # in a hand-placed house as homeless.
    housed_citizens = len(already_housed)

    for city in cities:
        for district in districts_by_city.get(city.id, []):
            reserved = manual_by_district.get(district.id, [])

            # Order-preserving filter, so the citizens who remain keep their
            # relative positions and therefore their deterministic house slots.
            residents = [
                c
                for c in citizens_by_district.get(district.id, [])
                if c.id not in already_housed
            ]
            district_shops = shops_by_district.get(district.id, [])

            blueprints = plan_district_buildings(
                _district_to_dict(district),
                city_id=city.id,
                house_count=len(residents),
                shop_names=[s.name for s in district_shops],
                reserved=reserved,
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

    NOBODY INHERITS A HOUSE. `count_citizens_by_neighborhood` counts the living,
    so a district whose residents have died reads as sparse and gets picked first —
    but `list_unowned_houses` only returns houses with `owner_citizen_id IS NULL`,
    and a deceased citizen still owns theirs. So the new arrival gets a NEW house
    appended to the district grid rather than moving into a dead person's home.
    That is intentional: there is no inheritance system here, matching the same
    decision made for wallets in dashboard_service.get_stats.
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
    # forbids, so the new house is appended at the next FREE slot in the SAME
    # deterministic grid the generator used (same rng_key, same footprint
    # helper, capacity rounded the same coarse way).
    houses = building_repo.list_buildings(
        db, neighborhood_id=target.id, types=[BUILDING_HOUSE]
    )
    wanted = housing_capacity(len(houses) + 1)

    slots = grid_slots(
        target.width, target.depth, wanted, house_footprint_for(target.type),
        rng_key=f"district-{target.city_id}-{target.id}",
    )

    # Every building in the district, not just the houses — a school or a police
    # station occupies real ground and a new house must not be dropped on top of
    # one (see world_generator.plan_civic_buildings).
    occupied = building_repo.list_buildings(db, neighborhood_id=target.id)

    # FIRST FREE SLOT, not the last slot.
    #
    # This used to take `slots[-1]`, which was wrong in a way that only showed up
    # past a capacity boundary: `housing_capacity` rounds up to a multiple of 8, so
    # a district with 9 houses and a district with 10 both ask for a 16-slot grid
    # and both got handed slot 15 — the second house landed exactly on top of the
    # first. Searching for a free slot fixes that and, in the same stroke, keeps
    # houses off the civic buildings.
    blueprint = None
    for index, (slot_x, slot_z) in enumerate(slots):
        candidate = house_blueprint(
            target.city_id, target.id, index,
            target.offset_x, target.offset_z, slot_x, slot_z,
        )
        if collides(candidate, occupied):
            continue
        blueprint = candidate
        break

    if blueprint is None:
        # District is genuinely full. The citizen still belongs to it (marker
        # renders at the district centre) — they just have no house yet.
        db.commit()
        return None

    building = building_repo.create_building(
        db,
        city_id=target.city_id,
        neighborhood_id=target.id,
        type=BUILDING_HOUSE,
        owner_citizen_id=citizen.id,
        offset_x=blueprint["offset_x"],
        offset_z=blueprint["offset_z"],
        width=blueprint["width"],
        depth=blueprint["depth"],
        height=blueprint["height"],
        rotation=blueprint["rotation"],
        is_landmark=False,
        commit=True,
    )
    return building.id
