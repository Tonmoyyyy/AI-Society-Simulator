"""add neighborhood column to citizens  (NO-OP — superseded by 2cdfcfa31200)

Revision ID: bd5026cd32f7
Revises: 2cdfcfa31200
Create Date: 2026-08-14 03:17:31.755763

WHY THIS REVISION DOES NOTHING
------------------------------
This migration was generated twice. Its original body was byte-identical to
its own parent, 2cdfcfa31200 — both added `citizens.neighborhood` and
`comments.parent_comment_id`, plus the same index and self-referential foreign
key. Running both in sequence is impossible: the second one died on a fresh
database with MySQL error 1060, "Duplicate column name 'neighborhood'".

That failure was not cosmetic. Because every later revision chains through
this one, `alembic upgrade head` never got past it, so a1f4c7b2e930
(cities / neighborhoods) and c3d8e5a91b47 (buildings / roads) were never
applied. The world tables only existed at runtime thanks to the
`Base.metadata.create_all` safety net in app/main.py, which meant Alembic's
recorded state and the real schema had permanently diverged.

WHY THE FILE IS KEPT INSTEAD OF DELETED
---------------------------------------
Any database that was already stamped with bd5026cd32f7 has that string in its
`alembic_version` table. Deleting the file would leave Alembic unable to
resolve that revision — "Can't locate revision identified by
'bd5026cd32f7'" — and the migration history would be unusable. Keeping the
revision with empty bodies preserves the chain for those databases while
letting a fresh database walk straight through to head.

The real work still lives in 2cdfcfa31200. Do not re-add it here.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'bd5026cd32f7'
down_revision: Union[str, None] = '2cdfcfa31200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally empty — see the module docstring. The columns this revision
    # used to add are created by 2cdfcfa31200, its immediate parent.
    pass


def downgrade() -> None:
    # Intentionally empty — 2cdfcfa31200.downgrade() owns the reversal.
    pass
