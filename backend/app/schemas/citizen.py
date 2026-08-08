from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CitizenCreate(BaseModel):
    """
    All fields optional — an empty body creates a fully randomized citizen.
    Passing name/age lets a human seed a specific citizen; personality is
    always generated (not user-supplied) since it drives the decision engine
    and shouldn't be hand-picked to "win" the simulation.
    """
    name: Optional[str] = Field(default=None, max_length=100)
    age: Optional[int] = Field(default=None, ge=0, le=120)


class CitizenUpdate(BaseModel):
    """Partial update — only mutable-by-admin fields. Personality is not
    editable after creation; it's the citizen's fixed nature."""
    name: Optional[str] = Field(default=None, max_length=100)
    job: Optional[str] = Field(default=None, max_length=100)
    current_activity: Optional[str] = Field(default=None, max_length=100)


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
    current_activity: str
    created_at: datetime


class CitizenListResponse(BaseModel):
    total: int
    items: list[CitizenOut]
