"""Build API output models with batched counts (no per-row queries)."""
from collections.abc import Sequence

from sqlalchemy.orm import Session

from ..models import Campaign, Event
from ..repositories import campaigns as campaigns_repo
from ..schemas.api import CampaignOut, EventOut


def campaigns_out(db: Session, rows: Sequence[Campaign]) -> list[CampaignOut]:
    counts = campaigns_repo.participant_counts(db, [c.id for c in rows])
    out = []
    for c in rows:
        o = CampaignOut.model_validate(c)
        o.recipient_count = counts.get(c.id, 0)
        out.append(o)
    return out


def campaign_out(db: Session, c: Campaign) -> CampaignOut:
    return campaigns_out(db, [c])[0]


def events_out(db: Session, rows: Sequence[Event]) -> list[EventOut]:
    counts = campaigns_repo.counts_by_event(db, [e.id for e in rows])
    out = []
    for e in rows:
        o = EventOut.model_validate(e)
        o.campaign_count = counts.get(e.id, 0)
        out.append(o)
    return out


def event_out(db: Session, e: Event) -> EventOut:
    return events_out(db, [e])[0]
