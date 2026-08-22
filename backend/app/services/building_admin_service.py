"""
Admin building placement — create / move / demolish one building by hand.

WHY THIS IS ITS OWN SERVICE
---------------------------
The project already splits the world into a read service (world_service.py) and a
generation service (world_generation_service.py), for the stated reason that "a
bug in generation can't be triggered by someone merely viewing the map". Hand
placement is a third thing again: it is a single-row write, driven by a human
clicking on a map, and its whole job is VALIDATION — does this fit, is it inside
the district, is something already there. None of that belongs in the read path,
and it is not generation either: it makes exactly one building and never touches
roads or citizen assignment.

WHAT THIS GUARANTEES
--------------------
Every building it writes carries `is_manual = True`, which is what makes it
survive `POST /api/v1/world/generate?force=true` (see
world_generation_service.py). Anything it EDITS is promoted to `is_manual = True`
as well — "you moved it, so you own it". Without that promotion, dragging a
generated house two units to the left would look like it worked and then silently
snap back on the next regeneration, which is the worst of both behaviours.

GEOMETRY LIVES IN ONE PLACE
---------------------------
The overlap and bounds predicates are imported from
simulation/world_generator.py, the same functions the generator's civic pass uses.
That is deliberate: if "does it fit?" meant one thing to the generator and another
thing to this endpoint, an admin could place a building in a gap the next
regeneration would then build a house into.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.city import City
from app.models.neighborhood import Neighborhood
from app.repositories import building_repo, world_repo
from app.schemas.world import BuildingCreate, BuildingUpdate
from app.services import world_service
from app.services.world_service import (
    BuildingNotFound,
    CityNotFound,
    NeighborhoodNotFound,
    WorldError,
)
from app.simulation.building_types import spec_for
from app.simulation.world_generator import first_collision, within_district

# How far inside a district's edge a hand-placed building must stay.
#
# Much smaller than the generator's DISTRICT_MARGIN (9.0) and smaller than
# CIVIC_MARGIN (4.0) on purpose: those are aesthetic choices about where the
# generator prefers to build, while this is a correctness floor. An admin who
# wants a building tucked right against the boundary has said so by clicking
# there, and the only thing worth refusing is a footprint that hangs off the
# district's ground plate entirely.
PLACEMENT_MARGIN = 0.5


class BuildingPlacementError(WorldError):
    """The request was well-formed but the building can't go there — it overlaps
    something, it hangs outside its district, or the change isn't allowed for this
    particular building. Mapped to 409 by the API layer, not 422: nothing about the
    payload's *shape* is wrong."""


# --------------------------------------------------------------- resolution

def _resolve_place(
    db: Session,
    city_id: Optional[int],
    neighborhood_id: Optional[int],
) -> tuple[City, Optional[Neighborhood]]:
    """Turn "which city / which district" into the real rows, or raise.

    A district implies its city, so `city_id` is optional whenever
    `neighborhood_id` is given — which is the normal case for a map click, since
    the click lands on a district plate. When both are given they must agree; a
    request that names a district in city 2 and a city of 1 is a client bug and
    guessing which one it meant would put the building somewhere nobody asked for.
    """
    district: Optional[Neighborhood] = None

    if neighborhood_id is not None:
        district = world_repo.get_neighborhood(db, neighborhood_id)
        if district is None:
            raise NeighborhoodNotFound(f"Neighborhood {neighborhood_id} not found")
        if city_id is not None and city_id != district.city_id:
            raise BuildingPlacementError(
                f"Neighborhood {district.id} belongs to city {district.city_id}, "
                f"not city {city_id}."
            )
        city_id = district.city_id

    city = world_repo.get_city(db, city_id) if city_id is not None else None
    if city is None:
        raise CityNotFound(f"City {city_id} not found")

    return city, district


def _offsets_from_payload(
    payload,
    city: City,
    current_x: Optional[float] = None,
    current_z: Optional[float] = None,
) -> tuple[float, float]:
    """The city-relative offsets a request asks for.

    Three cases, and the schema's validator has already guaranteed they are the
    only three (see `_BuildingGeometryMixin._positions_are_not_mixed`):
      * `offset_x`/`offset_z` given  -> used as-is
      * `world_x`/`world_z` given    -> converted by subtracting the city centre,
        which is the inverse of what `world_service._serialize_building` does when
        it reports absolute coordinates. A map click is absolute, so this is the
        path the build mode actually uses.
      * neither given (PATCH only)   -> keep what the building already has
    """
    if payload.offset_x is not None and payload.offset_z is not None:
        return float(payload.offset_x), float(payload.offset_z)

    if payload.world_x is not None and payload.world_z is not None:
        return (
            float(payload.world_x) - city.world_x,
            float(payload.world_z) - city.world_z,
        )

    # PATCH with no position change. `current_*` is always supplied in that path.
    return float(current_x or 0.0), float(current_z or 0.0)


# --------------------------------------------------------------- validation

def _check_fits(
    db: Session,
    candidate: dict,
    city: City,
    district: Optional[Neighborhood],
    exclude_building_id: Optional[int] = None,
    allow_overlap: bool = False,
) -> None:
    """Raise BuildingPlacementError unless `candidate` can stand where it says.

    `candidate` is a dict with city-relative `offset_x`/`offset_z` plus
    `width`/`depth` — the same shape the generator's blueprints use, which is why
    the imported predicates accept it unchanged.

    TWO CHECKS, AND ONLY THE SECOND CAN BE WAIVED
    ---------------------------------------------
    District bounds are not negotiable: a building hanging off the edge of its
    district's ground plate is a rendering artefact, not a design decision, and the
    district is also what `plan_district_buildings` uses to decide what to
    regenerate. Overlap, by contrast, is a matter of taste often enough that
    `allow_overlap` exists — a market stall abutting a shop is a legitimate thing
    to want, and an admin who has clicked twice knows what they are doing.

    ROTATION IS IGNORED, as it is throughout the overlap geometry. Hand-placed
    rotations can be anything, so the axis-aligned test is no longer strictly
    conservative for a 45-degree building. That is accepted: the failure mode is a
    placement being allowed that visually clips by a unit or two, and the
    alternative — a full separating-axis test — is a lot of machinery for a
    stylized low-poly map an admin is looking at from above and can simply nudge.
    """
    if district is not None:
        # `within_district` works in DISTRICT-relative coordinates, so the
        # district's own offset comes out first.
        relative = {
            "offset_x": candidate["offset_x"] - district.offset_x,
            "offset_z": candidate["offset_z"] - district.offset_z,
            "width": candidate["width"],
            "depth": candidate["depth"],
        }
        if not within_district(
            relative, district.width, district.depth, margin=PLACEMENT_MARGIN
        ):
            raise BuildingPlacementError(
                f"A {candidate['width']:g}x{candidate['depth']:g} building at that "
                f"position does not fit inside {district.name} "
                f"({district.width:g}x{district.depth:g}). Move it toward the "
                f"district centre, make it smaller, or place it on city land by "
                f"sending neighborhood_id: null."
            )

    if allow_overlap:
        return

    # Same city only. Districts never overlap and cities are far apart, so a
    # building in another city cannot possibly be in the way — and scanning one
    # city keeps this cheap on a large world.
    others = [
        b
        for b in building_repo.list_buildings(db, city_id=city.id)
        if b.id != exclude_building_id
    ]
    hit = first_collision(candidate, others)
    if hit is not None:
        label = hit.name or spec_for(hit.type)["label"]
        raise BuildingPlacementError(
            f"That position overlaps building {hit.id} ({label}). Move it, or "
            f"resend with allow_overlap=true if the two are meant to touch."
        )


# ------------------------------------------------------------------ writes

def create_building(
    db: Session, payload: BuildingCreate, allow_overlap: bool = False
) -> dict:
    """Place one building by hand. Returns it in the same shape GET
    /api/v1/world/buildings/{id} does, so the map can drop the result straight
    into its scene without a second request.

    Size, height and `is_landmark` fall back to the type's spec, which is how the
    build mode can place a school from a type and a click alone — and means a
    hand-placed school is exactly the size a generated one would have been.
    """
    city, district = _resolve_place(db, payload.city_id, payload.neighborhood_id)
    offset_x, offset_z = _offsets_from_payload(payload, city)

    spec = spec_for(payload.type)
    candidate = {
        "offset_x": offset_x,
        "offset_z": offset_z,
        "width": float(payload.width if payload.width is not None else spec["width"]),
        "depth": float(payload.depth if payload.depth is not None else spec["depth"]),
    }

    _check_fits(db, candidate, city, district, allow_overlap=allow_overlap)

    building = building_repo.create_building(
        db,
        city_id=city.id,
        neighborhood_id=district.id if district is not None else None,
        type=payload.type,
        name=payload.name,
        offset_x=candidate["offset_x"],
        offset_z=candidate["offset_z"],
        width=candidate["width"],
        depth=candidate["depth"],
        height=float(payload.height if payload.height is not None else spec["height"]),
        rotation=float(payload.rotation or 0.0),
        is_landmark=(
            spec["is_landmark"] if payload.is_landmark is None else payload.is_landmark
        ),
        # THE POINT OF THE WHOLE FEATURE. Without this the next forced
        # regeneration deletes it.
        is_manual=True,
        commit=True,
    )
    return world_service.get_building_detail(db, building.id)


def update_building(
    db: Session,
    building_id: int,
    payload: BuildingUpdate,
    allow_overlap: bool = False,
) -> dict:
    """Move / resize / rename / retype / re-district one building.

    `exclude_unset` IS LOAD-BEARING. It is what separates "the client didn't
    mention name" from "the client sent name: null and wants it cleared", and the
    same for `neighborhood_id`, where null legitimately means "move this out onto
    city land". Replacing it with a plain `model_dump()` would blank every field
    the request didn't mention.
    """
    building = building_repo.get_building(db, building_id)
    if building is None:
        raise BuildingNotFound(f"Building {building_id} not found")

    sent = payload.model_dump(exclude_unset=True)
    if not sent:
        # Nothing to do. Returning the building rather than erroring keeps a
        # double-click in the editor harmless.
        return world_service.get_building_detail(db, building.id)

    city = world_repo.get_city(db, building.city_id)
    if city is None:
        # The FK is NOT NULL with ON DELETE CASCADE, so this is unreachable
        # through normal use — it means the row was orphaned by direct SQL.
        raise CityNotFound(f"City {building.city_id} not found")

    # ---- which district, after the change ----
    #
    # `city_id` is intentionally not editable (see BuildingUpdate), so a new
    # district must belong to the city the building is already in. Otherwise the
    # offsets, which are relative to the city centre, would place it hundreds of
    # units outside its own district.
    if "neighborhood_id" in sent:
        district: Optional[Neighborhood] = None
        if sent["neighborhood_id"] is not None:
            district = world_repo.get_neighborhood(db, sent["neighborhood_id"])
            if district is None:
                raise NeighborhoodNotFound(
                    f"Neighborhood {sent['neighborhood_id']} not found"
                )
            if district.city_id != building.city_id:
                raise BuildingPlacementError(
                    f"Neighborhood {district.id} is in city {district.city_id}; "
                    f"building {building.id} is in city {building.city_id}. A "
                    f"building cannot change city — demolish it and place a new one."
                )
    elif building.neighborhood_id is not None:
        district = world_repo.get_neighborhood(db, building.neighborhood_id)
    else:
        district = None

    # ---- retyping ----
    new_type = sent.get("type") or building.type
    if new_type != building.type:
        if building.owner_citizen_id is not None:
            raise BuildingPlacementError(
                f"Building {building.id} is somebody's house. Changing its type "
                f"would leave a citizen living in a factory — demolish it instead, "
                f"or clear the owner first."
            )
        if building.shop_id is not None:
            raise BuildingPlacementError(
                f"Building {building.id} is a shop's premises. Changing its type "
                f"would leave the shop trading from nowhere."
            )

    # ---- geometry, merging what was sent over what is already stored ----
    offset_x, offset_z = _offsets_from_payload(
        payload, city, current_x=building.offset_x, current_z=building.offset_z
    )
    candidate = {
        "offset_x": offset_x,
        "offset_z": offset_z,
        "width": float(sent.get("width") or building.width),
        "depth": float(sent.get("depth") or building.depth),
    }

    _check_fits(
        db,
        candidate,
        city,
        district,
        exclude_building_id=building.id,
        allow_overlap=allow_overlap,
    )

    # ---- the actual write ----
    #
    # Built explicitly rather than by passing `sent` through, because `sent` may
    # contain `world_x`/`world_z`, which are request spellings and not columns.
    fields: dict = {
        "offset_x": candidate["offset_x"],
        "offset_z": candidate["offset_z"],
        "width": candidate["width"],
        "depth": candidate["depth"],
        # PROMOTED TO HAND-PLACED. An edit is authorship: the position an admin
        # chose is not derivable from any generator input, so without this flag the
        # next regeneration would quietly undo it.
        "is_manual": True,
    }
    if "type" in sent:
        fields["type"] = new_type
    if "neighborhood_id" in sent:
        fields["neighborhood_id"] = district.id if district is not None else None
    if "name" in sent:
        fields["name"] = sent["name"]
    if "height" in sent and sent["height"] is not None:
        fields["height"] = float(sent["height"])
    if "rotation" in sent and sent["rotation"] is not None:
        fields["rotation"] = float(sent["rotation"])
    if "is_landmark" in sent and sent["is_landmark"] is not None:
        fields["is_landmark"] = bool(sent["is_landmark"])

    building_repo.write_building_fields(db, building, fields, commit=True)
    return world_service.get_building_detail(db, building.id)


def delete_building(db: Session, building_id: int) -> dict:
    """Demolish one building.

    A real DELETE, unlike a citizen's death, which is a soft flag — see
    `building_repo.delete_building` for why the two differ.

    Works on generated buildings too, deliberately: an admin clearing space should
    not have to care who put the building there. But the honest caveat is reported
    back in `detail`, because a GENERATED building comes back on the next
    `POST /world/generate?force=true`, while a hand-placed one is gone for good.
    """
    building = building_repo.get_building(db, building_id)
    if building is None:
        raise BuildingNotFound(f"Building {building_id} not found")

    former_owner = building.owner_citizen_id
    was_manual = building.is_manual
    label = building.name or spec_for(building.type)["label"]

    building_repo.delete_building(db, building, commit=True)

    detail = f"Demolished building {building_id} ({label})."
    if former_owner is not None:
        # No re-housing here on purpose: this service makes exactly one change per
        # call. The citizen keeps their district, so their marker still renders at
        # the district centre, and a regeneration (or the next citizen creation
        # pass) will give them a house again.
        detail += (
            f" Citizen {former_owner} no longer has a house; their marker will show "
            f"at the district centre until the world is regenerated."
        )
    if not was_manual:
        detail += (
            " This was a generated building, so it will reappear the next time the "
            "world is regenerated."
        )

    return {
        "deleted_building_id": building_id,
        "former_owner_citizen_id": former_owner,
        "detail": detail,
    }
