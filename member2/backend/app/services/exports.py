"""CSV exports of an event's data. Phone numbers are masked unless the caller explicitly asks otherwise."""
from sqlalchemy.orm import Session

from ..repositories import campaigns as campaigns_repo
from ..repositories import intents as intents_repo
from ..repositories import leads as leads_repo
from ..repositories import recipients as recipients_repo
from . import csv_io
from . import leads as lead_svc
from .events import mask


def participants_csv(db: Session, event_id: int, masked: bool = True) -> str:
    camps = {c.id: c for c in campaigns_repo.for_event(db, event_id)}
    rows = sorted(recipients_repo.filtered(db, event_id=event_id, with_attempts=True),
                  key=lambda r: (r.campaign_id, r.id))
    latest = intents_repo.latest_by_recipient(db, camps)
    out = []
    for r in rows:
        last = r.attempts[-1] if r.attempts else None
        ir = latest.get(r.id)
        out.append([r.campaign_id, camps[r.campaign_id].name, r.external_ref, r.name, csv_io.Verbatim(mask(r.phone) if masked else r.phone),
                    r.preferred_language, r.consent_status, "yes" if r.opted_out else "no", r.outcome, len(r.attempts),
                    last.status if last else "", ir.intent if ir else "", ir.method if ir else "",
                    "yes" if r.is_demo else "no"])
    return csv_io.to_csv(["campaign_id", "campaign", "participant_id", "name", "phone", "language", "consent", "opted_out",
                          "outcome", "calls", "last_call_status", "last_intent", "response_method", "sample_data"], out)


def leads_csv(db: Session, event_id: int, masked: bool = True) -> str:
    leads = sorted(leads_repo.for_event(db, event_id), key=lambda l: l.id)
    rmap = lead_svc.recipients_for(db, list(leads))
    out = []
    for l in leads:
        pts, _ = lead_svc.score(l)
        rec = rmap.get(l.recipient_id) if l.recipient_id else None
        out.append([l.id, l.name, csv_io.Verbatim(mask(l.phone) if masked else l.phone), l.email, l.source, l.interest, l.preferred_language,
                    l.consent_status, l.status, pts, rec.campaign_id if rec else "", "yes" if l.is_demo else "no"])
    return csv_io.to_csv(["lead_id", "name", "phone", "email", "source", "interest", "language", "consent", "status",
                          "readiness_score", "campaign_id", "sample_data"], out)
