"""Alembic environment.

Used two ways: by the app at start-up (core/migrate.py hands in a connection) and from the command line
(`alembic -c member2/backend/alembic.ini upgrade head`, which connects with DATABASE_URL / the app settings).
"""
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from member2.backend.app import models  # noqa: E402,F401  (register tables)
from member2.backend.app.core.config import get_settings  # noqa: E402
from member2.backend.app.core.db import Base  # noqa: E402

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                      render_as_batch=True, transactional_ddl=True)


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:                       # started by the app: it owns the connection and the transaction
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    from member2.backend.app.core.migrate import migration_engine
    engine = migration_engine(config.get_main_option("sqlalchemy.url") or get_settings().database_url)
    with engine.connect() as conn:
        _configure(conn)
        with context.begin_transaction():
            context.run_migrations()
        conn.commit()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline (SQL script) mode is not supported: SQLite migrations rebuild tables in Python")
run_migrations_online()
