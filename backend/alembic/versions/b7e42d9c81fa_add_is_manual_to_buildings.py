"""add is_manual flag to buildings

One boolean column, and it is the whole reason admin map build-mode can exist.

WHAT PROBLEM IT SOLVES
----------------------
`buildings` has always been *derived* data: `POST /api/v1/world/generate?force=true`
deletes every row and rebuilds it from the deterministic generator. That is safe
precisely because nothing in the table was ever authored by a human — it could all
be recomputed.

Hand-placing a building breaks that assumption. A school an admin dropped on a
specific corner is not recomputable: no generator input describes it, so a
regeneration would silently destroy it. `is_manual` is the marker that lets the
regeneration path delete only what it created (see
`building_repo.delete_generated_buildings`) and leave authored rows standing.

WHY A COLUMN AND NOT A SEPARATE TABLE
-------------------------------------
A `custom_buildings` table would need every column `buildings` already has, and
then every read path — the map overview, the venue index for citizen markers,
`list_unowned_houses`, the info panel — would have to UNION the two. A
hand-placed school must behave in every way like a generated one; it differs
only in who authored it, which is exactly what one boolean records.

WHY NOT NULLABLE
----------------
Every row that exists when this runs was produced by the generator, so the
backfill value is known with certainty: 0. A nullable column would introduce an
"unknown provenance" state that the delete path would then have to guess about —
and guessing wrong means either destroying an admin's work or leaving orphaned
geometry that never regenerates.

PURELY ADDITIVE. No column is dropped, renamed or retyped, and nothing outside
`buildings` is touched.

Revision ID: b7e42d9c81fa
Revises: a4c91f7bd3e8
Create Date: 2026-08-22 11:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e42d9c81fa'
down_revision: Union[str, None] = 'a4c91f7bd3e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default is required, not optional: the table already has rows and
    # MySQL has nothing to put in a NOT NULL column without it. Left in place
    # afterwards rather than dropped, so it stays in agreement with
    # `default=False` / `server_default` on models/building.py.
    op.add_column(
        'buildings',
        sa.Column(
            'is_manual', sa.Boolean(), nullable=False, server_default=sa.text('0')
        ),
    )

    # Indexed because the regeneration path filters on it (`WHERE is_manual = 0`
    # for the delete, `WHERE is_manual = 1` to reload the survivors) on a table
    # that holds thousands of rows in a populated world.
    op.create_index(
        op.f('ix_buildings_is_manual'), 'buildings', ['is_manual'], unique=False
    )


def downgrade() -> None:
    # Dropping the column loses the distinction between authored and generated
    # geometry. The buildings themselves survive the downgrade — but the next
    # forced regeneration on the downgraded schema will delete all of them,
    # including the hand-placed ones, because nothing is left to tell them apart.
    op.drop_index(op.f('ix_buildings_is_manual'), table_name='buildings')
    op.drop_column('buildings', 'is_manual')
