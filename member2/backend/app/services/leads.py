"""Lead generation: capture, transparent scoring, conversion into campaign participants.

Rules (see docs/DECISIONS.md #16):
- Leads are self-supplied (registration form), organiser-imported or typed in. Nothing is scraped or bought.
- A lead whose consent is revoked is never converted and never called.
- The score is a transparent "contact readiness" checklist, NOT a prediction of attendance or conversion.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Campaign, Lead, Recipient

SOURCE_POINTS = {"registration_form": 25, "referral": 20, "walk_in": 20, "csv_import": 10, "manual": 10}
SOURCE_LABEL = {"registration_form": "registration form", "referral": "referral", "walk_in": "walk-in",
                "csv_import": "CSV import", "manual": "added by hand"}


def score(lead: Lead) -> tuple[int, list[str]]:
    """Contact readiness 0-100 as a sum of visible checks. Revoked consent is always 0."""
    if lead.consent_status == "revoked":
        return 0, ["consent revoked: do not contact"]
    pts, why = 0, []
    if lead.consent_status == "granted":
        pts += 40
        why.append("consent granted (+40)")
    else:
        why.append("consent not recorded (+0)")
    src = SOURCE_POINTS.get(lead.source, 10)
    pts += src
    why.append(f"came from {SOURCE_LABEL.get(lead.source, lead.source)} (+{src})")
    if lead.email:
        pts += 10
        why.append("email on file (+10)")
    if lead.preferred_language:
        pts += 10
        why.append("language known (+10)")
    if lead.interest:
        pts += 10
        why.append("interest stated (+10)")
    pts += 5
    why.append("valid phone number (+5)")
    return min(pts, 100), why


def lead_out(db: Session, lead: Lead):
    from ..schemas.api import LeadOut
    out = LeadOut.model_validate(lead)
    out.score, out.score_reasons = score(lead)
    if lead.recipient_id:
        r = db.get(Recipient, lead.recipient_id)
        if r:
            out.campaign_id, out.recipient_outcome = r.campaign_id, r.outcome
    return out


def convert(db: Session, campaign: Campaign, leads: list[Lead]) -> dict:
    """Turn leads into participants of `campaign` (same event). Returns {converted, skipped:[{lead_id, reason}]}."""
    have = set(db.scalars(select(Recipient.phone).where(Recipient.campaign_id == campaign.id)))
    converted, skipped = 0, []
    for lead in leads:
        reason = None
        if lead.event_id != campaign.event_id:
            reason = "lead belongs to a different event"
        elif lead.consent_status == "revoked":
            reason = "consent revoked"
        elif lead.status == "converted" and lead.recipient_id:
            reason = "already converted"
        elif lead.phone in have:
            reason = "already a participant in this campaign"
        elif campaign.require_consent and lead.consent_status != "granted":
            reason = "consent not recorded (this campaign requires it)"
        if reason:
            skipped.append({"lead_id": lead.id, "reason": reason})
            continue
        lang = lead.preferred_language if lead.preferred_language in campaign.languages else None
        r = Recipient(campaign_id=campaign.id, name=lead.name, phone=lead.phone, preferred_language=lang,
                      segment=lead.interest or "lead", consent_status=lead.consent_status, is_demo=campaign.is_demo)
        db.add(r)
        db.flush()
        lead.recipient_id, lead.status = r.id, "converted"
        have.add(lead.phone)
        converted += 1
    db.commit()
    return {"converted": converted, "skipped": skipped}


def summary(db: Session, event_id: int) -> dict:
    leads = list(db.scalars(select(Lead).where(Lead.event_id == event_id)))
    total = len(leads)
    by_status = {s: 0 for s in ("new", "contacted", "qualified", "converted", "lost")}
    by_source: dict[str, dict] = {}
    for l in leads:
        by_status[l.status] = by_status.get(l.status, 0) + 1
        row = by_source.setdefault(l.source, {"source": l.source, "leads": 0, "converted": 0, "consented": 0})
        row["leads"] += 1
        row["converted"] += 1 if l.status == "converted" else 0
        row["consented"] += 1 if l.consent_status == "granted" else 0
    for row in by_source.values():
        row["conversion_rate"] = round(row["converted"] / row["leads"], 4)   # converted / leads from that source
    consented = sum(1 for l in leads if l.consent_status == "granted")
    return {"total": total, "by_status": by_status, "consented": consented,
            "consent_rate": round(consented / total, 4) if total else None,
            "conversion_rate": round(by_status["converted"] / total, 4) if total else None,   # converted / all leads
            "ready_to_convert": sum(1 for l in leads if l.consent_status == "granted"
                                    and l.status in ("new", "contacted", "qualified")),
            "by_source": sorted(by_source.values(), key=lambda r: -r["leads"])}
