from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.models.user import User
from app.schemas.government import (
    CandidateListOut,
    GovernmentOut,
    GovernmentUpdate,
    ParliamentAppointRequest,
    ParliamentListOut,
    ParliamentMemberOut,
    ParliamentMemberUpdate,
    ParliamentRemovalOut,
)
from app.services import government_service
from app.services.government_service import (
    AlreadySeated,
    CitizenNotEligible,
    CitizenNotFound,
    InvalidSeatNumber,
    ParliamentFull,
    SameCitizenTwice,
    SeatNotFound,
)

router = APIRouter(prefix="/api/v1/government", tags=["government"])

# ---------------------------------------------------------------------------
# ROUTE ORDER: literal paths before parameterised ones. `/parliament` must be
# registered before `/parliament/{member_id}` — Starlette matches in
# registration order and takes the first hit. Same rule the world and citizens
# routers document.
# ---------------------------------------------------------------------------


# ------------------------------------------------------------------ reads
# Public, matching the read-is-public convention used by citizens / posts /
# shops / dashboard / world — a spectator can see who governs the society
# without logging in.


@router.get("", response_model=GovernmentOut)
def get_government(db: Session = Depends(get_db)):
    """Public — the sitting government: President, First Lady, tax rate,
    curfew, and which city is the capital.

    404 when no government row exists at all, which happens only if startup
    seeding never ran (for example the app booted with no database). The 3D map
    does not depend on this route — it reads the government through
    GET /api/v1/world, which degrades to `system_available: false` instead of
    erroring."""
    gov = government_service.get_government(db)
    if gov is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No government exists yet. An admin can create one with PATCH /api/v1/government.",
        )
    return gov


@router.get("/candidates", response_model=CandidateListOut)
def list_candidates(db: Session = Depends(get_db)):
    """Public — every citizen eligible for public office, annotated with what
    they already hold.

    THIS IS WHAT THE PRESIDENT PAGE'S PICKER READS. There is no nomination step
    and no vote: the admin observes and operates the society rather than voting in
    it, so appointment is a direct choice from this list. Elections are listed in
    §21 as a future extension and this endpoint is the seam they would plug into —
    an election would change how a candidate is chosen without changing what
    "eligible" means.

    Eligible means living and at least `adult_age`, which is echoed in the response
    so the page can explain why someone is missing without keeping its own copy of
    the setting. The same rule is enforced again at appointment time, so a list
    left open in a browser tab cannot be used to appoint someone who has since
    died."""
    return government_service.list_candidates(db)


@router.get("/parliament", response_model=ParliamentListOut)
def list_parliament(db: Session = Depends(get_db)):
    """Public — the chamber: every occupied seat plus how many remain.

    `seats_total` comes from settings.PARLIAMENT_SEATS so the frontend can render
    "18 of 30 seats filled" without its own copy of the cap."""
    return government_service.list_parliament(db)


# ------------------------------------------------------------------ writes
# Admin-only via the existing `require_admin` from core/deps.py. Appointing the
# head of state, seating legislators and setting the national tax rate are not
# spectator actions.


@router.patch("", response_model=GovernmentOut)
def update_government(
    payload: GovernmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — appoint or vacate offices and set national policy.

    Send only the fields you want to change. A field sent as `null` VACATES
    that office; an omitted field is left untouched — which is why this uses
    `exclude_unset=True` rather than a plain dump. Creates the government row
    if it is missing, so this also works as "establish a government".

    Because office holders are stored as citizen ids and names are resolved on
    read, appointing a different President immediately relabels the
    Presidential Palace on the 3D map with no frontend change.

    An appointee must be living and at least settings.ADULT_AGE. Both office ids
    are validated before anything is written, so a request naming one eligible and
    one ineligible citizen changes nothing at all."""
    try:
        return government_service.update_government(
            db, payload.model_dump(exclude_unset=True)
        )
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except CitizenNotEligible as e:
        # 400, not 404: the id is correct and the citizen exists — they are simply
        # not eligible. A 404 would send the admin looking for a wrong id.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except SameCitizenTwice as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message
        )


@router.post("/auto-appoint", response_model=GovernmentOut)
def auto_appoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — fill any vacant office with a citizen, leaving filled offices
    alone.

    Useful on a database whose citizens were generated after the government row
    was created, where both offices are vacant. Deliberately manual: startup
    never does this, so dissolving the government stays dissolved until an admin
    says otherwise. Idempotent — a second call with both offices filled changes
    nothing."""
    return government_service.auto_appoint(db)


@router.post(
    "/parliament",
    response_model=ParliamentMemberOut,
    status_code=status.HTTP_201_CREATED,
)
def appoint_parliament_member(
    payload: ParliamentAppointRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — seat a citizen in parliament.

    Omit `seat_number` and the lowest free seat is used, which is the normal case.
    Pass it to place someone in a particular seat; an occupied seat is refused
    rather than silently reassigned.

    One citizen, one seat. Appointing someone who already sits is a 409, not a
    second seat. The chamber is capped at settings.PARLIAMENT_SEATS and a full
    house is a 409 as well — the cap is real, not a hint."""
    try:
        return government_service.appoint_parliament_member(
            db,
            citizen_id=payload.citizen_id,
            party=payload.party,
            seat_number=payload.seat_number,
        )
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except CitizenNotEligible as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except (AlreadySeated, ParliamentFull) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except InvalidSeatNumber as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)


@router.patch("/parliament/{member_id}", response_model=ParliamentMemberOut)
def update_parliament_member(
    member_id: int,
    payload: ParliamentMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — change a seated member's party or move them to another seat.

    `member_id` is the SEAT RECORD id, not the citizen id. Sending
    `{"party": null}` makes the member an independent; omitting `party` leaves it
    alone — the distinction `exclude_unset` preserves.

    The occupant cannot be changed here. Moving a seat to a different citizen is a
    removal plus an appointment, two decisions that should each be visible."""
    try:
        return government_service.update_parliament_member(
            db, member_id, payload.model_dump(exclude_unset=True)
        )
    except SeatNotFound as e:
        # 404 when the member id is unknown, 400 when the requested seat number is
        # out of range — both raise SeatNotFound, so the message distinguishes
        # them. Kept as one exception because "that seat does not exist" is the
        # same fact in both cases.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except AlreadySeated as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.delete("/parliament/{member_id}", response_model=ParliamentRemovalOut)
def remove_parliament_member(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin — vacate a seat.

    Returns who was removed, by name, so the UI can confirm in words instead of
    echoing an id. The citizen itself is untouched — losing a seat is neither a
    death nor a deletion. The freed seat number is reused by the next
    appointment."""
    try:
        return government_service.remove_parliament_member(db, member_id)
    except SeatNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
