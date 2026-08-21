"""
DB access for the world (cities + neighborhoods). No business logic here —
same rule as the other repositories in this package.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.citizen import Citizen
from app.models.city import City
from app.models.neighborhood import Neighborhood


# ---- cities ----

def count_cities(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(City)) or 0


def list_cities(db: Session) -> list[City]:
    return db.query(City).order_by(City.id).all()


def get_city(db: Session, city_id: int) -> Optional[City]:
    return db.get(City, city_id)


def get_city_by_name(db: Session, name: str) -> Optional[City]:
    return db.query(City).filter(City.name == name).first()


def get_capital(db: Session) -> Optional[City]:
    """The capital hosts the Presidential District. Lowest id wins if the
    data somehow has more than one flagged, so this is always deterministic."""
    return db.query(City).filter(City.is_capital.is_(True)).order_by(City.id).first()


def create_city(
    db: Session,
    name: str,
    region: str,
    description: Optional[str],
    world_x: float,
    world_z: float,
    radius: float,
    is_capital: bool = False,
    commit: bool = True,
) -> City:
    city = City(
        name=name,
        region=region,
        description=description,
        world_x=world_x,
        world_z=world_z,
        radius=radius,
        is_capital=is_capital,
    )
    db.add(city)
    if commit:
        db.commit()
        db.refresh(city)
    return city


def update_city(db: Session, city: City, **fields) -> City:
    """Ignores None values so a PATCH only touches what it actually sent —
    same semantics as citizen_repo.update."""
    for key, value in fields.items():
        if value is not None:
            setattr(city, key, value)
    db.commit()
    db.refresh(city)
    return city


# ---- neighborhoods ----

def count_neighborhoods(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Neighborhood)) or 0


def list_neighborhoods(db: Session, city_id: Optional[int] = None) -> list[Neighborhood]:
    query = db.query(Neighborhood)
    if city_id is not None:
        query = query.filter(Neighborhood.city_id == city_id)
    return query.order_by(Neighborhood.city_id, Neighborhood.id).all()


def get_neighborhood(db: Session, neighborhood_id: int) -> Optional[Neighborhood]:
    return db.get(Neighborhood, neighborhood_id)


def get_neighborhood_by_name(db: Session, city_id: int, name: str) -> Optional[Neighborhood]:
    return (
        db.query(Neighborhood)
        .filter(Neighborhood.city_id == city_id, Neighborhood.name == name)
        .first()
    )


def get_neighborhood_by_type(db: Session, city_id: int, type_: str) -> Optional[Neighborhood]:
    """Used to locate the presidential district without hardcoding its name."""
    return (
        db.query(Neighborhood)
        .filter(Neighborhood.city_id == city_id, Neighborhood.type == type_)
        .order_by(Neighborhood.id)
        .first()
    )


def create_neighborhood(
    db: Session,
    city_id: int,
    name: str,
    type: str,
    description: Optional[str],
    offset_x: float,
    offset_z: float,
    width: float,
    depth: float,
    commit: bool = True,
) -> Neighborhood:
    neighborhood = Neighborhood(
        city_id=city_id,
        name=name,
        type=type,
        description=description,
        offset_x=offset_x,
        offset_z=offset_z,
        width=width,
        depth=depth,
    )
    db.add(neighborhood)
    if commit:
        db.commit()
        db.refresh(neighborhood)
    return neighborhood


def update_neighborhood(db: Session, neighborhood: Neighborhood, **fields) -> Neighborhood:
    for key, value in fields.items():
        if value is not None:
            setattr(neighborhood, key, value)
    db.commit()
    db.refresh(neighborhood)
    return neighborhood


# ---- population distribution (counted, never cached) ----
#
# `cities` and `neighborhoods` have no population column on purpose (see the
# docstring on models/city.py). These GROUP BY queries are the only way
# population is ever reported, so it can't drift from reality.

def count_citizens_by_city(db: Session) -> dict[int, int]:
    rows = (
        db.query(Citizen.city_id, func.count(Citizen.id))
        .filter(Citizen.city_id.isnot(None))
        .group_by(Citizen.city_id)
        .all()
    )
    return {city_id: count for city_id, count in rows}


def count_citizens_by_neighborhood(db: Session) -> dict[int, int]:
    rows = (
        db.query(Citizen.neighborhood_id, func.count(Citizen.id))
        .filter(Citizen.neighborhood_id.isnot(None))
        .group_by(Citizen.neighborhood_id)
        .all()
    )
    return {neighborhood_id: count for neighborhood_id, count in rows}


def count_unassigned_citizens(db: Session) -> int:
    """Citizens with no city yet. Expected to equal the whole population
    until World Phase 2 runs the backfill — surfaced in the API so an empty
    map reads as "not assigned yet" instead of looking like a bug."""
    return (
        db.query(func.count(Citizen.id))
        .filter(Citizen.city_id.is_(None))
        .scalar()
        or 0
    )
