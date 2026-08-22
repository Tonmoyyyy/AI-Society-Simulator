"""
Government business logic: who holds office, and the two national policy dials.

WHY THIS MODULE EXISTS SEPARATELY FROM world_service
----------------------------------------------------
The 3D map needs the President's and First Lady's names, but the map is a
*reader* of the government, not its owner. Keeping the government here means:

  * `world_service` imports `government_service` (one direction only), so there
    is no circular import — `government_service` must never import
    `world_service`. The one fact the map contributes, "which city is the
    capital", is read from `cities.is_capital` via `world_repo` instead.
  * the government can be changed by an admin without touching any world code.

IMPORT RULE: this module may import `government_repo`, `citizen_repo` and
`world_repo`. It must NOT import `world_service` or `world_generation_service`.

Everything returns plain dicts; the schemas in schemas/government.py shape the
HTTP response, same convention as world_service.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.government import Government
from app.repositories import citizen_repo, government_repo, simulation_tick_repo, world_repo


class GovernmentError(Exception):
    """Raised for government business-rule failures the API layer maps to HTTP."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CitizenNotFound(GovernmentError):
    pass


class SameCitizenTwice(GovernmentError):
    pass


# ------------------------------------------------------------------ seeding

def ensure_government(db: Session) -> dict:
    """
    Create the single government row if — and only if — none exists.

    Idempotent, like `ensure_seed_world` and `ensure_seed_shops`: one existence
    check makes this a no-op on every boot after the first. That is what makes
    an admin's changes permanent — including a *deliberate vacancy*. If this
    re-appointed a President whenever the office was empty, an admin who
    dissolved the government would find it restored on the next restart.

    FIRST-BOOT APPOINTMENT, AND WHY IT IS NOT HARDCODING
    ----------------------------------------------------
    When the row is created, the two lowest-id citizens are appointed President
    and First Lady, purely so the map has something to label instead of an empty
    palace. Nothing about those citizens is special and no name appears anywhere
    in this file — the names are read from `citizens` at request time, so
    renaming that citizen renames the President on the 3D map with no
    regeneration and no frontend change. An admin can reassign either office at
    any time via PATCH /api/v1/government, and this function will never
    overwrite that.

    ON A COMPLETELY EMPTY DATABASE, BOTH OFFICES START VACANT
    ---------------------------------------------------------
    Nothing in this project creates citizens automatically — they arrive via
    POST /api/v1/citizens — so a brand-new install boots with zero citizens and
    there is simply nobody to appoint. The row is still created, with both
    offices vacant, and because this function keys off the ROW it will not come
    back and appoint anyone on a later boot once citizens do exist. That is
    intentional (see above: a later retry could not tell "never appointed" apart
    from "deliberately vacated"), and it is why two escape hatches exist:
    `POST /api/v1/government/auto-appoint` and PATCH /api/v1/government. The map
    surfaces this state explicitly rather than leaving the palace mysteriously
    unlabelled — see the vacancy notice in frontend/static/js/world/main.js.
    """
    existing = government_repo.get_government(db)
    if existing is not None:
        return {"created": False, "government_id": existing.id}

    president_id, first_lady_id = _pick_default_office_holders(db)

    recent = simulation_tick_repo.list_recent(db, limit=1)
    current_tick = recent[0].tick_number if recent else 0

    gov = government_repo.create_government(
        db,
        president_citizen_id=president_id,
        first_lady_citizen_id=first_lady_id,
        tax_rate=0.10,
        curfew_enabled=False,
        term_started_tick=current_tick,
    )
    return {"created": True, "government_id": gov.id}


def _pick_default_office_holders(db: Session) -> tuple[Optional[int], Optional[int]]:
    """The two lowest-id citizens, or fewer if the society is that small.

    Ordering by id (not by `random`, not by happiness) keeps this deterministic
    across restarts, which is the same rule the world generator follows: the
    same database must always produce the same world.
    """
    citizens, _total = citizen_repo.list_paginated(db, 0, 2)
    president_id = citizens[0].id if len(citizens) >= 1 else None
    first_lady_id = citizens[1].id if len(citizens) >= 2 else None
    return president_id, first_lady_id


# -------------------------------------------------------------------- reads

def get_government(db: Session) -> Optional[dict]:
    """The sitting government as a dict, or None if the row does not exist.

    None is a legitimate answer, not an error: it means `ensure_government` has
    never run (the app booted without a database, or this is a test that didn't
    seed). The route turns it into a 404 and the map falls back to hiding
    government-only UI.
    """
    gov = government_repo.get_government(db)
    if gov is None:
        return None
    return _serialize(db, gov)


def _serialize(db: Session, gov: Government) -> dict:
    """Shape a Government row for GovernmentOut, resolving names by join.

    Names are looked up here on every request rather than stored on the row —
    the whole reason the model has no `president_name` column.
    """
    names = government_repo.get_office_holders(
        db, gov.president_citizen_id, gov.first_lady_citizen_id
    )
    capital = world_repo.get_capital(db)

    return {
        "id": gov.id,
        "president": _office_holder(gov.president_citizen_id, names),
        "first_lady": _office_holder(gov.first_lady_citizen_id, names),
        "tax_rate": gov.tax_rate,
        "curfew_enabled": gov.curfew_enabled,
        "term_started_tick": gov.term_started_tick,
        "capital_city_id": capital.id if capital else None,
        "capital_city_name": capital.name if capital else None,
        "created_at": gov.created_at,
        "updated_at": gov.updated_at,
    }


def _office_holder(citizen_id: Optional[int], names: dict[int, str]) -> Optional[dict]:
    """None for a vacant office — and also None if the id somehow has no
    matching citizen, which reads as vacant rather than crashing. The FKs are
    ON DELETE SET NULL, so that second case should not survive a commit."""
    if citizen_id is None:
        return None
    name = names.get(citizen_id)
    if name is None:
        return None
    return {"citizen_id": citizen_id, "name": name}


def get_summary(db: Session) -> dict:
    """
    Flat summary for the 3D map's Presidential Palace panel.

    THIS IS THE FUNCTION `world_service.get_government_summary` CALLS. It
    returns only the government's own fields — no capital city, no presidential
    district — because `world_service` already knows those from the world data
    and merges them in. Keeping the split here is what stops the two modules
    needing to import each other.

    `system_available` is False only when the government row is missing — which
    means "no government has been established", not "this feature doesn't
    exist". A database that was never seeded (the test suite, or a first boot
    before MySQL was reachable) therefore still serves the map, which hides its
    government-only UI instead of erroring. Note that True does not imply a
    President: an established government can have vacant offices, so
    `president_name` may still be None here.
    """
    gov = government_repo.get_government(db)
    if gov is None:
        return {
            "president_name": None,
            "first_lady_name": None,
            "tax_rate": None,
            "curfew_enabled": None,
            "system_available": False,
        }

    names = government_repo.get_office_holders(
        db, gov.president_citizen_id, gov.first_lady_citizen_id
    )
    # `is not None`, not truthiness: an office is vacant only when its column is
    # NULL. Testing the id for truth would report citizen id 0 as a vacancy and
    # disagree with `_office_holder` above, which gets this right — so
    # GET /api/v1/government and the map summary would contradict each other.
    return {
        "president_name": (
            names.get(gov.president_citizen_id)
            if gov.president_citizen_id is not None
            else None
        ),
        "first_lady_name": (
            names.get(gov.first_lady_citizen_id)
            if gov.first_lady_citizen_id is not None
            else None
        ),
        "tax_rate": gov.tax_rate,
        "curfew_enabled": gov.curfew_enabled,
        "system_available": True,
    }


# ------------------------------------------------------------------- writes

def update_government(db: Session, fields: dict) -> dict:
    """
    Apply an admin PATCH. `fields` must come from
    `GovernmentUpdate.model_dump(exclude_unset=True)`.

    WHY exclude_unset MATTERS HERE: a key that is present with value None means
    "vacate this office", while an absent key means "leave it alone". If the
    route passed a full dump, every PATCH would vacate both offices.

    Creates the government row if it is missing, so an admin can configure the
    government on a database where startup seeding never ran (for example the
    test suite, or a first boot before MySQL was reachable).
    """
    gov = government_repo.get_government(db)
    if gov is None:
        gov = government_repo.create_government(db)

    # Validate both office ids BEFORE writing anything, so a request naming one
    # real and one bogus citizen changes nothing at all.
    for key in ("president_citizen_id", "first_lady_citizen_id"):
        citizen_id = fields.get(key)
        if citizen_id is not None and citizen_repo.get_by_id(db, citizen_id) is None:
            raise CitizenNotFound(f"Citizen {citizen_id} not found")

    # The President cannot also be the First Lady. Checked against the values
    # that will be in effect after the patch, not just the ones sent, so
    # promoting the current First Lady to President without vacating her old
    # office is caught too.
    president_after = fields.get(
        "president_citizen_id", gov.president_citizen_id
    )
    first_lady_after = fields.get(
        "first_lady_citizen_id", gov.first_lady_citizen_id
    )
    if president_after is not None and president_after == first_lady_after:
        raise SameCitizenTwice(
            f"Citizen {president_after} cannot hold both offices — "
            "vacate one in the same request (send it as null)"
        )

    if fields:
        government_repo.update_government(db, gov, **fields)
    return _serialize(db, gov)


def auto_appoint(db: Session) -> dict:
    """
    Fill any VACANT office with a citizen, leaving filled offices untouched.

    Exists because `ensure_government` deliberately runs once: on a database
    whose citizens were generated after first boot, both offices are vacant and
    nothing will ever fill them on its own. This is the explicit, admin-
    triggered way to populate them — never automatic, so it cannot undo a
    deliberate vacancy behind the admin's back.

    Skips whoever already holds the other office, so one citizen can't end up
    appointed to both.
    """
    gov = government_repo.get_government(db)
    if gov is None:
        gov = government_repo.create_government(db)

    if gov.president_citizen_id is not None and gov.first_lady_citizen_id is not None:
        return _serialize(db, gov)

    # Four is enough: at most two offices to fill, and at most two ids to skip.
    candidates, _total = citizen_repo.list_paginated(db, 0, 4)
    taken = {gov.president_citizen_id, gov.first_lady_citizen_id}
    available = [c.id for c in candidates if c.id not in taken]

    fields: dict = {}
    if gov.president_citizen_id is None and available:
        fields["president_citizen_id"] = available.pop(0)
    if gov.first_lady_citizen_id is None and available:
        fields["first_lady_citizen_id"] = available.pop(0)

    if fields:
        government_repo.update_government(db, gov, **fields)
    return _serialize(db, gov)
