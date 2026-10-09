from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CallAttempt


def get(db: Session, attempt_id: int) -> CallAttempt | None:
    return db.get(CallAttempt, attempt_id)


def in_campaign(db: Session, campaign_id: int) -> list[CallAttempt]:
    return list(db.scalars(select(CallAttempt).where(CallAttempt.campaign_id == campaign_id).order_by(CallAttempt.id)))


def by_provider_call(db: Session, provider: str, provider_call_id: str) -> CallAttempt | None:
    """Unique per provider (uq_call_attempts_provider_call)."""
    return db.scalar(select(CallAttempt).where(CallAttempt.provider == provider,
                                               CallAttempt.provider_call_id == provider_call_id))


OPEN_STATUSES = ("queued", "initiating", "ringing", "answered")


def open_real_before(db: Session, cutoff: datetime, campaign_id: int | None = None) -> list[CallAttempt]:
    """Real (non-simulated) calls with no final status that were started before `cutoff`."""
    q = select(CallAttempt).where(CallAttempt.is_simulated.is_(False), CallAttempt.status.in_(OPEN_STATUSES),
                                  CallAttempt.created_at <= cutoff).order_by(CallAttempt.id)
    if campaign_id:
        q = q.where(CallAttempt.campaign_id == campaign_id)
    return list(db.scalars(q))
