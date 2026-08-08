from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Memory(Base):
    """
    A single remembered event for a citizen. Simplified for v0.1 per the
    approved corrections — no sentiment score, no decay, no related-citizen
    link yet. Just "what happened and how important was it," which is
    enough for the decision engine to weight recent important events.
    """

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
