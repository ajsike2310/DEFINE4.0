from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import Campaign, Recipient

ATTENTION_OUTCOMES = ("unclear", "human_required", "callback_requested", "information_requested", "no_response")


def get(db: Session, recipient_id: int) -> Recipient | None:
    return db.get(Recipient, recipient_id)


def in_campaign(db: Session, campaign_id: int, outcome: str | None = None) -> list[Recipient]:
    q = select(Recipient).where(Recipient.campaign_id == campaign_id).order_by(Recipient.id)
    if outcome:
        q = q.where(Recipient.outcome == outcome)
    return list(db.scalars(q))


def phones_in_campaign(db: Session, campaign_id: int) -> set[str]:
    return set(db.scalars(select(Recipient.phone).where(Recipient.campaign_id == campaign_id)))


def by_ids(db: Session, ids: Iterable[int]) -> dict[int, Recipient]:
    ids = set(ids)
    return {r.id: r for r in db.scalars(select(Recipient).where(Recipient.id.in_(ids)))} if ids else {}


def filtered(db: Session, *, outcome=None, language=None, event_id=None, campaign_id=None, attention=False,
             opted_out=None, with_attempts=False, limit: int | None = None, offset: int = 0) -> list[Recipient]:
    """Newest first. With limit/offset the paging happens in SQL."""
    q = select(Recipient).order_by(Recipient.id.desc())
    if event_id:
        q = q.join(Campaign, Campaign.id == Recipient.campaign_id).where(Campaign.event_id == event_id)
    if campaign_id:
        q = q.where(Recipient.campaign_id == campaign_id)
    if outcome:
        q = q.where(Recipient.outcome == outcome)
    if language:
        q = q.where(Recipient.preferred_language == language)
    if attention:
        q = q.where(Recipient.outcome.in_(ATTENTION_OUTCOMES), Recipient.opted_out.is_(False))
    if opted_out is not None:
        q = q.where(Recipient.opted_out.is_(opted_out))
    if with_attempts:
        q = q.options(selectinload(Recipient.attempts))
    if limit is not None:
        q = q.offset(offset).limit(limit)
    return list(db.scalars(q))


def _scope(stmt, event_id: int, is_demo: bool):
    """Records that count for `event_id`: its own, plus (for real data) every other non-sample campaign."""
    stmt = stmt.join(Campaign, Campaign.id == Recipient.campaign_id)
    return stmt.where(Campaign.event_id == event_id) if is_demo \
        else stmt.where(or_(Campaign.event_id == event_id, Campaign.is_demo.is_(False)))


def opted_out_phones(db: Session, phones: Iterable[str], *, event_id: int, is_demo: bool) -> set[str]:
    """Which of these numbers belong to a participant who opted out or revoked consent, within scope."""
    wanted = set(phones)
    if not wanted:
        return set()
    stmt = select(Recipient.phone).where(Recipient.phone.in_(wanted),
                                         or_(Recipient.opted_out.is_(True), Recipient.consent_status == "revoked"))
    return set(db.scalars(_scope(stmt, event_id, is_demo)))


def still_contactable_with_phone(db: Session, phone: str, *, exclude_id: int, event_id: int, is_demo: bool) -> list[Recipient]:
    """Other participant rows with this number that are not yet opted out, within scope."""
    stmt = select(Recipient).where(Recipient.phone == phone, Recipient.id != exclude_id, Recipient.opted_out.is_(False))
    return list(db.scalars(_scope(stmt, event_id, is_demo)))
