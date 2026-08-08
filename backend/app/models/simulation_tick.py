from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SimulationTick(Base):
    """
    One row per simulation tick — crash-safety and observability for the
    tick engine (see SDD §Simulation Configuration). If the process dies
    mid-tick, this table shows exactly which tick was running and how far
    it got, instead of the state living only in memory.
    """

    __tablename__ = "simulation_ticks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tick_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    citizens_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    # status values: "running", "completed", "failed"
