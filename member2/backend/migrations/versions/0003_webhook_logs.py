"""webhook_logs: received provider callbacks (masked), for diagnosing a live integration

Adds one table (with its two indexes). Nothing existing is touched.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10
"""
from alembic import op

from member2.backend.migrations import rebuild

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    rebuild.ensure_tables(op.get_bind(), rebuild.load("v3"))     # creates only the tables that are missing


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS webhook_logs")
