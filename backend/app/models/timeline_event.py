from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimelineEvent(Base):
    """
    Simulation history / replay feature (SDD §9). Written by cheap
    "milestone detector" functions that run once per tick, comparing the
    post-tick state against what's already recorded here — not a new
    simulation subsystem, just detection on top of data the other phases
    already produce.
    """

    __tablename__ = "timeline_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tick_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
