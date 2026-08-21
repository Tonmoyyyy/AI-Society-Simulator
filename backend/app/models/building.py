from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Building(Base):
    """
    A structure standing in the world (World Phase 2) — a citizen's house, a
    shop, a factory, a government office, the Parliament, the Presidential
    Palace.

    WHY A TABLE AND NOT GENERATED ON THE FLY
    ----------------------------------------
    The spec is explicit: "Do not use meaningless random coordinates every
    time the server restarts. A citizen's house should not randomly move."
    Generating positions in the renderer, or in the service on each request,
    would break that the moment anything about the input order changed. So
    every position is generated once (deterministically) and WRITTEN HERE.
    After that the database is the only source of truth and the generator is
    never consulted again.

    POSITIONS ARE OFFSETS FROM THE CITY CENTRE
    ------------------------------------------
    Same choice as models/neighborhood.py: `offset_x`/`offset_z` are relative
    to the parent city's `world_x`/`world_z`. Re-siting a whole city stays a
    one-row update instead of an UPDATE over thousands of buildings. The API
    returns the computed absolute `world_x`/`world_z` as well, so the renderer
    never redoes that maths.

    Coordinates are X/Z because Three.js's up axis is Y — the ground is the XZ
    plane.

    OWNERSHIP LINKS ARE NULLABLE AND ondelete="SET NULL"
    ----------------------------------------------------
    `owner_citizen_id` is set for houses, `shop_id` for shop buildings; both
    are NULL for civic buildings. Deleting a citizen must leave an empty house
    standing rather than cascade-deleting part of the city, and deleting a
    shop must not delete the building it traded from. This is also why there
    is NO `home_building_id` column added to `citizens`: the link lives on the
    building side only, so nothing about the existing citizens table changes.
    """

    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # A building cannot exist outside a city, and deleting a city should take
    # its buildings with it — this is real containment, unlike the citizen link.
    city_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Nullable: a landmark can sit on city land between districts.
    neighborhood_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("neighborhoods.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # See simulation/building_types.py BUILDING_TYPES for valid values.
    type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Display name. NULL for anonymous houses (the map labels those by their
    # owner's name instead, which is read live from `citizens` — so renaming a
    # citizen renames their house with no data migration).
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    owner_citizen_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("citizens.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    shop_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("shops.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Offset from the parent city's centre, on the XZ ground plane.
    offset_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    offset_z: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Footprint + height in world units. Stored (not looked up from
    # building_types at render time) so a future admin edit can make one
    # specific building bigger without touching the shared type spec.
    width: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    depth: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    height: Mapped[float] = mapped_column(Float, nullable=False, default=7.0)

    # Y-axis rotation in radians. Small per-building variation is what stops a
    # generated district from looking like a spreadsheet.
    rotation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Draw with special geometry / lighting / a name label (Palace, Parliament,
    # monuments). A column rather than a lookup on `type` so an admin can
    # promote any building to a landmark later.
    is_landmark: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
