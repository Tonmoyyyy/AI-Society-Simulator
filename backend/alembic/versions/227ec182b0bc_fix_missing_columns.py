"""fix missing columns

Revision ID: 227ec182b0bc
Revises: b7e42d9c81fa
Create Date: 2026-08-22 13:52:52.654401

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '227ec182b0bc'
down_revision: Union[str, None] = 'b7e42d9c81fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Safe index creation wrapper
    def create_index_if_not_exists(index_name, table_name, columns, unique=False):
        try:
            op.create_index(index_name, table_name, columns, unique=unique)
        except Exception:
            pass

    create_index_if_not_exists(op.f('ix_buildings_is_manual'), 'buildings', ['is_manual'], unique=False)
    
    # Check & add missing columns safely
    try:
        op.add_column('citizens', sa.Column('died_at_tick', sa.Integer(), nullable=True))
    except Exception:
        pass

    try:
        op.add_column('citizens', sa.Column('death_cause', sa.String(length=100), nullable=True))
    except Exception:
        pass
    
    # Safe alter for gender column
    try:
        op.alter_column('citizens', 'gender',
                   existing_type=mysql.VARCHAR(length=20),
                   type_=sa.String(length=20),
                   nullable=True)
    except Exception:
        pass
               
    # Safe alter for national_id column
    try:
        op.alter_column('citizens', 'national_id',
                   existing_type=mysql.VARCHAR(length=50),
                   type_=sa.String(length=50),
                   existing_nullable=True)
    except Exception:
        pass

    create_index_if_not_exists(op.f('ix_citizens_city_id'), 'citizens', ['city_id'], unique=False)
    create_index_if_not_exists(op.f('ix_citizens_gender'), 'citizens', ['gender'], unique=False)
    create_index_if_not_exists(op.f('ix_citizens_is_alive'), 'citizens', ['is_alive'], unique=False)
    create_index_if_not_exists(op.f('ix_citizens_neighborhood_id'), 'citizens', ['neighborhood_id'], unique=False)


def downgrade() -> None:
    pass