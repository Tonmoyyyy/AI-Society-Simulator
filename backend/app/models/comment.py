from datetime import datetime
from typing import Optional

from sqlalchemy import Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False, index=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Self-referential: NULL means a top-level comment on the post; set
    # means this is a reply to another comment (real threading, not just
    # @name text addressing — see simulation/social_interactions.py).
    parent_comment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("comments.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
