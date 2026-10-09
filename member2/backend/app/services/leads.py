"""Lead generation: capture, transparent scoring, conversion into campaign participants.

Rules (see docs/DECISIONS.md #16):
- Leads are self-supplied (registration form), organiser-imported or typed in. Nothing is scraped or bought.
- A lead whose consent is revoked is never converted and never called.
- A number that opted out anywhere in scope is never converted (opt-out wins).
- The score is a transparent "contact readiness" checklist, NOT a prediction of attendance or conversion.
"""
from collections import Counter

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import ApiError
from ..models import Campaign, Event, ImportRun, Lead, Recipient
from ..repositories import leads as leads_repo
from ..repositories import recipients as recipients_repo
from ..schemas.api import LEAD_SOURCES, LeadIn, LeadOut, LeadPatch
from . import csv_io, suppression

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


def recipients_for(db: Session, leads: list[Lead]) -> dict[int, Recipient]:
    return recipients_repo.by_ids(db, (l.recipient_id for l in leads if l.recipient_id))


def lead_out(db: Session, lead: Lead, recipients: dict[int, Recipient] | None = None) -> LeadOut:
    out = LeadOut.model_validate(lead)
    out.score, out.score_reasons = score(lead)
    if lead.recipient_id:
        r = recipients.get(lead.recipient_id) if recipients is not None else db.get(Recipient, lead.recipient_id)
        if r:
            out.campaign_id, out.recipient_outcome = r.campaign_id, r.outcome
    return out


def capture(db: Session, ev: Event, body: LeadIn) -> LeadOut:
    lead = Lead(event_id=ev.id, is_demo=ev.is_demo, **body.model_dump())
    db.add(lead)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "duplicate", "this phone number is already a lead for this event")
    return lead_out(db, lead)


def list_for_event(db: Session, event_id: int, *, status=None, source=None, q=None, limit=300) -> list[LeadOut]:
    rows = leads_repo.for_event(db, event_id, status=status, source=source, q=q)
    rmap = recipients_for(db, rows)
    out = [lead_out(db, x, rmap) for x in rows]
    out.sort(key=lambda o: (-o.score, -o.id))      # most contact-ready first
    return out[:limit]


def import_csv(db: Session, ev: Event, raw: bytes, filename: str, consent_confirmed: bool, source: str) -> dict:
    """CSV columns: name,phone[,email][,interest][,language]. consent_confirmed=true records consent=granted
    for every row - only tick it if the organiser holds consent for these contacts."""
    if source not in LEAD_SOURCES:
        raise ApiError(422, "validation_error", f"source must be one of {sorted(LEAD_SOURCES)}")
    try:
        rows = csv_io.read_rows(raw, header_hint="CSV needs header columns: name, phone (optional: email, interest, language)")
    except csv_io.CsvError as exc:
        raise ApiError(exc.status, exc.code, exc.message)
    have = leads_repo.phones_in_event(db, ev.id)
    imported, errors = 0, []
    for line, row in enumerate(rows, start=2):
        try:
            body = LeadIn(name=(row.get("name") or "").strip(), phone=row.get("phone") or "",
                          email=row.get("email"), interest=(row.get("interest") or "").strip() or None,
                          preferred_language=(row.get("language") or "").strip() or None, source=source,
                          consent_status="granted" if consent_confirmed else "unknown")
            if body.phone in have:
                raise ValueError("duplicate phone")
            db.add(Lead(event_id=ev.id, is_demo=ev.is_demo, **body.model_dump()))
            have.add(body.phone)
            imported += 1
        except (ValidationError, ValueError) as exc:
            errors.append({"line": line, "error": csv_io.row_error(exc)})
    db.add(ImportRun(kind="leads", event_id=ev.id, filename=(filename or "")[:200], rows_total=len(rows),
                     imported=imported, rejected=len(errors), is_demo=ev.is_demo,
                     reasons=dict(Counter(e["error"] for e in errors))))
    db.commit()
    return {"imported": imported, "rejected": len(errors), "errors": errors[:50]}


def patch(db: Session, lead: Lead, body: LeadPatch) -> LeadOut:
    data = body.model_dump(exclude_unset=True)
    if lead.status == "converted" and data.get("status") not in (None, "converted"):
        raise ApiError(409, "invalid_state", "a converted lead is now a participant; manage it in its campaign")
    if data.get("status") == "converted":
        raise ApiError(422, "validation_error", "use the convert action to turn a lead into a participant")
    for k, v in data.items():
        setattr(lead, k, v)
    if lead.consent_status == "revoked":      # opt-out wins: a revoked lead is closed and, if converted, opted out
        if not lead.recipient_id:
            lead.status = "lost"
        else:
            r = db.get(Recipient, lead.recipient_id)
            if r:
                r.opted_out, r.outcome, r.consent_status = True, "opted_out", "revoked"
                suppression.record_opt_out(db, r)
    db.commit()
    return lead_out(db, lead)


def convert(db: Session, campaign: Campaign, leads: list[Lead]) -> dict:
    """Turn leads into participants of `campaign` (same event). Returns {converted, skipped:[{lead_id, reason}]}."""
    have = recipients_repo.phones_in_campaign(db, campaign.id)
    blocked = suppression.find_suppressed(db, [l.phone for l in leads], event_id=campaign.event_id, is_demo=campaign.is_demo)
    converted, skipped = 0, []
    for lead in leads:
        reason = None
        if lead.event_id != campaign.event_id:
            reason = "lead belongs to a different event"
        elif lead.consent_status == "revoked":
            reason = "consent revoked"
        elif lead.phone in blocked:
            reason = "number opted out earlier"
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
    leads = leads_repo.for_event(db, event_id)
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
