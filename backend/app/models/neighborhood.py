from datetime import datetime

from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Neighborhood(Base):
    """
    A district inside a City (World Phase 1) — e.g. "Presidential District",
    "Worker District", "Industrial District".

    IMPORTANT — this does NOT replace `citizens.neighborhood` (the plain
    string column). That legacy column stays exactly as it is, still fed by
    simulation/neighborhoods.py, because the citizen-create form, the
    /citizens/options endpoint, CitizenCreate/CitizenUpdate validation and the
    leaderboard all read it. This table is the new *structured* location
    system that lives alongside it; `citizens.neighborhood_id` is a separate,
    nullable FK. Phase 2 backfills the link. Nothing breaks in between.

    Positions are stored as an OFFSET from the parent city's centre rather
    than as absolute world coordinates. That way, moving or re-laying-out a
    city only updates one `cities` row instead of every district in it, and
    the district layout stays internally consistent. The API exposes the
    absolute world position too (computed as city + offset) so the renderer
    doesn't have to do that maths itself.

    `type` drives how the district is rendered (colour, building style,
    special lighting for the presidential district). Valid values live in
    simulation/world_layout.py — the single source of truth, same pattern as
    simulation/jobs.py and simulation/neighborhoods.py.
    """

    __tablename__ = "neighborhoods"
    __table_args__ = (
        # Two districts in the SAME city can't share a name, but "Central
        # District" existing in several different cities is fine and expected.
        UniqueConstraint("city_id", "name", name="uq_neighborhoods_city_id_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    city_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # See simulation/world_layout.py DISTRICT_TYPES for the valid values.
    type: Mapped[str] = mapped_column(String(30), nullable=False, default="residential")

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Offset from the parent city's centre, on the Three.js XZ ground plane.
    offset_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    offset_z: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # District footprint — the size of the ground plate drawn for it.
    width: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)
    depth: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
