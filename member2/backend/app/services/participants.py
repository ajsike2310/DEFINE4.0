"""Participants of a campaign: add, import, reuse, list, history, opt-out. HTTP-free (raises ApiError)."""
from collections import Counter

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import ApiError
from ..models import Campaign, ImportRun, Recipient
from ..repositories import attempts as attempts_repo
from ..repositories import campaigns as campaigns_repo
from ..repositories import followups as followups_repo
from ..repositories import intents as intents_repo
from ..repositories import recipients as recipients_repo
from ..schemas.api import AttemptOut, FollowUpOut, IntentOut, RecipientIn, RecipientOut
from . import campaigns as campaign_svc
from . import csv_io, suppression

ACTIVE_STATUSES = ("draft", "scheduled", "running")


def _build(db: Session, c: Campaign, body: RecipientIn, *, opted_out: bool = False) -> Recipient:
    if c.status not in ACTIVE_STATUSES:
        raise ApiError(409, "invalid_state", f"cannot add recipients to a {c.status} campaign")
    if body.preferred_language and body.preferred_language not in c.languages:
        raise ApiError(422, "validation_error", "preferred_language is not enabled for this campaign")
    if not opted_out and suppression.is_suppressed(db, body.phone, event_id=c.event_id, is_demo=c.is_demo):
        raise ApiError(409, "suppressed", suppression.SUPPRESSED_REASON)
    r = Recipient(campaign_id=c.id, is_demo=c.is_demo, **body.model_dump())
    if opted_out:
        r.opted_out, r.outcome, r.consent_status = True, "opted_out", "revoked"
    db.add(r)
    return r


def add(db: Session, c: Campaign, body: RecipientIn) -> Recipient:
    r = _build(db, c, body)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "duplicate", "this phone number is already in the campaign")
    return r


def import_csv(db: Session, c: Campaign, raw: bytes, filename: str, consent_confirmed: bool) -> dict:
    """CSV columns: name,phone[,participant_id][,language][,segment][,opted_out]. consent_confirmed=true marks
    rows consent=granted; rows with opted_out=yes/true/1 are imported as opted out (never called). Numbers that
    opted out anywhere else in scope are rejected (opt-out wins)."""
    try:
        rows = csv_io.read_rows(raw, header_hint="CSV needs header columns: name, phone (optional: language, segment)")
    except csv_io.CsvError as exc:
        raise ApiError(exc.status, exc.code, exc.message)
    existing = recipients_repo.phones_in_campaign(db, c.id)
    imported, errors = 0, []
    for line, row in enumerate(rows, start=2):
        try:
            body = RecipientIn(name=(row.get("name") or "").strip(), phone=row.get("phone") or "",
                               external_ref=(row.get("participant_id") or "").strip() or None,
                               preferred_language=(row.get("language") or "").strip() or None,
                               segment=(row.get("segment") or "").strip() or None,
                               consent_status="granted" if consent_confirmed else "unknown")
            if body.phone in existing:
                raise ValueError("duplicate phone")
            opt = (row.get("opted_out") or "").strip().lower() in ("yes", "true", "1", "y")
            _build(db, c, body, opted_out=opt)
            existing.add(body.phone)
            imported += 1
        except (ValidationError, ValueError, ApiError) as exc:
            errors.append({"line": line, "error": csv_io.row_error(exc)})
    db.add(ImportRun(kind="participants", event_id=c.event_id, campaign_id=c.id, filename=(filename or "")[:200],
                     rows_total=len(rows), imported=imported, rejected=len(errors), is_demo=c.is_demo,
                     reasons=dict(Counter(e["error"] for e in errors))))
    db.commit()
    return {"imported": imported, "rejected": len(errors), "errors": errors[:50]}


def copy_from(db: Session, c: Campaign, src: Campaign) -> dict:
    """Reuse the eligible participants of another campaign of the SAME event. Opted-out and consent-revoked
    participants (here or anywhere in scope) are never copied; consent/language/ref carry over."""
    if c.event_id != src.event_id:
        raise ApiError(422, "different_event", "source campaign belongs to a different event")
    if c.id == src.id:
        raise ApiError(422, "validation_error", "source and target are the same campaign")
    have = recipients_repo.phones_in_campaign(db, c.id)
    blocked = suppression.find_suppressed(db, [r.phone for r in src.recipients], event_id=c.event_id, is_demo=c.is_demo)
    copied = skipped = 0
    for r in src.recipients:
        if r.phone in have or r.opted_out or r.consent_status == "revoked" or r.phone in blocked:
            skipped += 1
            continue
        lang = r.preferred_language if r.preferred_language in c.languages else None
        db.add(Recipient(campaign_id=c.id, external_ref=r.external_ref, name=r.name, phone=r.phone,
                         preferred_language=lang, segment=r.segment, consent_status=r.consent_status, is_demo=c.is_demo))
        copied += 1
    db.commit()
    return {"copied": copied, "skipped": skipped}


def opt_out(db: Session, r: Recipient) -> Recipient:
    """Operator-recorded opt-out (e.g. received outside the call). Cancels open follow-ups and applies to every
    other record of the same number in scope."""
    r.opted_out, r.consent_status, r.outcome = True, "revoked", "opted_out"
    for fu in followups_repo.open_for_recipient(db, r.id):
        fu.status, fu.note = "cancelled", "recipient opted out"
    suppression.record_opt_out(db, r)
    db.commit()
    return r


def list_filtered(db: Session, *, outcome=None, language=None, event_id=None, campaign_id=None, attention=False,
                  opted_out=None, retry_eligible=False, limit=200, offset=0) -> list[Recipient]:
    filters = dict(outcome=outcome, language=language, event_id=event_id, campaign_id=campaign_id,
                   attention=attention, opted_out=opted_out)
    if not retry_eligible:                       # plain filters page in SQL
        return recipients_repo.filtered(db, **filters, limit=limit, offset=offset)
    rows = recipients_repo.filtered(db, **filters, with_attempts=True)
    camps = campaigns_repo.by_ids(db, {r.campaign_id for r in rows})
    rows = [r for r in rows if campaign_svc.retry_eligible(camps[r.campaign_id], r)]
    return rows[offset:offset + limit]


def history(db: Session, r: Recipient) -> dict:
    return {
        "recipient": RecipientOut.model_validate(r),
        "attempts": [AttemptOut.model_validate(a) for a in r.attempts],
        "intents": [IntentOut.model_validate(i) for i in intents_repo.for_recipient(db, r.id)],
        "followups": [FollowUpOut.model_validate(f) for f in followups_repo.for_recipient(db, r.id)],
    }


def list_attempts(db: Session, cid: int):
    return attempts_repo.in_campaign(db, cid)
