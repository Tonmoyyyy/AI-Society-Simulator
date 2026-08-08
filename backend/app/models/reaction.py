from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("post_id", "citizen_id", name="uq_reaction_post_citizen"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False, index=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="like")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
