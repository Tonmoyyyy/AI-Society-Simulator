"""create cities and neighborhoods tables, link citizens to them

World Phase 1. Purely ADDITIVE:
  - creates `cities` and `neighborhoods`
  - adds nullable `city_id` / `neighborhood_id` to `citizens`

Nothing is dropped, renamed or retyped. In particular the existing
`citizens.neighborhood` VARCHAR column is left untouched — it is still used by
CitizenCreate/CitizenUpdate validation, /api/v1/citizens/options and the
dashboard leaderboard. The new FKs sit alongside it and stay NULL until World
Phase 2 backfills them, so every existing feature keeps working after this
migration runs.

Revision ID: a1f4c7b2e930
Revises: bd5026cd32f7
Create Date: 2026-08-21 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f4c7b2e930'
down_revision: Union[str, None] = 'bd5026cd32f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- cities ----
    # No `population` column on purpose: citizens.city_id is the source of
    # truth and population is counted at read time (same rule as wallets
    # being the only source of truth for money).
    op.create_table(
        'cities',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('region', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('world_x', sa.Float(), nullable=False),
        sa.Column('world_z', sa.Float(), nullable=False),
        sa.Column('radius', sa.Float(), nullable=False),
        sa.Column('is_capital', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_cities_name'),
    )

    # ---- neighborhoods ----
    op.create_table(
        'neighborhoods',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('city_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('offset_x', sa.Float(), nullable=False),
        sa.Column('offset_z', sa.Float(), nullable=False),
        sa.Column('width', sa.Float(), nullable=False),
        sa.Column('depth', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['city_id'], ['cities.id'],
            name='fk_neighborhoods_city_id',
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint('city_id', 'name', name='uq_neighborhoods_city_id_name'),
    )
    op.create_index(
        op.f('ix_neighborhoods_city_id'), 'neighborhoods', ['city_id'], unique=False
    )

    # ---- link citizens to the world (nullable = non-breaking) ----
    # ondelete='SET NULL': deleting a city must never cascade into deleting
    # citizens. The person survives; they just have no assigned location.
    op.add_column('citizens', sa.Column('city_id', sa.Integer(), nullable=True))
    op.add_column('citizens', sa.Column('neighborhood_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_citizens_city_id'), 'citizens', ['city_id'], unique=False)
    op.create_index(
        op.f('ix_citizens_neighborhood_id'), 'citizens', ['neighborhood_id'], unique=False
    )
    op.create_foreign_key(
        'fk_citizens_city_id', 'citizens', 'cities', ['city_id'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_citizens_neighborhood_id',
        'citizens',
        'neighborhoods',
        ['neighborhood_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    # Exact reverse order. All constraints are explicitly named above so MySQL
    # can drop them by name instead of relying on auto-generated identifiers.
    op.drop_constraint('fk_citizens_neighborhood_id', 'citizens', type_='foreignkey')
    op.drop_constraint('fk_citizens_city_id', 'citizens', type_='foreignkey')
    op.drop_index(op.f('ix_citizens_neighborhood_id'), table_name='citizens')
    op.drop_index(op.f('ix_citizens_city_id'), table_name='citizens')
    op.drop_column('citizens', 'neighborhood_id')
    op.drop_column('citizens', 'city_id')

    op.drop_index(op.f('ix_neighborhoods_city_id'), table_name='neighborhoods')
    op.drop_table('neighborhoods')
    op.drop_table('cities')
