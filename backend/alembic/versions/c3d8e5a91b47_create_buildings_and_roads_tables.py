"""create buildings and roads tables

World Phase 2. Purely ADDITIVE — creates two new tables and touches nothing
that already exists:

  - `buildings`: every generated structure (houses, shops, factories, government
    offices, the Parliament, the Presidential Palace), positioned as an offset
    from its city's centre.
  - `roads`: straight road segments in absolute world coordinates.

NO existing table is altered. In particular `citizens` is NOT given a
`home_building_id` column — the citizen↔house link lives on the building side
(`buildings.owner_citizen_id`), so the citizens table keeps exactly the shape it
had after World Phase 1 and every existing citizen API keeps working unchanged.

FK delete behaviour, and why:
  buildings.city_id          -> CASCADE  (a building cannot outlive its city)
  buildings.neighborhood_id  -> SET NULL (a landmark can sit on city land)
  buildings.owner_citizen_id -> SET NULL (deleting a person must not demolish
                                          a house, and must never cascade)
  buildings.shop_id          -> SET NULL (a closed shop leaves the unit empty)
  roads.city_id              -> SET NULL (highways belong to no single city)

Revision ID: c3d8e5a91b47
Revises: a1f4c7b2e930
Create Date: 2026-08-21 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d8e5a91b47'
down_revision: Union[str, None] = 'a1f4c7b2e930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- buildings ----
    op.create_table(
        'buildings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('city_id', sa.Integer(), nullable=False),
        sa.Column('neighborhood_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=True),
        sa.Column('owner_citizen_id', sa.Integer(), nullable=True),
        sa.Column('shop_id', sa.Integer(), nullable=True),
        sa.Column('offset_x', sa.Float(), nullable=False),
        sa.Column('offset_z', sa.Float(), nullable=False),
        sa.Column('width', sa.Float(), nullable=False),
        sa.Column('depth', sa.Float(), nullable=False),
        sa.Column('height', sa.Float(), nullable=False),
        sa.Column('rotation', sa.Float(), nullable=False),
        sa.Column('is_landmark', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['city_id'], ['cities.id'],
            name='fk_buildings_city_id',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['neighborhood_id'], ['neighborhoods.id'],
            name='fk_buildings_neighborhood_id',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['owner_citizen_id'], ['citizens.id'],
            name='fk_buildings_owner_citizen_id',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['shop_id'], ['shops.id'],
            name='fk_buildings_shop_id',
            ondelete='SET NULL',
        ),
    )
    op.create_index(op.f('ix_buildings_city_id'), 'buildings', ['city_id'], unique=False)
    op.create_index(
        op.f('ix_buildings_neighborhood_id'), 'buildings', ['neighborhood_id'], unique=False
    )
    op.create_index(op.f('ix_buildings_type'), 'buildings', ['type'], unique=False)
    op.create_index(
        op.f('ix_buildings_owner_citizen_id'), 'buildings', ['owner_citizen_id'], unique=False
    )
    op.create_index(op.f('ix_buildings_shop_id'), 'buildings', ['shop_id'], unique=False)

    # ---- roads ----
    op.create_table(
        'roads',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('city_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=120), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('start_x', sa.Float(), nullable=False),
        sa.Column('start_z', sa.Float(), nullable=False),
        sa.Column('end_x', sa.Float(), nullable=False),
        sa.Column('end_z', sa.Float(), nullable=False),
        sa.Column('width', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['city_id'], ['cities.id'],
            name='fk_roads_city_id',
            ondelete='SET NULL',
        ),
    )
    op.create_index(op.f('ix_roads_city_id'), 'roads', ['city_id'], unique=False)
    op.create_index(op.f('ix_roads_kind'), 'roads', ['kind'], unique=False)


def downgrade() -> None:
    # Exact reverse order. Every constraint above is explicitly named so MySQL
    # can drop it by name instead of relying on auto-generated identifiers.
    op.drop_index(op.f('ix_roads_kind'), table_name='roads')
    op.drop_index(op.f('ix_roads_city_id'), table_name='roads')
    op.drop_table('roads')

    op.drop_index(op.f('ix_buildings_shop_id'), table_name='buildings')
    op.drop_index(op.f('ix_buildings_owner_citizen_id'), table_name='buildings')
    op.drop_index(op.f('ix_buildings_type'), table_name='buildings')
    op.drop_index(op.f('ix_buildings_neighborhood_id'), table_name='buildings')
    op.drop_index(op.f('ix_buildings_city_id'), table_name='buildings')
    op.drop_table('buildings')
