from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Citizen(Base):
    """
    An AI citizen — NOT a human user account (see models/user.py for that).

    Deliberately has no money/balance column: wallets.balance is the single
    source of truth for a citizen's money (see approved v0.1 corrections).
    `job` is a plain string for v0.1 — a real `jobs` table with salary tiers
    arrives in Phase 5 (Economy) when it actually needs behavior.
    """

    __tablename__ = "citizens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)

    # Flat dict of 0-100 int trait scores, e.g.
    # {"kindness": 70, "intelligence": 80, "ambition": 60, "social": 40, "honesty": 90}
    personality_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    mood: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    happiness: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    energy: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    health: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)

    job: Mapped[str] = mapped_column(String(100), nullable=False, default="unemployed")
    current_activity: Mapped[str] = mapped_column(String(100), nullable=False, default="idle")

    # Where in the city this citizen lives — cosmetic/flavor for v0.1 (no
    # commute, rent, or district economy tied to it yet), assigned randomly
    # at creation from simulation/neighborhoods.py unless the creator
    # specifies one.
    #
    # KEPT AS-IS ON PURPOSE (World Phase 1): this plain string is still the
    # column that CitizenCreate/CitizenUpdate validate against, that
    # /api/v1/citizens/options feeds, and that the dashboard leaderboard
    # reads. The structured world link below is additive and does not replace
    # it — removing this would break all three.
    neighborhood: Mapped[str] = mapped_column(String(50), nullable=False, default="Unknown")

    # ---- structured world location (World Phase 1) ----
    # Nullable because every citizen that already exists predates the world
    # tables, and because a citizen must never be un-creatable just for
    # lacking a location. World Phase 2 backfills these; until then the map
    # reports them via `unassigned_citizens`.
    #
    # ondelete="SET NULL" (see the migration): deleting a city or district
    # must never cascade into deleting people.
    city_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    neighborhood_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("neighborhoods.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
