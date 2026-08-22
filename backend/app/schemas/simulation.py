from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TickResult(BaseModel):
    tick_number: int
    citizens_processed: int
    deaths: int = Field(
        default=0,
        description="Citizens who died of natural causes during this tick.",
    )
    status: str


class TickOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tick_number: int
    started_at: datetime
    finished_at: Optional[datetime]
    citizens_processed: int
    status: str


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    citizen_id: int
    event_type: str
    description: str
    importance: int
    created_at: datetime


class SchedulerStatus(BaseModel):
    running: bool
