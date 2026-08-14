from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.simulation.jobs import JOB_NAMES
from app.simulation.neighborhoods import NEIGHBORHOOD_NAMES

_TRAIT_NAMES = {"kindness", "intelligence", "ambition", "social", "honesty"}
_VALID_JOBS = set(JOB_NAMES) | {"unemployed"}
_VALID_NEIGHBORHOODS = set(NEIGHBORHOOD_NAMES)


class CitizenCreate(BaseModel):
    """
    All fields optional — an empty body creates a fully randomized citizen
    (name, age, job, neighborhood, personality all auto-assigned). Any field
    you DO pass overrides the random assignment for that field only — e.g.
    passing just `job` still randomizes personality/neighborhood.
    """
    name: Optional[str] = Field(default=None, max_length=100)
    age: Optional[int] = Field(default=None, ge=0, le=120)
    job: Optional[str] = Field(default=None, max_length=100)
    neighborhood: Optional[str] = Field(default=None, max_length=50)
    personality_json: Optional[dict[str, int]] = Field(
        default=None,
        description="All five traits required if provided: kindness, intelligence, ambition, social, honesty (each 0-100).",
    )

    @field_validator("job")
    @classmethod
    def _validate_job(cls, v):
        if v is not None and v not in _VALID_JOBS:
            raise ValueError(f"job must be one of {sorted(_VALID_JOBS)}")
        return v

    @field_validator("neighborhood")
    @classmethod
    def _validate_neighborhood(cls, v):
        if v is not None and v not in _VALID_NEIGHBORHOODS:
            raise ValueError(f"neighborhood must be one of {sorted(_VALID_NEIGHBORHOODS)}")
        return v

    @field_validator("personality_json")
    @classmethod
    def _validate_personality(cls, v):
        if v is None:
            return v
        if set(v.keys()) != _TRAIT_NAMES:
            raise ValueError(f"personality_json must have exactly these keys: {sorted(_TRAIT_NAMES)}")
        for trait, score in v.items():
            if not (0 <= score <= 100):
                raise ValueError(f"{trait} must be between 0 and 100")
        return v


class CitizenUpdate(BaseModel):
    """Partial update — only mutable-by-admin fields. Personality is not
    editable after creation; it's the citizen's fixed nature."""
    name: Optional[str] = Field(default=None, max_length=100)
    job: Optional[str] = Field(default=None, max_length=100)
    neighborhood: Optional[str] = Field(default=None, max_length=50)
    current_activity: Optional[str] = Field(default=None, max_length=100)

    @field_validator("job")
    @classmethod
    def _validate_job(cls, v):
        if v is not None and v not in _VALID_JOBS:
            raise ValueError(f"job must be one of {sorted(_VALID_JOBS)}")
        return v

    @field_validator("neighborhood")
    @classmethod
    def _validate_neighborhood(cls, v):
        if v is not None and v not in _VALID_NEIGHBORHOODS:
            raise ValueError(f"neighborhood must be one of {sorted(_VALID_NEIGHBORHOODS)}")
        return v


class CitizenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    age: int
    personality_json: dict
    mood: float
    happiness: float
    energy: float
    health: float
    job: str
    neighborhood: str
    current_activity: str
    created_at: datetime


class CitizenListResponse(BaseModel):
    total: int
    items: list[CitizenOut]
