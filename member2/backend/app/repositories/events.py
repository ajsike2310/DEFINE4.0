from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Event


def get(db: Session, event_id: int) -> Event | None:
    return db.get(Event, event_id)


def list_all(db: Session) -> list[Event]:
    return list(db.scalars(select(Event).order_by(Event.id)))


def by_ids(db: Session, ids) -> list[Event]:
    ids = list(ids)
    return list(db.scalars(select(Event).where(Event.id.in_(ids)).order_by(Event.id))) if ids else []
