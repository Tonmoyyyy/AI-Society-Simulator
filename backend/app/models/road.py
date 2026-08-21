from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Road(Base):
    """
    A road segment (World Phase 2) — stored as a straight line between two
    points, which the renderer draws as a flat ribbon on the ground.

    WHY ABSOLUTE COORDINATES HERE, WHEN EVERYTHING ELSE USES OFFSETS
    ---------------------------------------------------------------
    Districts and buildings are stored as offsets from their city centre
    because they are always *inside* exactly one city. A highway is not: it
    runs from one city to another and belongs to neither exclusively, so
    there is no single city whose centre the offset could be relative to.
    Rather than have two different coordinate conventions in one table, all
    roads use absolute world coordinates. `city_id` stays as a *tag* (which
    city this road serves, NULL for highways) rather than a coordinate origin.

    WHY STRAIGHT SEGMENTS AND NOT A PATH/SPLINE
    -------------------------------------------
    The spec asks for a stylised miniature civilization observed from above,
    and explicitly defers pathfinding ("Do NOT implement complicated
    pathfinding in the first version"). A straight segment is one row, renders
    as two triangles, and is enough to communicate "these places are
    connected". Curved roads would need a geometry format in the DB and buy
    nothing at this zoom level. Adding a `points_json` column later is purely
    additive if that ever changes.

    Coordinates are X/Z because Three.js's up axis is Y.
    """

    __tablename__ = "roads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # NULL for highways between cities. SET NULL (not CASCADE) so deleting a
    # city leaves the highways that used to reach it as orphaned segments the
    # regenerator can clean up, rather than silently vanishing mid-transaction.
    city_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # See simulation/building_types.py ROAD_KINDS.
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="district", index=True)

    start_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    start_z: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    end_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    end_z: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    width: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
