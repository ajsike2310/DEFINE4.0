from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

# Stable names for every constraint and index, so migrations are deterministic and reviewable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UTCDateTime(TypeDecorator):
    """Store UTC; always return timezone-aware datetimes (SQLite drops tzinfo)."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed; use timezone-aware values")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value else None


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _apply_sqlite_pragmas(engine, *, file_database: bool) -> None:
    """Every new connection: enforce foreign keys, wait instead of failing on a busy file, and (for files) use
    write-ahead logging so readers never block the writer."""
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA temp_store=MEMORY")
        if file_database:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


def make_engine(url: str, *, enforce_foreign_keys: bool = True):
    """Create the engine. `enforce_foreign_keys=False` is only for migrations, which rebuild tables."""
    sqlite = url.startswith("sqlite")
    memory = ":memory:" in url
    if sqlite and url.startswith("sqlite:///") and not memory:
        from pathlib import Path
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {"connect_args": {"check_same_thread": False}} if sqlite else {}
    if memory:
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if sqlite and enforce_foreign_keys:
        _apply_sqlite_pragmas(engine, file_database=not memory)
    return engine


def make_session_factory(url: str):
    engine = make_engine(url)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
