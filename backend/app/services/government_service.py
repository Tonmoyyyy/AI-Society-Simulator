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

IMPORT RULE: this module may import `government_repo`, `parliament_repo`,
`citizen_repo` and `world_repo`. It must NOT import `world_service`,
`world_generation_service` or `citizen_service` — `citizen_service` imports THIS
module (so that recording a death can vacate the offices the deceased held), and
importing it back would close the cycle.

Everything returns plain dicts; the schemas in schemas/government.py shape the
HTTP response, same convention as world_service.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.citizen import Citizen
from app.models.government import Government
from app.models.parliament_member import ParliamentMember
from app.repositories import (
    citizen_repo,
    government_repo,
    parliament_repo,
    simulation_tick_repo,
    world_repo,
)


class GovernmentError(Exception):
    """Raised for government business-rule failures the API layer maps to HTTP."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CitizenNotFound(GovernmentError):
    pass


class SameCitizenTwice(GovernmentError):
    pass


class CitizenNotEligible(GovernmentError):
    """The citizen exists but cannot hold office — deceased, or under age.

    Distinct from CitizenNotFound because the fix is different: "no such citizen"
    means the id is wrong, while this means the id is right and the person is not
    eligible. The API maps it to 400 rather than 404 for the same reason.
    """


class ParliamentFull(GovernmentError):
    """Every seat is taken. settings.PARLIAMENT_SEATS is a real cap, not a hint —
    appointing into a full chamber is refused rather than silently growing it."""


class AlreadySeated(GovernmentError):
    """This citizen already holds a seat. One person, one seat."""


class SeatNotFound(GovernmentError):
    """No seat record with that id. The id is wrong — maps to 404."""


class InvalidSeatNumber(GovernmentError):
    """A seat number outside 1..PARLIAMENT_SEATS.

    Separate from SeatNotFound so the API can answer 400 rather than 404: the
    request is malformed, not pointing at something that has been removed. Folding
    the two together would send an admin hunting for a deleted seat record when the
    real problem is that they asked for seat 99 in a 30-seat chamber.
    """


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
    """The two lowest-id ELIGIBLE citizens, or fewer if the society is that small.

    Ordering by id (not by `random`, not by happiness) keeps this deterministic
    across restarts, which is the same rule the world generator follows: the
    same database must always produce the same world.

    Fetches a page of ten and filters in Python rather than asking the repository
    for adults, because `citizen_repo.list_alive_adults` orders by NAME for the
    picker UI and using it here would make first-boot appointment depend on
    alphabetical order instead of id. Ten is enough headroom to find two adults in
    any realistic population while keeping the query bounded.
    """
    citizens, _total = citizen_repo.list_paginated(db, 0, 10)
    eligible = [c.id for c in citizens if c.age >= settings.ADULT_AGE]
    president_id = eligible[0] if len(eligible) >= 1 else None
    first_lady_id = eligible[1] if len(eligible) >= 2 else None
    return president_id, first_lady_id


def _require_eligible(db: Session, citizen_id: int) -> Citizen:
    """Resolve a citizen id and assert they may hold public office.

    Three conditions, and the order of the checks is the order of the messages an
    admin is most likely to need: does this person exist, are they alive, are they
    an adult.

    THE LIVENESS CHECK IS WHY `vacate_offices_for_citizen` EXISTS. Together they
    close the loop: a dead citizen cannot be appointed, and a citizen who dies
    while in office is removed from it. Without both halves the map could label
    the palace with a dead President indefinitely.
    """
    citizen = citizen_repo.get_by_id(db, citizen_id)
    if citizen is None:
        raise CitizenNotFound(f"Citizen {citizen_id} not found")
    if not citizen.is_alive:
        raise CitizenNotEligible(
            f"{citizen.name} is deceased and cannot hold office"
        )
    if citizen.age < settings.ADULT_AGE:
        raise CitizenNotEligible(
            f"{citizen.name} is {citizen.age} and must be at least "
            f"{settings.ADULT_AGE} to hold office"
        )
    return citizen


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
    #
    # `fields.get(key)` returning None covers two cases that both correctly skip
    # validation: the key is absent ("leave this office alone") or the key is
    # explicitly null ("vacate this office"). Neither names a citizen to check.
    for key in ("president_citizen_id", "first_lady_citizen_id"):
        citizen_id = fields.get(key)
        if citizen_id is not None:
            _require_eligible(db, citizen_id)

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

    # Ten rather than four: `list_paginated` returns the living, but some of them
    # may be under age, and filtering after the fetch needs headroom or a society
    # whose first few citizens are children would appoint nobody.
    candidates, _total = citizen_repo.list_paginated(db, 0, 10)
    taken = {gov.president_citizen_id, gov.first_lady_citizen_id}
    available = [
        c.id
        for c in candidates
        if c.id not in taken and c.age >= settings.ADULT_AGE
    ]

    fields: dict = {}
    if gov.president_citizen_id is None and available:
        fields["president_citizen_id"] = available.pop(0)
    if gov.first_lady_citizen_id is None and available:
        fields["first_lady_citizen_id"] = available.pop(0)

    if fields:
        government_repo.update_government(db, gov, **fields)
    return _serialize(db, gov)


def _current_tick(db: Session) -> int:
    """The most recent tick number, or 0 if the simulation has never run.

    Ticks are 1-BASED (`simulation_tick_repo.next_tick_number` returns
    `(max or 0) + 1`), so 0 genuinely means "before the first tick" and is not an
    off-by-one.
    """
    recent = simulation_tick_repo.list_recent(db, limit=1)
    return recent[0].tick_number if recent else 0


# --------------------------------------------------------------- candidates

def list_candidates(db: Session) -> dict:
    """
    Everyone eligible for public office, each annotated with what they already hold.

    THIS IS THE PICKER'S DATA SOURCE. There is no nomination step and no election:
    the admin is the system's observer and operator, not a voter, so the President
    page lists the eligible population and appointment is a direct choice. §21
    lists elections as a future extension, and this endpoint is the seam they would
    plug into — an election would replace how a candidate is *chosen* without
    changing what "eligible" means.

    Eligibility is exactly `_require_eligible`: living, and at least
    settings.ADULT_AGE. The same rule is enforced again at appointment time, so a
    candidate list that has gone stale in a browser tab cannot be used to appoint
    someone who has since died.

    `current_roles` is returned as a list of human-readable strings rather than
    three booleans alone, so the picker can render a badge without deciding what to
    call each office. The booleans are there too, because a UI that needs to grey
    out an already-seated citizen should not have to string-match.
    """
    gov = government_repo.get_government(db)
    president_id = gov.president_citizen_id if gov is not None else None
    first_lady_id = gov.first_lady_citizen_id if gov is not None else None
    seated = parliament_repo.seated_citizen_ids(db)

    items = []
    for citizen in citizen_repo.list_alive_adults(db, settings.ADULT_AGE):
        is_president = citizen.id == president_id
        is_first_lady = citizen.id == first_lady_id
        is_mp = citizen.id in seated

        roles = []
        if is_president:
            roles.append("President")
        if is_first_lady:
            roles.append("First Lady")
        if is_mp:
            roles.append("Parliament Member")

        items.append(
            {
                "citizen_id": citizen.id,
                "national_id": citizen.national_id,
                "name": citizen.name,
                "age": citizen.age,
                "gender": citizen.gender,
                "job": citizen.job,
                "neighborhood": citizen.neighborhood,
                "happiness": citizen.happiness,
                # Included because the picker shows it — the admin is choosing a
                # head of state and personality is the only thing that
                # distinguishes one candidate's behaviour from another's.
                "personality_json": citizen.personality_json,
                "is_president": is_president,
                "is_first_lady": is_first_lady,
                "is_parliament_member": is_mp,
                "current_roles": roles,
            }
        )

    return {
        "total": len(items),
        "adult_age": settings.ADULT_AGE,
        "items": items,
    }


# --------------------------------------------------------------- parliament

def _serialize_member(member: ParliamentMember, citizen: Citizen) -> dict:
    """Shape a seat plus its occupant for ParliamentMemberOut.

    The citizen's name is resolved from the joined row on every request rather
    than stored on `parliament_members` — the same derived-not-cached rule that
    keeps `president_name` off `governments`. Renaming a citizen renames the MP
    everywhere, with no migration and no frontend change.
    """
    return {
        "id": member.id,
        "seat_number": member.seat_number,
        "party": member.party,
        "appointed_tick": member.appointed_tick,
        "citizen_id": citizen.id,
        "national_id": citizen.national_id,
        "name": citizen.name,
        "age": citizen.age,
        "gender": citizen.gender,
        "job": citizen.job,
        # A seat is not vacated automatically when its occupant dies — death is a
        # soft flag, so the CASCADE on the foreign key never fires. Recording a
        # death calls `vacate_offices_for_citizen`, which removes the seat. This
        # field is the safety net for any row that slipped through (a citizen
        # marked dead directly in the database, say), so the roster shows the
        # problem instead of hiding it.
        "is_alive": citizen.is_alive,
    }


def list_parliament(db: Session) -> dict:
    """The chamber: every occupied seat, plus how many remain.

    `seats_total` and `seats_available` come back alongside the roster so the UI
    can render "18 of 30 seats filled" without knowing what
    settings.PARLIAMENT_SEATS is. Hardcoding the cap in the frontend would make
    changing it a two-file edit, which is the same mistake as hardcoding city
    names.
    """
    rows = parliament_repo.list_members_with_citizens(db)
    items = [_serialize_member(member, citizen) for member, citizen in rows]
    return {
        "seats_total": settings.PARLIAMENT_SEATS,
        "seats_filled": len(items),
        "seats_available": max(settings.PARLIAMENT_SEATS - len(items), 0),
        "items": items,
    }


def _next_free_seat(db: Session) -> int:
    """The lowest unoccupied seat number in 1..PARLIAMENT_SEATS.

    Lowest-free rather than highest-plus-one so that removing a member and
    appointing another reuses the empty seat instead of leaving a permanent hole
    and eventually running past the cap with seats still free.
    """
    taken = parliament_repo.taken_seat_numbers(db)
    for seat in range(1, settings.PARLIAMENT_SEATS + 1):
        if seat not in taken:
            return seat
    raise ParliamentFull(
        f"All {settings.PARLIAMENT_SEATS} parliament seats are occupied"
    )


def appoint_parliament_member(
    db: Session,
    citizen_id: int,
    party: Optional[str] = None,
    seat_number: Optional[int] = None,
) -> dict:
    """
    Seat a citizen in parliament.

    `seat_number` is normally omitted and the lowest free seat is assigned. Pass it
    to place someone in a specific seat — useful for reproducing a particular
    chamber layout, and refused if that seat is taken rather than quietly moving
    the request elsewhere.

    Every rule is checked before anything is written, so a rejected appointment
    leaves the chamber exactly as it was.
    """
    citizen = _require_eligible(db, citizen_id)

    if parliament_repo.get_member_by_citizen(db, citizen_id) is not None:
        raise AlreadySeated(f"{citizen.name} already holds a parliament seat")

    if seat_number is None:
        seat_number = _next_free_seat(db)
    else:
        if not 1 <= seat_number <= settings.PARLIAMENT_SEATS:
            raise InvalidSeatNumber(
                f"seat_number must be between 1 and {settings.PARLIAMENT_SEATS}"
            )
        if seat_number in parliament_repo.taken_seat_numbers(db):
            raise AlreadySeated(f"Seat {seat_number} is already occupied")

    member = parliament_repo.create_member(
        db,
        citizen_id=citizen_id,
        seat_number=seat_number,
        party=party,
        appointed_tick=_current_tick(db),
    )
    return _serialize_member(member, citizen)


def update_parliament_member(db: Session, member_id: int, fields: dict) -> dict:
    """Change a seated member's party or seat. `fields` must come from
    `ParliamentMemberUpdate.model_dump(exclude_unset=True)`.

    WHY exclude_unset MATTERS: `party` is nullable, so a key present with value
    None means "this member is now an independent" while an absent key means
    "leave the party alone". `parliament_repo.update_member` applies every key it
    is given, including None, which is what makes that distinction work — and what
    makes passing a full dump here a bug.
    """
    member = parliament_repo.get_member(db, member_id)
    if member is None:
        raise SeatNotFound(f"Parliament member {member_id} not found")

    new_seat = fields.get("seat_number")
    if new_seat is not None and new_seat != member.seat_number:
        if not 1 <= new_seat <= settings.PARLIAMENT_SEATS:
            raise InvalidSeatNumber(
                f"seat_number must be between 1 and {settings.PARLIAMENT_SEATS}"
            )
        if new_seat in parliament_repo.taken_seat_numbers(db):
            raise AlreadySeated(f"Seat {new_seat} is already occupied")

    if fields:
        parliament_repo.update_member(db, member, **fields)

    citizen = citizen_repo.get_by_id(db, member.citizen_id)
    return _serialize_member(member, citizen)


def remove_parliament_member(db: Session, member_id: int) -> dict:
    """Vacate a seat. Returns a small record of who was removed, so the API can
    confirm the action by name instead of echoing an id the admin then has to
    look up.

    The citizen is untouched — losing a seat is not a death and not a deletion.
    """
    member = parliament_repo.get_member(db, member_id)
    if member is None:
        raise SeatNotFound(f"Parliament member {member_id} not found")

    citizen = citizen_repo.get_by_id(db, member.citizen_id)
    removed = {
        "id": member.id,
        "seat_number": member.seat_number,
        "citizen_id": member.citizen_id,
        "name": citizen.name if citizen is not None else None,
    }
    parliament_repo.delete_member(db, member)
    return removed


# ----------------------------------------------------- deaths and vacancies

def vacate_offices_for_citizen(db: Session, citizen_id: int) -> list[str]:
    """
    Strip every office a citizen holds. Returns the offices that were actually
    vacated, as display strings, so a caller can tell the admin what changed.

    CALLED BY `citizen_service.mark_citizen_dead`. This is the half of the
    liveness contract that `_require_eligible` cannot cover: that function stops a
    dead citizen being appointed, and this one removes a citizen who dies while
    serving. Without it the 3D map would keep labelling the Presidential Palace
    with a dead President, because the map resolves the name by join and the join
    does not care whether the person is alive.

    WHY THE FOREIGN KEYS DO NOT DO THIS FOR US: `governments` uses ON DELETE SET
    NULL and `parliament_members` uses ON DELETE CASCADE, and neither fires,
    because a death is a flag rather than a row deletion. That is the trade the
    soft-delete design makes — history survives, and the cleanup that a hard
    delete would have got for free becomes this function's job.

    Safe to call for a citizen who holds nothing; it returns an empty list. Also
    safe to call twice — the second call finds nothing left to vacate.
    """
    vacated: list[str] = []

    gov = government_repo.get_government(db)
    if gov is not None:
        fields: dict = {}
        if gov.president_citizen_id == citizen_id:
            fields["president_citizen_id"] = None
            vacated.append("President")
        if gov.first_lady_citizen_id == citizen_id:
            fields["first_lady_citizen_id"] = None
            vacated.append("First Lady")
        if fields:
            government_repo.update_government(db, gov, **fields)

    member = parliament_repo.get_member_by_citizen(db, citizen_id)
    if member is not None:
        vacated.append(f"Parliament seat {member.seat_number}")
        parliament_repo.delete_member(db, member)

    return vacated
