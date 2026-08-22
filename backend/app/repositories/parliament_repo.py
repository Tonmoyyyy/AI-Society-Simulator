"""
DB access for parliament seats. No business logic — same rule as the other
repositories in this package.

Separate from `government_repo` because `governments` is a single fixed row and
`parliament_members` is a variable-length roster; they share a domain but not a
single query shape. The business rules that span both (a member must be a living
adult, a death vacates the seat) live in `government_service`, which is the only
module that imports both.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.citizen import Citizen
from app.models.parliament_member import ParliamentMember


def count_members(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(ParliamentMember)) or 0


def list_members(db: Session) -> list[ParliamentMember]:
    """Ordered by seat number, which is how a chamber is described to a human."""
    return db.query(ParliamentMember).order_by(ParliamentMember.seat_number).all()


def list_members_with_citizens(db: Session) -> list[tuple[ParliamentMember, Citizen]]:
    """The roster joined to its citizens in one round trip.

    Exists so rendering the roster is a single query instead of one `db.get` per
    seat. Returns the full Citizen rows rather than just names — unlike
    `government_repo.get_office_holders` — because the roster UI shows age,
    gender and job for each member, and re-fetching those per row would be worse
    than passing the row through and letting the service pick fields.
    """
    return (
        db.query(ParliamentMember, Citizen)
        .join(Citizen, Citizen.id == ParliamentMember.citizen_id)
        .order_by(ParliamentMember.seat_number)
        .all()
    )


def get_member(db: Session, member_id: int) -> Optional[ParliamentMember]:
    return db.get(ParliamentMember, member_id)


def get_member_by_citizen(db: Session, citizen_id: int) -> Optional[ParliamentMember]:
    return (
        db.query(ParliamentMember)
        .filter(ParliamentMember.citizen_id == citizen_id)
        .first()
    )


def taken_seat_numbers(db: Session) -> set[int]:
    """Just the occupied seat numbers, for finding the lowest free one.

    A set of at most PARLIAMENT_SEATS integers, so the service can pick a seat
    without loading the rows.
    """
    return {row[0] for row in db.execute(select(ParliamentMember.seat_number)).all()}


def seated_citizen_ids(db: Session) -> set[int]:
    """Who already has a seat — used to mark them in the candidate list so an
    admin is not offered someone they have already appointed."""
    return {row[0] for row in db.execute(select(ParliamentMember.citizen_id)).all()}


def create_member(
    db: Session,
    citizen_id: int,
    seat_number: int,
    party: Optional[str] = None,
    appointed_tick: int = 0,
    commit: bool = True,
) -> ParliamentMember:
    member = ParliamentMember(
        citizen_id=citizen_id,
        seat_number=seat_number,
        party=party,
        appointed_tick=appointed_tick,
    )
    db.add(member)
    if commit:
        db.commit()
        db.refresh(member)
    return member


def update_member(db: Session, member: ParliamentMember, **fields) -> ParliamentMember:
    """Applies every key present, including None.

    Follows `government_repo.update_government` rather than `citizen_repo.update`:
    `party` is genuinely nullable and setting it to null ("this member is now an
    independent") is a real instruction. Callers must therefore omit keys they do
    not intend to change, which is what the service does by building the dict from
    `model_dump(exclude_unset=True)`.
    """
    for key, value in fields.items():
        setattr(member, key, value)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def delete_member(db: Session, member: ParliamentMember, commit: bool = True) -> None:
    """`commit=False` so a death can vacate a seat inside the tick's single batch
    commit instead of committing mid-loop."""
    db.delete(member)
    if commit:
        db.commit()
