from datetime import datetime

from sqlalchemy import Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Post(Base):
    """A social post authored by a citizen — written automatically by the
    tick engine's `create_post` action (see simulation/actions.py)."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
