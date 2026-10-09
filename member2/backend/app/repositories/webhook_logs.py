from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import WebhookLog


def recent(db: Session, *, provider: str | None = None, ok: bool | None = None, limit: int = 50) -> list[WebhookLog]:
    q = select(WebhookLog).order_by(WebhookLog.id.desc()).limit(limit)
    if provider:
        q = q.where(WebhookLog.provider == provider)
    if ok is not None:
        q = q.where(WebhookLog.ok.is_(ok))
    return list(db.scalars(q))


def counts_since(db: Session, since: datetime, provider: str | None = None) -> dict[str, int]:
    """{endpoint: callbacks received since `since`} (uses ix_webhook_logs_received_at)."""
    q = select(WebhookLog.endpoint, func.count()).where(WebhookLog.received_at >= since).group_by(WebhookLog.endpoint)
    if provider:
        q = q.where(WebhookLog.provider == provider)
    return dict(db.execute(q).all())


def delete_older_than(db: Session, cutoff: datetime) -> int:
    return db.execute(delete(WebhookLog).where(WebhookLog.received_at < cutoff)).rowcount or 0
