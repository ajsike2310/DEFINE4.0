from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IntentResult


def in_campaign(db: Session, campaign_id: int) -> list[IntentResult]:
    return list(db.scalars(select(IntentResult).where(IntentResult.campaign_id == campaign_id).order_by(IntentResult.id)))


def for_recipient(db: Session, recipient_id: int) -> list[IntentResult]:
    return list(db.scalars(select(IntentResult).where(IntentResult.recipient_id == recipient_id).order_by(IntentResult.id)))


def for_attempt(db: Session, attempt_id: int) -> IntentResult | None:
    """At most one (uq_intent_results_call_attempt_id)."""
    return db.scalar(select(IntentResult).where(IntentResult.call_attempt_id == attempt_id))


def latest_by_recipient(db: Session, campaign_ids: Iterable[int]) -> dict[int, IntentResult]:
    ids = list(campaign_ids)
    out: dict[int, IntentResult] = {}
    if ids:
        for ir in db.scalars(select(IntentResult).where(IntentResult.campaign_id.in_(ids)).order_by(IntentResult.id)):
            out[ir.recipient_id] = ir
    return out
