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


# ------------------------------------------------------------- candidates

class CandidateOut(BaseModel):
    """
    One eligible citizen on the President page's picker.

    Carries more than OfficeHolderOut on purpose. OfficeHolderOut answers "who
    holds this office" and is embedded in every government response and in the 3D
    map payload, so it stays minimal per §14. This schema answers "who should hold
    it", which is a decision — an admin choosing a head of state needs age, gender,
    job and personality to tell one candidate from another, and personality is the
    only field that actually predicts how that citizen will behave in office.

    `current_roles` is pre-rendered display text so the picker can show a badge
    without hardcoding office names; the three booleans are for logic that needs to
    disable or highlight a row.
    """

    citizen_id: int
    national_id: Optional[str] = None
    name: str
    age: int
    gender: str
    job: str
    neighborhood: str
    happiness: float
    personality_json: dict

    is_president: bool = False
    is_first_lady: bool = False
    is_parliament_member: bool = False
    current_roles: list[str] = Field(
        default_factory=list,
        description='Display names of offices already held, e.g. ["President"]. Empty for an unencumbered candidate.',
    )


class CandidateListOut(BaseModel):
    """
    GET /api/v1/government/candidates — the eligible population.

    Only LIVING ADULTS appear. `adult_age` is echoed back so the page can explain
    *why* someone is missing ("must be at least 18") without duplicating the
    setting, the same reason ParliamentListOut returns `seats_total`.

    Unpaginated. The eligible pool is bounded by MAX_CITIZENS_V0 (100 at v0.1), and
    a picker the admin scrolls and searches is more useful than one they have to
    page through. If the cap ever rises materially this becomes the place to add
    pagination.
    """

    total: int
    adult_age: int = Field(
        description="Minimum age to hold office — from settings.ADULT_AGE."
    )
    items: list[CandidateOut]


# ------------------------------------------------------------- parliament

class ParliamentMemberOut(BaseModel):
    """
    One occupied seat.

    The member's name, age, gender and job are resolved from `citizens` by join on
    every request and are NOT stored on `parliament_members` — the same
    derived-not-cached rule that keeps `president_name` off `governments`. Renaming
    a citizen renames the MP everywhere with no migration.

    `is_alive` is present because a death is a soft flag, so the CASCADE on the
    seat's foreign key never fires. Recording a death vacates the seat explicitly;
    this field surfaces any row that got past that path instead of hiding a dead
    legislator in the roster.
    """

    id: int = Field(description="Seat record id — what PATCH and DELETE address.")
    seat_number: int
    party: Optional[str] = None
    appointed_tick: int

    citizen_id: int
    national_id: Optional[str] = None
    name: str
    age: int
    gender: str
    job: str
    is_alive: bool = True


class ParliamentListOut(BaseModel):
    """
    GET /api/v1/government/parliament — the chamber.

    `seats_total` comes from settings.PARLIAMENT_SEATS so the frontend can render
    "18 of 30 seats filled" without its own copy of the cap. Hardcoding it in JS
    would make changing the chamber size a two-file edit — the same mistake as
    hardcoding city names.
    """

    seats_total: int
    seats_filled: int
    seats_available: int
    items: list[ParliamentMemberOut]


class ParliamentAppointRequest(BaseModel):
    """
    POST /api/v1/government/parliament — admin-only.

    `seat_number` is normally omitted and the lowest free seat is assigned, so the
    common case is a one-field request. Pass it only to place someone in a
    particular seat; a taken seat is refused rather than silently reassigned.
    """

    citizen_id: int = Field(
        description="Citizen to seat. Must be living and at least settings.ADULT_AGE."
    )
    party: Optional[str] = Field(
        default=None,
        max_length=60,
        description="Free text — parties are not a modelled entity at this stage.",
    )
    seat_number: Optional[int] = Field(
        default=None,
        ge=1,
        description="Omit to take the lowest free seat.",
    )

    @field_validator("citizen_id")
    @classmethod
    def _positive_citizen_id(cls, v: int) -> int:
        if v < 1:
            raise ValueError("citizen_id must be a positive integer")
        return v


class ParliamentMemberUpdate(BaseModel):
    """
    PATCH /api/v1/government/parliament/{member_id} — admin-only.

    `exclude_unset` IS LOAD-BEARING, for the same reason as GovernmentUpdate:
    `party` is nullable, so sending `{"party": null}` makes the member an
    independent while omitting the key leaves their party alone. The service passes
    `model_dump(exclude_unset=True)` and the repository applies every key it
    receives including None, which is what keeps those two requests distinct.

    The occupant cannot be changed here — moving a seat to a different citizen is
    a removal and an appointment, two decisions that should each be visible rather
    than one PATCH that silently unseats someone.
    """

    party: Optional[str] = Field(
        default=None,
        max_length=60,
        description="Send null to clear (independent); omit to leave unchanged.",
    )
    seat_number: Optional[int] = Field(
        default=None,
        ge=1,
        description="Move this member to a different seat. Refused if occupied.",
    )


class ParliamentRemovalOut(BaseModel):
    """DELETE response — who was removed, by name.

    Returns the name rather than only the id so the UI can confirm the action in
    words ("Removed Maya Chen from seat 4") instead of echoing an id the admin
    would then have to look up.
    """

    id: int
    seat_number: int
    citizen_id: int
    name: Optional[str] = None
