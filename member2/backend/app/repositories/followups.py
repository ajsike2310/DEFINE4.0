from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import CallAttempt, Campaign, FollowUp, IntentResult, Recipient

OPEN = ("pending", "scheduled")


def get(db: Session, followup_id: int) -> FollowUp | None:
    return db.get(FollowUp, followup_id)


def filtered(db: Session, *, campaign_id: int | None = None, status: str | None = None) -> list[FollowUp]:
    q = select(FollowUp).order_by(FollowUp.id.desc())
    if campaign_id:
        q = q.where(FollowUp.campaign_id == campaign_id)
    if status:
        q = q.where(FollowUp.status == status)
    return list(db.scalars(q))


def for_recipient(db: Session, recipient_id: int) -> list[FollowUp]:
    return list(db.scalars(select(FollowUp).where(FollowUp.recipient_id == recipient_id).order_by(FollowUp.id)))


def open_for_recipient(db: Session, recipient_id: int) -> list[FollowUp]:
    return list(db.scalars(select(FollowUp).where(FollowUp.recipient_id == recipient_id, FollowUp.status.in_(OPEN))))


def open_review(db: Session, recipient_id: int) -> FollowUp | None:
    """The participant's open human-review task, if any (at most one: uq_follow_ups_open_review)."""
    return db.scalar(select(FollowUp).where(FollowUp.recipient_id == recipient_id,
                                            FollowUp.action_type == "human_review", FollowUp.status.in_(OPEN)))


def send_information_for_intent(db: Session, intent_id: int) -> FollowUp | None:
    return db.scalar(select(FollowUp).where(FollowUp.source_intent_id == intent_id,
                                            FollowUp.action_type == "send_information"))


def queue_rows(db: Session, *, event_id: int | None = None, campaign_id: int | None = None, include_closed: bool = False):
    """Follow-ups with their campaign, participant, source response and call in ONE query (plus one for attempts)."""
    q = (select(FollowUp, Campaign, Recipient, IntentResult, CallAttempt)
         .join(Campaign, Campaign.id == FollowUp.campaign_id)
         .join(Recipient, Recipient.id == FollowUp.recipient_id)
         .outerjoin(IntentResult, IntentResult.id == FollowUp.source_intent_id)
         .outerjoin(CallAttempt, CallAttempt.id == IntentResult.call_attempt_id)
         .options(selectinload(Recipient.attempts)))
    if not include_closed:
        q = q.where(FollowUp.status.in_(OPEN))
    if campaign_id:
        q = q.where(FollowUp.campaign_id == campaign_id)
    if event_id:
        q = q.where(Campaign.event_id == event_id)
    return db.execute(q).all()
