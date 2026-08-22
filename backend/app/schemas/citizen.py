import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.simulation.genders import GENDER_NAMES, GENDER_UNKNOWN, label_for
from app.simulation.jobs import JOB_NAMES
from app.simulation.neighborhoods import NEIGHBORHOOD_NAMES

_TRAIT_NAMES = {"kindness", "intelligence", "ambition", "social", "honesty"}
_VALID_JOBS = set(JOB_NAMES) | {"unemployed"}
_VALID_NEIGHBORHOODS = set(NEIGHBORHOOD_NAMES)
_VALID_GENDERS = set(GENDER_NAMES)

# Uppercase letters, digits and dashes, 3-24 characters. Deliberately permissive
# about the shape: the service issues "AS-000042", but an admin renaming a
# citizen's number to match some other registry should not be told their format
# is wrong. What is enforced is that it is short, uppercase and free of
# whitespace, so it stays usable as a lookup key someone types.
_NATIONAL_ID_PATTERN = re.compile(r"^[A-Z0-9-]{3,24}$")


def _validate_national_id(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v = v.strip().upper()
    if not _NATIONAL_ID_PATTERN.match(v):
        raise ValueError(
            "national_id must be 3-24 characters of uppercase letters, digits or dashes"
        )
    return v


def _validate_personality(v: Optional[dict]) -> Optional[dict]:
    if v is None:
        return v
    if set(v.keys()) != _TRAIT_NAMES:
        raise ValueError(f"personality_json must have exactly these keys: {sorted(_TRAIT_NAMES)}")
    for trait, score in v.items():
        if not (0 <= score <= 100):
            raise ValueError(f"{trait} must be between 0 and 100")
    return v


class CitizenCreate(BaseModel):
    """
    All fields optional — an empty body creates a fully randomized citizen
    (name, gender, age, job, neighborhood, personality all auto-assigned). Any
    field you DO pass overrides the random assignment for that field only — e.g.
    passing just `job` still randomizes personality/neighborhood.

    `name` and `gender` interact: pass both and both are used; pass only `gender`
    and the name is drawn from the pool matching it; pass only `name` and the
    gender is inferred from it where possible (`unknown` otherwise); pass neither
    and a matching pair is generated. See simulation/name_generator.generate_person.

    `national_id` is normally omitted — the service issues one from the new
    citizen's id. Pass it only when importing someone with an existing number.
    """
    name: Optional[str] = Field(default=None, max_length=100)
    gender: Optional[str] = Field(
        default=None,
        description=f"One of {sorted(_VALID_GENDERS)}. Omit to have it assigned.",
    )
    age: Optional[int] = Field(default=None, ge=0, le=120)
    job: Optional[str] = Field(default=None, max_length=100)
    neighborhood: Optional[str] = Field(default=None, max_length=50)
    national_id: Optional[str] = Field(
        default=None,
        max_length=24,
        description="Usually omitted — one is issued automatically. Must be unique.",
    )
    personality_json: Optional[dict[str, int]] = Field(
        default=None,
        description="All five traits required if provided: kindness, intelligence, ambition, social, honesty (each 0-100).",
    )

    @field_validator("job")
    @classmethod
    def _check_job(cls, v):
        if v is not None and v not in _VALID_JOBS:
            raise ValueError(f"job must be one of {sorted(_VALID_JOBS)}")
        return v

    @field_validator("neighborhood")
    @classmethod
    def _check_neighborhood(cls, v):
        if v is not None and v not in _VALID_NEIGHBORHOODS:
            raise ValueError(f"neighborhood must be one of {sorted(_VALID_NEIGHBORHOODS)}")
        return v

    @field_validator("gender")
    @classmethod
    def _check_gender(cls, v):
        if v is not None and v not in _VALID_GENDERS:
            raise ValueError(f"gender must be one of {sorted(_VALID_GENDERS)}")
        return v

    @field_validator("national_id")
    @classmethod
    def _check_national_id(cls, v):
        return _validate_national_id(v)

    @field_validator("personality_json")
    @classmethod
    def _check_personality(cls, v):
        return _validate_personality(v)


class CitizenUpdate(BaseModel):
    """
    Full profile edit. Every field is optional and only the ones you send are
    written — omitting a field leaves it alone rather than clearing it.

    PERSONALITY IS NOW EDITABLE — a reversal, and a deliberate one. This schema
    previously said "Personality is not editable after creation; it's the
    citizen's fixed nature", which was a reasonable simulation stance but is
    incompatible with the admin being able to customize every citizen. The
    simulation reads personality on every decision, so editing it genuinely
    changes how that citizen behaves from the next tick onward. That is the
    intent, not a side effect.

    WELLBEING IS EDITABLE TOO, AND `health` HAS A CONSEQUENCE. Setting health at
    or below settings.CRITICAL_HEALTH makes the citizen die of ill health on the
    next tick (see simulation/mortality.py). That is the one edit here that can
    end a life, so it is called out rather than left to be discovered.

    NOT EDITABLE HERE: `city_id` / `neighborhood_id`, the structured world
    location. Moving a citizen between districts has to move their house too, or
    the 3D map draws their marker in one district while their home building sits
    in another — two sources of truth disagreeing. Relocation is therefore its own
    operation rather than a field on this form. The legacy `neighborhood` display
    string IS editable, because nothing positional depends on it.

    Also not editable: `id` (see models/citizen.py for why the primary key is
    immutable — `national_id` is the identifier an admin customizes) and
    `is_alive` (death is POST /{id}/death, so that it can record when and why and
    vacate any office held, none of which a bare field assignment would do).
    """

    name: Optional[str] = Field(default=None, max_length=100)
    gender: Optional[str] = Field(default=None)
    age: Optional[int] = Field(default=None, ge=0, le=120)
    job: Optional[str] = Field(default=None, max_length=100)
    neighborhood: Optional[str] = Field(default=None, max_length=50)
    current_activity: Optional[str] = Field(default=None, max_length=100)
    national_id: Optional[str] = Field(default=None, max_length=24)
    personality_json: Optional[dict[str, int]] = Field(
        default=None,
        description="All five traits required if provided (each 0-100). Changes how this citizen decides from the next tick.",
    )
    mood: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    happiness: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    energy: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    health: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="At or below settings.CRITICAL_HEALTH this citizen dies of ill health on the next tick.",
    )

    @field_validator("job")
    @classmethod
    def _check_job(cls, v):
        if v is not None and v not in _VALID_JOBS:
            raise ValueError(f"job must be one of {sorted(_VALID_JOBS)}")
        return v

    @field_validator("neighborhood")
    @classmethod
    def _check_neighborhood(cls, v):
        if v is not None and v not in _VALID_NEIGHBORHOODS:
            raise ValueError(f"neighborhood must be one of {sorted(_VALID_NEIGHBORHOODS)}")
        return v

    @field_validator("gender")
    @classmethod
    def _check_gender(cls, v):
        if v is not None and v not in _VALID_GENDERS:
            raise ValueError(f"gender must be one of {sorted(_VALID_GENDERS)}")
        return v

    @field_validator("national_id")
    @classmethod
    def _check_national_id(cls, v):
        return _validate_national_id(v)

    @field_validator("personality_json")
    @classmethod
    def _check_personality(cls, v):
        return _validate_personality(v)


class CitizenDeathRequest(BaseModel):
    """Why they died, in the admin's own words.

    `cause` is free text rather than a closed vocabulary: the two causes the tick
    engine produces are fixed strings, but an admin recording a death should be
    able to say what happened.
    """
    cause: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Free text, e.g. 'old age'. Defaults to 'recorded by admin'.",
    )


class CitizenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    national_id: Optional[str] = None
    name: str
    gender: str = GENDER_UNKNOWN
    gender_label: Optional[str] = None
    age: int
    personality_json: dict
    mood: float
    happiness: float
    energy: float
    health: float
    job: str
    neighborhood: str
    current_activity: str
    # Liveness is always present rather than only when someone is dead, so a
    # frontend can render "living"/"deceased" from one field without having to
    # infer it from the absence of another.
    is_alive: bool = True
    died_at_tick: Optional[int] = None
    death_cause: Optional[str] = None
    created_at: datetime

    @model_validator(mode="after")
    def _fill_gender_label(self):
        """Derive the display label from the stored value.

        Done here rather than in the service so that EVERY endpoint returning a
        CitizenOut gets the label for free — there are six of them across
        citizens, government and world, and one of them would eventually be
        forgotten if each had to remember to attach it. `label_for` falls back to
        the raw value, so an unrecognised gender still renders.
        """
        if self.gender_label is None:
            self.gender_label = label_for(self.gender)
        return self


class CitizenListResponse(BaseModel):
    total: int
    items: list[CitizenOut]


class CitizenDeathOut(BaseModel):
    """
    POST /api/v1/citizens/{id}/death — the recorded death plus its consequences.

    `vacated_offices` is the reason this is not just a CitizenOut. Marking the
    President dead also empties the presidency, which relabels the Presidential
    Palace on the 3D map and changes the dashboard's government block. An admin who
    was not told that happened would reasonably read it as a bug, so the response
    names every office the death emptied.

    Empty list for an ordinary citizen — the common case, and not an error.
    """

    citizen: CitizenOut
    vacated_offices: list[str] = Field(
        default_factory=list,
        description='Offices this death emptied, e.g. ["President", "Parliament seat 4"].',
    )


class GenderCountOut(BaseModel):
    """One row of the gender breakdown.

    Carries `label` alongside `gender` so a chart legend does not have to keep its
    own copy of the display names — the same reason the world map reads its labels
    and colours from GET /api/v1/world/legend instead of hardcoding them.
    """
    gender: str
    label: str
    count: int


class AgeBracketOut(BaseModel):
    label: str
    count: int


class CitizenDemographicsOut(BaseModel):
    """
    Population makeup, counted at request time.

    Nothing here is stored. Every number is a GROUP BY or a COUNT against the
    current rows, so it cannot drift out of agreement with the citizens table the
    way a cached tally would.

    `living` and `deceased` are separate top-level numbers rather than a single
    `total`, because after the first death "how many citizens are there" has two
    different right answers and the API should not pick one silently. The gender
    breakdown counts the LIVING only, which is what "how many men and women are in
    my society" means; `gender_breakdown_all_time` includes the dead for anyone who
    wants the historical figure.
    """
    living: int
    deceased: int
    total_ever: int
    gender_breakdown: list[GenderCountOut]
    gender_breakdown_all_time: list[GenderCountOut]
    male: int
    female: int
    other: int
    unknown: int
    age_brackets: list[AgeBracketOut]
    average_age: Optional[float] = None
