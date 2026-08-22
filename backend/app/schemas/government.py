from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------- outputs

class OfficeHolderOut(BaseModel):
    """A citizen holding an office, reduced to what any UI actually needs.

    Deliberately NOT CitizenOut. Returning the full row here would leak
    personality JSON, energy and mood into every government response and into
    the 3D map payload, which §14 ("do not return unnecessary database fields")
    rules out. The id is included so the frontend can deep-link to the citizen
    profile page that already exists.
    """

    citizen_id: int
    name: str


class GovernmentOut(BaseModel):
    """
    GET /api/v1/government — the sitting government.

    `president` / `first_lady` are null when the office is vacant, which is a
    normal state (a fresh database has citizens before it has a head of state),
    not an error. `tax_rate` is a 0.0-1.0 FRACTION; the frontend multiplies by
    100 for display.

    Office-holder names are resolved from `citizens` on every request rather
    than stored, so renaming a citizen renames the President everywhere —
    including the 3D map's Presidential Palace label — with no frontend change.
    """

    id: int
    president: Optional[OfficeHolderOut] = None
    first_lady: Optional[OfficeHolderOut] = None
    tax_rate: float = Field(description="National tax rate as a 0.0-1.0 fraction.")
    curfew_enabled: bool
    term_started_tick: int = Field(
        description="Simulation tick this administration took office on."
    )

    capital_city_id: Optional[int] = None
    capital_city_name: Optional[str] = None

    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- inputs

class GovernmentUpdate(BaseModel):
    """
    PATCH /api/v1/government — admin-only.

    EVERY FIELD IS OPTIONAL AND `exclude_unset` IS LOAD-BEARING. The service
    passes `model_dump(exclude_unset=True)` to the repository, so a field the
    client did not send is left alone, while a field explicitly sent as `null`
    IS applied. That distinction is the whole point here: sending
    `{"president_citizen_id": null}` vacates the presidency, whereas omitting
    the key keeps the current President. A plain `None` default with no
    exclude_unset would make those two requests indistinguishable.

    The office ids are validated for EXISTENCE in the service, not here —
    a schema cannot see the database, and doing it here would need a session.
    """

    president_citizen_id: Optional[int] = Field(
        default=None,
        description="Citizen id of the President. Send null to vacate the office; omit to leave unchanged.",
    )
    first_lady_citizen_id: Optional[int] = Field(
        default=None,
        description="Citizen id of the First Lady. Send null to vacate the office; omit to leave unchanged.",
    )
    tax_rate: Optional[float] = Field(
        default=None,
        description="National tax rate as a 0.0-1.0 fraction (not a percentage).",
    )
    curfew_enabled: Optional[bool] = None
    term_started_tick: Optional[int] = None

    @field_validator("tax_rate")
    @classmethod
    def _tax_rate_is_a_fraction(cls, v: Optional[float]) -> Optional[float]:
        # Rejecting >1 also catches the most likely client mistake: sending 15
        # meaning "15%" instead of 0.15, which would otherwise silently tax
        # every citizen at 1500%.
        if v is None:
            return v
        if not 0.0 <= v <= 1.0:
            raise ValueError("tax_rate must be a fraction between 0.0 and 1.0 (e.g. 0.15 for 15%)")
        return v

    @field_validator("president_citizen_id", "first_lady_citizen_id", "term_started_tick")
    @classmethod
    def _not_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("must be zero or a positive integer")
        return v
