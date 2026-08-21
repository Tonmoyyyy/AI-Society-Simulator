"""
DB access for generated world geometry: `buildings` and `roads`
(World Phase 2). No business logic here — same rule as the other repositories.

Kept separate from world_repo.py (cities + districts) because these two tables
are *regenerated* data with a very different lifecycle: cities and districts are
authored and renamed by an admin and must survive forever, while buildings and
roads are derived output that a regeneration is allowed to delete and rebuild.
Mixing "never delete this" and "safe to delete this" access in one module is how
someone eventually wipes the wrong table.
"""

from typing import Iterable, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.building import Building
from app.models.road import Road


# ---------------------------------------------------------------- buildings

def count_buildings(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Building)) or 0


def get_building(db: Session, building_id: int) -> Optional[Building]:
    return db.get(Building, building_id)


def list_buildings(
    db: Session,
    city_id: Optional[int] = None,
    neighborhood_id: Optional[int] = None,
    types: Optional[Iterable[str]] = None,
) -> list[Building]:
    """Ordered by id so the renderer's InstancedMesh indices are stable between
    requests — an unordered result would make markers appear to swap places."""
    query = db.query(Building)
    if city_id is not None:
        query = query.filter(Building.city_id == city_id)
    if neighborhood_id is not None:
        query = query.filter(Building.neighborhood_id == neighborhood_id)
    if types is not None:
        type_list = list(types)
        if type_list:
            query = query.filter(Building.type.in_(type_list))
    return query.order_by(Building.id).all()


def get_home_for_citizen(db: Session, citizen_id: int) -> Optional[Building]:
    return (
        db.query(Building)
        .filter(Building.owner_citizen_id == citizen_id)
        .order_by(Building.id)
        .first()
    )


def map_homes_by_citizen(db: Session) -> dict[int, Building]:
    """One query for every citizen's home, so serialising N citizens stays O(1)
    queries instead of N. Lowest building id wins if a citizen somehow owns
    two, which keeps the result deterministic."""
    rows = (
        db.query(Building)
        .filter(Building.owner_citizen_id.isnot(None))
        .order_by(Building.id)
        .all()
    )
    homes: dict[int, Building] = {}
    for building in rows:
        homes.setdefault(building.owner_citizen_id, building)
    return homes


def list_unowned_houses(db: Session, neighborhood_id: int) -> list[Building]:
    """Houses in a district that nobody lives in yet — used when placing a
    citizen who was created after the world was generated."""
    from app.simulation.building_types import BUILDING_HOUSE

    return (
        db.query(Building)
        .filter(
            Building.neighborhood_id == neighborhood_id,
            Building.type == BUILDING_HOUSE,
            Building.owner_citizen_id.is_(None),
        )
        .order_by(Building.id)
        .all()
    )


def count_buildings_by_city(db: Session) -> dict[int, int]:
    rows = (
        db.query(Building.city_id, func.count(Building.id))
        .group_by(Building.city_id)
        .all()
    )
    return {city_id: count for city_id, count in rows}


def create_building(
    db: Session,
    city_id: int,
    type: str,
    offset_x: float,
    offset_z: float,
    width: float,
    depth: float,
    height: float,
    neighborhood_id: Optional[int] = None,
    name: Optional[str] = None,
    owner_citizen_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    rotation: float = 0.0,
    is_landmark: bool = False,
    commit: bool = True,
) -> Building:
    building = Building(
        city_id=city_id,
        neighborhood_id=neighborhood_id,
        type=type,
        name=name,
        owner_citizen_id=owner_citizen_id,
        shop_id=shop_id,
        offset_x=offset_x,
        offset_z=offset_z,
        width=width,
        depth=depth,
        height=height,
        rotation=rotation,
        is_landmark=is_landmark,
    )
    db.add(building)
    if commit:
        db.commit()
        db.refresh(building)
    return building


def update_building(db: Session, building: Building, **fields) -> Building:
    """Ignores None values so a PATCH only touches what it sent — same
    semantics as citizen_repo.update and world_repo.update_city."""
    for key, value in fields.items():
        if value is not None:
            setattr(building, key, value)
    db.commit()
    db.refresh(building)
    return building


def set_building_owner(
    db: Session, building: Building, citizen_id: Optional[int], commit: bool = True
) -> Building:
    """Explicit setter because update_building() skips None, and clearing an
    owner (moving out) is a legitimate operation that needs to write NULL."""
    building.owner_citizen_id = citizen_id
    if commit:
        db.commit()
        db.refresh(building)
    return building


def delete_all_buildings(db: Session, commit: bool = True) -> int:
    """Used only by the forced regeneration path. Returns the row count so the
    API can report what it destroyed."""
    total = count_buildings(db)
    db.execute(delete(Building))
    if commit:
        db.commit()
    return total


# -------------------------------------------------------------------- roads

def count_roads(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Road)) or 0


def list_roads(db: Session, city_id: Optional[int] = None) -> list[Road]:
    """When `city_id` is given, highways (city_id IS NULL) are included too —
    otherwise a single-city view would show a city with no way in or out."""
    query = db.query(Road)
    if city_id is not None:
        query = query.filter((Road.city_id == city_id) | (Road.city_id.is_(None)))
    return query.order_by(Road.id).all()


def create_road(
    db: Session,
    kind: str,
    start_x: float,
    start_z: float,
    end_x: float,
    end_z: float,
    width: float,
    city_id: Optional[int] = None,
    name: Optional[str] = None,
    commit: bool = True,
) -> Road:
    road = Road(
        city_id=city_id,
        name=name,
        kind=kind,
        start_x=start_x,
        start_z=start_z,
        end_x=end_x,
        end_z=end_z,
        width=width,
    )
    db.add(road)
    if commit:
        db.commit()
        db.refresh(road)
    return road


def delete_all_roads(db: Session, commit: bool = True) -> int:
    total = count_roads(db)
    db.execute(delete(Road))
    if commit:
        db.commit()
    return total
