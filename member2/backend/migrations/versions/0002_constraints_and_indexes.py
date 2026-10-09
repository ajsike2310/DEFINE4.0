"""constraints, foreign-key rules, server defaults and indexes

* CHECK constraints on every closed vocabulary and numeric range, and on phone format.
* Foreign keys with explicit ON DELETE rules (enforced at runtime: PRAGMA foreign_keys=ON).
* One classified response per call attempt; one open human-review follow-up per participant; a provider call id
  identifies one attempt.
* Composite indexes for the hot queries; redundant single-column indexes dropped.
* `follow_ups.updated_at` added (backfilled from `created_at`); server defaults on defaulted columns.

Tables are rebuilt (see migrations/rebuild.py). If existing rows break a new rule the migration stops with a message and
changes nothing.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09
"""
from alembic import op

from member2.backend.migrations import rebuild

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    rebuild.rebuild(op.get_bind(), rebuild.load("v2"), copy_from={"follow_ups": {"updated_at": "created_at"}})


def downgrade() -> None:
    rebuild.rebuild(op.get_bind(), rebuild.load("legacy"))
