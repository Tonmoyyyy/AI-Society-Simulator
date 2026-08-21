from datetime import datetime

from sqlalchemy import String, Text, Float, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class City(Base):
    """
    A city in the simulated society (World Phase 1).

    Deliberately has NO `population` column: `citizens` is the single source
    of truth for who lives where, so population is COUNTED from
    citizens.city_id at read time instead of cached here. This is the same
    rule the project already applies to money (wallets.balance is the only
    source of truth, never a cached `citizens.money` column — see SDD §8).
    A cached population column would silently drift every time a citizen is
    created, deleted, or migrates between cities.

    `world_x` / `world_z` are the city's position on the Three.js ground
    plane. We use X/Z (not X/Y) because in Three.js Y is the UP axis, so the
    ground is the XZ plane — storing it this way means the renderer can use
    these numbers directly with no axis conversion. Positions live in the DB
    (not generated at random on boot) so the world is stable across restarts.

    `radius` is the city's boundary size, used later for drawing city
    limits and for framing the camera when the user selects a city.
    """

    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Unique so the admin/president rename flow can't create two "Nova City"s.
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    region: Mapped[str] = mapped_column(String(100), nullable=False, default="Central")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # World position on the Three.js XZ ground plane.
    world_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    world_z: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # City boundary size (used for bounds rendering + camera framing).
    radius: Mapped[float] = mapped_column(Float, nullable=False, default=120.0)

    # The capital hosts the Presidential District (Palace + Parliament).
    # A flag rather than a hardcoded city name, so renaming the capital or
    # moving the seat of government never requires a frontend change.
    is_capital: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
