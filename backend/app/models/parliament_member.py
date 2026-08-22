from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ParliamentMember(Base):
    """
    One seat in Parliament, held by one citizen.

    WHY A SEPARATE TABLE AND NOT COLUMNS ON `governments`
    -----------------------------------------------------
    `governments` is a single-row table with exactly two office holders, which is
    why it can get away with two FK columns. Parliament is a variable-length
    roster, so it needs its own table — the alternative (a JSON list of citizen
    ids on the government row) would give up the foreign key, which is the thing
    that makes "deleting a citizen removes them from Parliament" automatic
    instead of something every code path has to remember.

    NO CACHED NAME COLUMN
    ---------------------
    Same rule as `governments`: this stores `citizen_id` and the name is resolved
    from `citizens` on read. Renaming a citizen renames the MP everywhere,
    including on the 3D map, with no regeneration and no frontend change.

    TWO UNIQUE CONSTRAINTS, AND WHY BOTH ARE NEEDED
    -----------------------------------------------
    `citizen_id` is unique so one person cannot hold two seats, and
    `seat_number` is unique so one seat cannot hold two people. Either
    constraint alone permits a nonsense roster, so the database enforces both
    rather than trusting the service layer to check.

    NO ELECTION MODELLING
    ---------------------
    The admin appoints members directly — that was an explicit product decision,
    not an omission. Votes, parties with seat counts, coalitions and terms with
    end dates are all §21 "future-ready" work. `party` exists as free text so a
    roster can be grouped visually today without committing to a `parties` table
    that would need its own migration, service and CRUD before it did anything.
    """

    __tablename__ = "parliament_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ondelete="CASCADE", unlike governments' SET NULL. The difference is
    # deliberate: a government with a vacant presidency is a real, meaningful
    # state worth keeping a row for, but a parliament seat row with no citizen in
    # it carries no information at all — it is just a hole in the roster. So
    # hard-deleting a citizen removes their seat outright.
    #
    # Note this does NOT fire on death: death is a soft flag, so the row survives
    # and parliament_service evicts the member explicitly. That is on purpose —
    # the eviction is a decision the service should make and log, not a silent
    # database side effect.
    citizen_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("citizens.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # 1-based, matching how the seats are described to a human. Assigned by the
    # service as the lowest free number, so removing seat 3 from a 5-seat house
    # and appointing someone new reuses 3 rather than creating a gap and a seat 6.
    seat_number: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=True, index=True
    )

    # Free text. Nullable because an independent has no party, and "" would be a
    # second way of saying the same thing.
    party: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    # Which simulation tick they took their seat on, so the roster can say "since
    # day N" without a separate terms table — same approach as
    # governments.term_started_tick.
    appointed_tick: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
