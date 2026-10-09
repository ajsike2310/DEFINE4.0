from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import Campaign, Recipient


def get(db: Session, campaign_id: int) -> Campaign | None:
    return db.get(Campaign, campaign_id)


def list_filtered(db: Session, *, status: str | None = None, event_id: int | None = None) -> list[Campaign]:
    q = select(Campaign).order_by(Campaign.id.desc())
    if status:
        q = q.where(Campaign.status == status)
    if event_id:
        q = q.where(Campaign.event_id == event_id)
    return list(db.scalars(q))


def with_participants(db: Session, event_id: int | None = None) -> list[Campaign]:
    """Campaigns with participants and their call attempts loaded in two extra queries (for the overview)."""
    q = select(Campaign).options(selectinload(Campaign.recipients).selectinload(Recipient.attempts)) \
        .order_by(Campaign.id.desc())
    if event_id:
        q = q.where(Campaign.event_id == event_id)
    return list(db.scalars(q))


def due_scheduled(db: Session, now: datetime) -> list[Campaign]:
    """Scheduled campaigns whose time has come (uses ix_campaigns_status_scheduled_at)."""
    return list(db.scalars(select(Campaign).where(Campaign.status == "scheduled", Campaign.scheduled_at <= now)
                           .order_by(Campaign.scheduled_at, Campaign.id)))


def running(db: Session) -> list[Campaign]:
    return list(db.scalars(select(Campaign).where(Campaign.status == "running").order_by(Campaign.id)))


def by_ids(db: Session, ids) -> dict[int, Campaign]:
    ids = list(ids)
    return {c.id: c for c in db.scalars(select(Campaign).where(Campaign.id.in_(ids)))} if ids else {}


def for_event(db: Session, event_id: int) -> list[Campaign]:
    return list(db.scalars(select(Campaign).where(Campaign.event_id == event_id).order_by(Campaign.id)))


def participant_counts(db: Session, campaign_ids: Sequence[int]) -> dict[int, int]:
    if not campaign_ids:
        return {}
    return dict(db.execute(select(Recipient.campaign_id, func.count()).where(Recipient.campaign_id.in_(campaign_ids))
                           .group_by(Recipient.campaign_id)).all())


def counts_by_event(db: Session, event_ids: Sequence[int]) -> dict[int, int]:
    if not event_ids:
        return {}
    return dict(db.execute(select(Campaign.event_id, func.count()).where(Campaign.event_id.in_(event_ids))
                           .group_by(Campaign.event_id)).all())


def count_for_event(db: Session, event_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Campaign).where(Campaign.event_id == event_id)) or 0
