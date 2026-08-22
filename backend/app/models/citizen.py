from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Boolean, DateTime, JSON, ForeignKey, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.simulation.genders import DEFAULT_GENDER


class Citizen(Base):
    """
    An AI citizen — NOT a human user account (see models/user.py for that).

    Deliberately has no money/balance column: wallets.balance is the single
    source of truth for a citizen's money (see approved v0.1 corrections).
    `job` is a plain string for v0.1 — a real `jobs` table with salary tiers
    arrives in Phase 5 (Economy) when it actually needs behavior.

    TWO IDS, ON PURPOSE
    -------------------
    `id` is an immutable internal surrogate key that a dozen other tables point
    at, and `national_id` is the editable human-facing number. See the comment on
    `national_id` for why the primary key is not the thing an admin customizes.

    DEATH IS A FLAG, NOT A DELETE
    -----------------------------
    `is_alive` / `died_at_tick` / `death_cause` record a death while keeping the
    row, so the person's wallet, posts and timeline history outlive them. Every
    read that means "the population" must filter on `is_alive` — the repository
    does this by default and the places that query this model directly
    (simulation/engine.py, simulation/milestones.py, services/dashboard_service.py,
    services/world_service.py, repositories/world_repo.py) each filter explicitly.
    """

    __tablename__ = "citizens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)

    # ---- identity (admin-customizable) ----
    #
    # One of simulation/genders.py's GENDER_NAMES. NOT NULL with an `unknown`
    # default rather than nullable, so the demographics count never has to
    # special-case NULL and "not recorded" stays visible in the totals instead of
    # vanishing. `default=` and `server_default=` must agree — same reasoning as
    # models/government.py: a raw INSERT from a SQL client still lands on a legal
    # value instead of failing a NOT NULL constraint.
    gender: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=DEFAULT_GENDER,
        server_default=text(f"'{DEFAULT_GENDER}'"),
        index=True,
    )

    # The human-facing citizen number, e.g. "AS-000042" — what an admin quotes
    # when identifying a person, and the ONLY id in this project that is safe to
    # edit.
    #
    # WHY THIS EXISTS INSTEAD OF LETTING `id` BE EDITED
    # -------------------------------------------------
    # `id` is referenced by wallets, posts, comments, reactions, follows,
    # transactions, purchases, memories, buildings.owner_citizen_id,
    # governments.president_citizen_id/first_lady_citizen_id and
    # parliament_members.citizen_id. Changing a primary key would have to
    # rewrite all of them inside one transaction and would still break any URL
    # or bookmark pointing at the old value. So `id` stays an immutable internal
    # surrogate key and this column carries the identifier a human actually
    # cares about.
    #
    # Nullable because a citizen must never be un-creatable for lack of one; the
    # service issues one immediately and the migration backfilled every existing
    # row, so NULL is a transient state rather than a normal one. Unique so two
    # citizens can never share a number.
    national_id: Mapped[Optional[str]] = mapped_column(
        String(24), nullable=True, unique=True, index=True
    )

    # ---- liveness ----
    #
    # SOFT DEATH, NOT DELETION. A dead citizen keeps their row, and with it their
    # wallet, posts, comments, memories and every timeline event that mentions
    # them — the whole point of recording a death is that the history survives
    # it. `DELETE /api/v1/citizens/{id}` still exists for genuine removal (an
    # admin cleaning up a test row); death is a different operation with a
    # different meaning and they are deliberately not the same endpoint.
    #
    # Indexed because nearly every read filters on it: the tick engine, the
    # population count, the citizens roster, the 3D map, the leaderboard and the
    # candidate picker all want the living only.
    is_alive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1"), index=True
    )

    # Which simulation tick they died on. Nullable and only meaningful when
    # `is_alive` is False. A tick number rather than a wall-clock timestamp so it
    # lines up with the timeline, which is measured in ticks and days — a real
    # datetime would say when the server processed it, not when it happened in
    # the simulation.
    died_at_tick: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Free text, e.g. "old age", "poor health", or whatever an admin typed. Not a
    # closed vocabulary on purpose: the two causes the tick engine generates are
    # fixed strings, but an admin marking someone dead should be able to say why
    # in their own words.
    death_cause: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

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
