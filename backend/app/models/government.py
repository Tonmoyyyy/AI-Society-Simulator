from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Government(Base):
    """
    The sitting government: who holds office and the two national policy dials.

    SINGLE-ROW TABLE
    ----------------
    There is exactly one *current* government, so this table is expected to hold
    one row, fetched by lowest id (see government_repo.get_government). It is a
    table rather than a config file because the President changes at runtime and
    that change has to survive a restart.

    WHY NO `president_name` STRING COLUMN
    -------------------------------------
    The President is a citizen, so this stores `president_citizen_id` and the
    name is read from `citizens.name` at request time. That is what makes the
    hard requirement work: renaming citizen "Tonmoy" to "Alex" changes the label
    on the 3D map's Presidential Palace with no regeneration, no cache
    invalidation and no frontend change. A copied name string would go stale the
    moment the citizen was renamed — the same reason `cities` has no cached
    `population` column and `citizens` has no cached `money` column.

    WHY THE OFFICE COLUMNS ARE NULLABLE
    -----------------------------------
    A society can exist before it has a head of state, and a brand-new database
    has citizens before it has a government. Nullable office holders let the row
    exist with the policy dials set while the seats are still vacant, and
    `ondelete="SET NULL"` means deleting a citizen vacates their office instead
    of cascading into deleting the government.

    NO capital_city_id COLUMN
    -------------------------
    The seat of government is already located by `cities.is_capital`. Storing it
    again here would create a second source of truth that could disagree with
    the world data the map is drawn from.

    NOT MODELLED HERE (deliberately, per spec §21 "future-ready"): elections,
    parliament membership, ministers, terms with end dates, or a marriage table.
    The Parliament *building* is already rendered by the world feature; adding
    parliament *membership* is a later phase and needs no change to this table.
    """

    __tablename__ = "governments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # The head of state, and their spouse who holds the First Lady title.
    # Both are citizens; both may be vacant.
    president_citizen_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("citizens.id", ondelete="SET NULL"), nullable=True, index=True
    )
    first_lady_citizen_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("citizens.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # National policy. Stored as a 0.0-1.0 FRACTION, not a percentage, so the
    # API and the map never have to guess which one they were handed; the
    # frontend multiplies by 100 for display.
    #
    # `default=` AND `server_default=` on the next three columns is deliberate,
    # and they must agree. `default=` covers ORM inserts; `server_default=`
    # matches what migration f18a3c6d40b2 actually put in the schema, so a raw
    # `INSERT INTO governments (id) VALUES (1)` in a SQL client still lands on a
    # sane government instead of NULL-ing three NOT NULL columns. (Alembic here
    # is not configured with `compare_server_default=True`, so autogenerate
    # ignores this either way — the parity is for humans and for hand-written
    # SQL.)
    tax_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.10, server_default=text("0.10")
    )

    curfew_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    # Which simulation tick this administration took office on. Lets the
    # timeline say "in office since day N" without a separate terms table.
    term_started_tick: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # `onupdate` is ORM-side only — SQLAlchemy emits the new timestamp as part of
    # the UPDATE statement. It is NOT an `ON UPDATE CURRENT_TIMESTAMP` column, so
    # a hand-written `UPDATE governments SET tax_rate = ...` in a SQL client will
    # not bump this. Every code path goes through government_repo, so that is a
    # note for whoever pokes at the DB directly, not a bug.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
