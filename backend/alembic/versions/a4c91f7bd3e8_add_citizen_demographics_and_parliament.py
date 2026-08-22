"""add citizen gender, national id and liveness; create parliament_members

Two things at once because they are one feature: the admin can now customize
every citizen (gender, a human-facing national ID, full profile edit), mark
people dead, and appoint Parliament.

PURELY ADDITIVE. Five new nullable-or-defaulted columns on `citizens` and one
new table. No existing column is dropped, renamed or retyped — in particular
`citizens.neighborhood` (the legacy plain string) is left exactly as it is,
because CitizenCreate/CitizenUpdate validation, `/api/v1/citizens/options` and
the dashboard leaderboard all still read it.

WHY `gender` IS NOT NULL WITH A DEFAULT
--------------------------------------
Nullable would mean every demographics query has to special-case NULL, and
"not recorded" would quietly disappear from the totals. NOT NULL DEFAULT
'unknown' keeps it visible and countable. The backfill below then upgrades the
rows it can classify honestly and leaves the rest for an admin to correct.

WHY `is_alive` IS NOT NULL DEFAULT 1
------------------------------------
Everyone who exists when this migration runs is alive. A nullable column would
introduce a third state ("unknown whether alive") that nothing in the product
means or handles.

WHY THE NAME POOLS ARE COPIED IN HERE INSTEAD OF IMPORTED
---------------------------------------------------------
`app.simulation.name_generator` has the same lists, but a migration must
describe what happened at the moment it ran. If a later release adds names to
that module, importing it would silently change what this already-applied
migration would have done — and worse, `alembic downgrade` then `upgrade` on an
old database would produce different data than the first run. Frozen copies are
the correct trade here even though they duplicate ten lines.

Revision ID: a4c91f7bd3e8
Revises: f18a3c6d40b2
Create Date: 2026-08-22 09:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c91f7bd3e8'
down_revision: Union[str, None] = 'f18a3c6d40b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Frozen snapshot of app/simulation/name_generator.py's gendered pools at the
# time this migration was written. See the module docstring for why these are
# copied rather than imported. Lowercased because a hand-typed name may not
# match the generator's capitalisation.
_MALE_FIRST_NAMES = {
    "aiden", "rahim", "leo", "kenji", "omar", "hiro", "diego", "noah",
    "mateo", "yusuf",
}
_FEMALE_FIRST_NAMES = {
    "maya", "priya", "sara", "nadia", "elena", "fatima", "amara", "zara",
    "layla", "ines",
}

# Matches app/simulation/genders.py. Kept as literals for the same
# frozen-in-time reason as the name pools.
_GENDER_MALE = "male"
_GENDER_FEMALE = "female"
_GENDER_UNKNOWN = "unknown"

# Matches the format citizen_service issues for new citizens. If you change the
# format there, do NOT change it here — issue the new format going forward and
# leave already-numbered citizens alone, exactly as a real registry would.
_NATIONAL_ID_PREFIX = "AS"


def _infer_gender(name) -> str:
    if not name:
        return _GENDER_UNKNOWN
    first = str(name).strip().split(" ")[0].lower()
    if first in _MALE_FIRST_NAMES:
        return _GENDER_MALE
    if first in _FEMALE_FIRST_NAMES:
        return _GENDER_FEMALE
    return _GENDER_UNKNOWN


def upgrade() -> None:
    # ---- citizens: new columns ----
    #
    # server_default is set on the two NOT NULL columns so the ALTER can run
    # against a table that already has rows — without it MySQL has nothing to put
    # in the new column for existing citizens and rejects the statement. The
    # defaults are left in place afterwards rather than dropped, so they stay in
    # agreement with `default=`/`server_default=` on models/citizen.py.
    op.add_column(
        'citizens',
        sa.Column(
            'gender', sa.String(length=10), nullable=False,
            server_default=sa.text(f"'{_GENDER_UNKNOWN}'"),
        ),
    )
    op.add_column(
        'citizens',
        sa.Column('national_id', sa.String(length=24), nullable=True),
    )
    op.add_column(
        'citizens',
        sa.Column(
            'is_alive', sa.Boolean(), nullable=False, server_default=sa.text('1')
        ),
    )
    op.add_column(
        'citizens',
        sa.Column('died_at_tick', sa.Integer(), nullable=True),
    )
    op.add_column(
        'citizens',
        sa.Column('death_cause', sa.String(length=100), nullable=True),
    )

    op.create_index(op.f('ix_citizens_gender'), 'citizens', ['gender'], unique=False)
    op.create_index(op.f('ix_citizens_is_alive'), 'citizens', ['is_alive'], unique=False)

    # ---- backfill, BEFORE the unique index on national_id ----
    #
    # Order matters: every existing row currently has national_id = NULL, and
    # while MySQL permits duplicate NULLs under a unique index, creating the index
    # first and then filling it in row by row would leave a window where a
    # concurrent insert could collide. Filling first and constraining after is
    # both safer and faster.
    #
    # Done in Python rather than as one clever UPDATE statement because the gender
    # inference is a lookup against two name lists, which SQL would express as a
    # 20-branch CASE that nobody could read or verify. At MAX_CITIZENS_V0 = 100
    # the row-by-row cost is irrelevant.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, name FROM citizens ORDER BY id")
    ).fetchall()

    for row in rows:
        citizen_id = row[0]
        bind.execute(
            sa.text(
                "UPDATE citizens SET gender = :gender, national_id = :national_id "
                "WHERE id = :id"
            ),
            {
                "gender": _infer_gender(row[1]),
                # Derived from the primary key so the backfill is deterministic:
                # re-running it on a copy of the same database produces the same
                # numbers. New citizens get theirs from citizen_service, which
                # uses the same format.
                "national_id": f"{_NATIONAL_ID_PREFIX}-{citizen_id:06d}",
                "id": citizen_id,
            },
        )

    op.create_index(
        op.f('ix_citizens_national_id'), 'citizens', ['national_id'], unique=True
    )

    # ---- parliament_members ----
    op.create_table(
        'parliament_members',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('citizen_id', sa.Integer(), nullable=False),
        sa.Column('seat_number', sa.Integer(), nullable=False),
        sa.Column('party', sa.String(length=60), nullable=True),
        sa.Column(
            'appointed_tick', sa.Integer(), nullable=False, server_default=sa.text('0')
        ),
        sa.Column(
            'created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
        # CASCADE, unlike governments' SET NULL: a seat row with no citizen in it
        # carries no information, whereas a government with a vacant presidency
        # does. See models/parliament_member.py.
        sa.ForeignKeyConstraint(
            ['citizen_id'], ['citizens.id'],
            name='fk_parliament_members_citizen_id',
            ondelete='CASCADE',
        ),
    )
    # Both unique: one seat per person AND one person per seat. Either constraint
    # alone still permits a nonsense roster.
    op.create_index(
        op.f('ix_parliament_members_citizen_id'),
        'parliament_members',
        ['citizen_id'],
        unique=True,
    )
    op.create_index(
        op.f('ix_parliament_members_seat_number'),
        'parliament_members',
        ['seat_number'],
        unique=True,
    )


def downgrade() -> None:
    # Exact reverse order. Constraints are explicitly named above so MySQL can
    # drop them by name rather than relying on auto-generated identifiers.
    op.drop_index(
        op.f('ix_parliament_members_seat_number'), table_name='parliament_members'
    )
    op.drop_index(
        op.f('ix_parliament_members_citizen_id'), table_name='parliament_members'
    )
    op.drop_table('parliament_members')

    op.drop_index(op.f('ix_citizens_national_id'), table_name='citizens')
    op.drop_index(op.f('ix_citizens_is_alive'), table_name='citizens')
    op.drop_index(op.f('ix_citizens_gender'), table_name='citizens')

    # Dropping these columns discards every recorded death. That is inherent to
    # reversing this migration, not an oversight — there is nowhere else to put
    # the information, and leaving the columns behind would make the downgrade a
    # no-op that lies about having run.
    op.drop_column('citizens', 'death_cause')
    op.drop_column('citizens', 'died_at_tick')
    op.drop_column('citizens', 'is_alive')
    op.drop_column('citizens', 'national_id')
    op.drop_column('citizens', 'gender')
