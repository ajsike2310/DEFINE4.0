from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator


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
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_session_factory(url: str):
    if url.startswith("sqlite:///") and ":memory:" not in url:
        from pathlib import Path
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if ":memory:" in url:
        from sqlalchemy.pool import StaticPool
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
