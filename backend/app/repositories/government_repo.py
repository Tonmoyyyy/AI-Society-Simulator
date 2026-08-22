"""
DB access for the government. No business logic here — same rule as the other
repositories in this package.

The one non-obvious query is `get_office_holders`, which resolves office-holder
names in a single round trip instead of two `db.get(Citizen, ...)` calls, and
returns names rather than Citizen rows so callers can't accidentally leak a
citizen's full record (personality JSON, energy, wallet) into a response.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.citizen import Citizen
from app.models.government import Government


def get_government(db: Session) -> Optional[Government]:
    """The sitting government, or None if one has never been created.

    Lowest id wins if the data somehow holds more than one row, so this is
    always deterministic — same tie-break as world_repo.get_capital.
    """
    return db.query(Government).order_by(Government.id).first()


def create_government(
    db: Session,
    president_citizen_id: Optional[int] = None,
    first_lady_citizen_id: Optional[int] = None,
    tax_rate: float = 0.10,
    curfew_enabled: bool = False,
    term_started_tick: int = 0,
    commit: bool = True,
) -> Government:
    gov = Government(
        president_citizen_id=president_citizen_id,
        first_lady_citizen_id=first_lady_citizen_id,
        tax_rate=tax_rate,
        curfew_enabled=curfew_enabled,
        term_started_tick=term_started_tick,
    )
    db.add(gov)
    if commit:
        db.commit()
        db.refresh(gov)
    return gov


def update_government(db: Session, gov: Government, **fields) -> Government:
    """Applies only the keys present in `fields`, so a PATCH touches nothing it
    didn't send.

    UNLIKE citizen_repo.update / world_repo.update_city, a None value here IS
    applied. Those helpers skip None because for them "absent" and "null" mean
    the same thing, but this table has two genuinely nullable columns where null
    is a meaningful instruction: `president_citizen_id=None` means "vacate the
    office". Callers must therefore omit keys they don't intend to change rather
    than passing None — which is what government_service does, building the dict
    from `payload.model_dump(exclude_unset=True)`.
    """
    for key, value in fields.items():
        setattr(gov, key, value)
    db.add(gov)
    db.commit()
    db.refresh(gov)
    return gov


def get_office_holders(
    db: Session, president_citizen_id: Optional[int], first_lady_citizen_id: Optional[int]
) -> dict[int, str]:
    """Map {citizen_id: name} for whichever of the two ids were given.

    Returns names only — never Citizen rows — so a government response can't
    accidentally carry a citizen's personality JSON or energy. Ids that no
    longer exist are simply absent from the result, which callers read as a
    vacant office; this can only happen transiently since the FKs are
    ON DELETE SET NULL.
    """
    ids = [cid for cid in (president_citizen_id, first_lady_citizen_id) if cid is not None]
    if not ids:
        return {}
    rows = db.execute(
        select(Citizen.id, Citizen.name).where(Citizen.id.in_(ids))
    ).all()
    return {row.id: row.name for row in rows}
