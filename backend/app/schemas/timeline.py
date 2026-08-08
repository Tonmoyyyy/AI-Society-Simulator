from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tick_number: int
    category: str
    title: str
    description: str
    payload_json: Optional[dict]
    created_at: datetime


class TimelineListResponse(BaseModel):
    total: int
    items: list[TimelineEventOut]
