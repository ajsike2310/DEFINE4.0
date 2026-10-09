"""Schema management: run Alembic at start-up, adopt databases that predate migrations, back up before changes.

A file database is always brought to the latest revision when the app starts:
  * empty database            -> create everything (upgrade from nothing)
  * database without a version table but with our tables (made by an earlier build) -> missing legacy tables are
                                 added, it is stamped as the baseline revision, then upgraded
  * versioned database        -> upgrade
Before any change to a database that already holds tables, a consistent copy is written next to it (data/backups).
In-memory databases (tests) are created directly from the models; the drift test proves both routes give the same schema.
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event

from ...migrations import rebuild

log = logging.getLogger("migrate")
BACKEND = Path(__file__).resolve().parents[2]
BASELINE = "0001"
KEEP_BACKUPS = 10


def migration_engine(url: str):
    """An engine for migrations: foreign keys OFF (tables are rebuilt) and explicit BEGIN so DDL is transactional."""
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _autocommit_off(dbapi_conn, _record):
        dbapi_conn.isolation_level = None       # we emit BEGIN ourselves

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    return engine


def alembic_config(connection=None) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def status(engine) -> dict:
    """Where this database is relative to the code. In-memory databases are created from the models directly."""
    head = head_revision()
    if ":memory:" in str(engine.url):
        return {"managed_by": "create_all (in-memory)", "current": head, "head": head, "up_to_date": True}
    with engine.connect() as conn:
        current = current_revision(conn)
    return {"managed_by": "alembic", "current": current, "head": head, "up_to_date": current == head}


def _file_path(url: str) -> Path | None:
    return Path(url.removeprefix("sqlite:///")) if url.startswith("sqlite:///") and ":memory:" not in url else None


def backup_database(url: str, label: str = "manual", keep: int = KEEP_BACKUPS) -> Path:
    """Consistent online copy (SQLite backup API; safe while the app is running). Returns the new file."""
    src = _file_path(url)
    if src is None or not src.exists():
        raise ValueError("only an existing SQLite file can be backed up")
    dest_dir = src.parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{src.stem}-{label}-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    source, target = sqlite3.connect(src), sqlite3.connect(dest)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    old = sorted(dest_dir.glob(f"{src.stem}-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]
    for p in old:
        p.unlink(missing_ok=True)
    return dest


def _reject_ancient(conn) -> None:
    cols = lambda t: {r[1] for r in conn.exec_driver_sql(f'PRAGMA table_info("{t}")')}   # noqa: E731
    have = rebuild.existing_tables(conn)
    if ("campaigns" in have and "event_id" not in cols("campaigns")) \
            or ("call_attempts" in have and "mode" not in cols("call_attempts")):
        raise RuntimeError("Database was created by an older version (no events) that cannot be migrated "
                           "automatically: stop the app and delete the data/ folder (or point DATABASE_URL at a "
                           "new file).")


def upgrade_database(url: str, target: str = "head") -> dict:
    """Bring a file database to `target`. Returns what happened (for logs and tests)."""
    engine = migration_engine(url)
    info: dict = {"backup": None, "adopted_legacy": False, "from": None}
    try:
        with engine.connect() as conn:
            tables = rebuild.existing_tables(conn)
            legacy = bool(tables) and "alembic_version" not in tables
            if legacy:
                _reject_ancient(conn)
            info["from"] = BASELINE if legacy else (current_revision(conn) if tables else None)
            conn.rollback()
        goal = head_revision() if target == "head" else target
        if tables and info["from"] != goal and _file_path(url) is not None:
            info["backup"] = str(backup_database(url, label=f"pre-{goal}"))
            log.info("database backed up to %s before migrating", info["backup"])
        with engine.connect() as conn:
            cfg = alembic_config(conn)
            if legacy:
                rebuild.ensure_tables(conn, rebuild.load("legacy"))      # tables added after the first release
                command.stamp(cfg, BASELINE)
                info["adopted_legacy"] = True
            command.upgrade(cfg, target)
            conn.commit()
            info["to"] = current_revision(conn)
            conn.rollback()
    finally:
        engine.dispose()
    if info["from"] != info["to"]:
        log.info("database migrated %s -> %s%s", info["from"], info["to"], " (adopted pre-migration database)" if info["adopted_legacy"] else "")
    return info


def downgrade_database(url: str, target: str) -> dict:
    engine = migration_engine(url)
    try:
        backup = str(backup_database(url, label=f"pre-downgrade-{target}")) if _file_path(url) else None
        with engine.connect() as conn:
            command.downgrade(alembic_config(conn), target)
            conn.commit()
            now = current_revision(conn)
            conn.rollback()
    finally:
        engine.dispose()
    return {"backup": backup, "to": now}
