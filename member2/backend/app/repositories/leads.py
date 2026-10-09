from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Lead


def get(db: Session, lead_id: int) -> Lead | None:
    return db.get(Lead, lead_id)


def by_ids(db: Session, ids: Iterable[int]) -> list[Lead]:
    ids = list(ids)
    return list(db.scalars(select(Lead).where(Lead.id.in_(ids)))) if ids else []


def for_event(db: Session, event_id: int, *, status=None, source=None, q: str | None = None) -> list[Lead]:
    stmt = select(Lead).where(Lead.event_id == event_id)
    if status:
        stmt = stmt.where(Lead.status == status)
    if source:
        stmt = stmt.where(Lead.source == source)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(Lead.name.ilike(like), Lead.email.ilike(like)))
    return list(db.scalars(stmt))


def phones_in_event(db: Session, event_id: int) -> set[str]:
    return set(db.scalars(select(Lead.phone).where(Lead.event_id == event_id)))


def _scope(stmt, event_id: int, is_demo: bool):
    return stmt.where(Lead.event_id == event_id) if is_demo \
        else stmt.where(or_(Lead.event_id == event_id, Lead.is_demo.is_(False)))


def revoked_phones(db: Session, phones: Iterable[str], *, event_id: int, is_demo: bool) -> set[str]:
    wanted = set(phones)
    if not wanted:
        return set()
    stmt = select(Lead.phone).where(Lead.phone.in_(wanted), Lead.consent_status == "revoked")
    return set(db.scalars(_scope(stmt, event_id, is_demo)))


def with_consent_not_revoked(db: Session, phone: str, *, event_id: int, is_demo: bool) -> list[Lead]:
    stmt = select(Lead).where(Lead.phone == phone, Lead.consent_status != "revoked")
    return list(db.scalars(_scope(stmt, event_id, is_demo)))
