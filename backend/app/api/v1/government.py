from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.models.user import User
from app.schemas.government import GovernmentOut, GovernmentUpdate
from app.services import government_service
from app.services.government_service import CitizenNotFound, SameCitizenTwice

router = APIRouter(prefix="/api/v1/government", tags=["government"])


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


# ------------------------------------------------------------------ writes
# Admin-only via the existing `require_admin` from core/deps.py. Appointing the
# head of state and setting the national tax rate are not spectator actions.


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
    Presidential Palace on the 3D map with no frontend change."""
    try:
        return government_service.update_government(
            db, payload.model_dump(exclude_unset=True)
        )
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
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
