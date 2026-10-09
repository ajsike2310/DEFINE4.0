"""baseline: the schema every database had before migrations existed

Databases created by earlier builds (via create_all) are stamped with this revision, so it must reproduce their
schema exactly; tests compare it against a frozen dump.

Revision ID: 0001
Revises:
Create Date: 2026-10-09
"""
from alembic import op

from member2.backend.migrations import rebuild

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    rebuild.ensure_tables(op.get_bind(), rebuild.load("legacy"))


def downgrade() -> None:
    rebuild.drop_all(op.get_bind(), rebuild.load("legacy"))
