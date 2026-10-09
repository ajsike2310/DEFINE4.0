import csv
import hmac
import io
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from member3.integrations.base import ProviderError
from member3.integrations.base import ProviderEvent as PEvent
from member3.integrations.browser_demo.provider import BrowserDemoProvider
from member3.integrations.elevenlabs.client import ElevenLabsClient
from member3.intelligence.policies.closing_lines import closing_line
from member3.integrations.demo_provider.provider import DemoProvider
from member3.integrations.factory import build_provider
from member4.analytics.metrics import compute
from member4.analytics.quality import compute as compute_quality

from ..core.config import get_settings
from ..core.db import utcnow
from ..models import CallAttempt, Campaign, Event, FollowUp, ImportRun, IntentResult, Lead, Recipient
from ..schemas.api import (LEAD_SOURCES, PURPOSES, SUPPORTED_LANGUAGES, AttemptOut, CampaignIn, CampaignOut,
                           CampaignPatch, ConvertIn, DuplicateIn, EventIn, EventOut, EventPatch, FollowUpOut,
                           FollowUpPatch, IntentOut, LeadIn, LeadOut, LeadPatch, QueueItem, RecipientIn,
                           RecipientOut, WebhookEventIn)
from ..services import campaigns as svc
from ..services import leads as lead_svc
from ..services import overview as overview_svc
from ..services.demo import reset_demo, seed_all, seed_demo, seed_sample_leads
from ..services.events import apply_event
from ..services.queue import build_queue
from ..services.states import InvalidTransition

ATTENTION_OUTCOMES = ("unclear", "human_required", "callback_requested", "information_requested", "no_response")

router = APIRouter(prefix="/api")


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(status_code=status, detail={"code": code, "message": message, "details": details})


def get_db(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def provider_for(request: Request, campaign: Campaign):
    """Demo-seeded campaigns can NEVER reach a real provider."""
    if campaign.is_demo:
        return DemoProvider()
    override = getattr(request.app.state, "provider_override", None)
    if override:
        return override
    try:
        return build_provider(get_settings())
    except Exception as exc:
        raise ApiError(503, "provider_unavailable", str(exc))


def _campaign(db: Session, cid: int) -> Campaign:
    c = db.get(Campaign, cid)
    if not c:
        raise ApiError(404, "not_found", f"campaign {cid} not found")
    return c


def _out(db, c: Campaign) -> CampaignOut:
    out = CampaignOut.model_validate(c)
    out.recipient_count = db.scalar(select(func.count()).select_from(Recipient).where(Recipient.campaign_id == c.id))
    return out


@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)):
    db.execute(select(1))
    s = get_settings()
    return {"status": "ok", "provider": s.call_provider}


@router.get("/settings")
def settings_info():
    s = get_settings()
    return {
        "provider": s.call_provider,
        "purposes": sorted(PURPOSES),
        "exotel_configured": all([s.exotel_account_sid, s.exotel_api_key, s.exotel_api_token,
                                  s.exotel_caller_id, s.exotel_flow_url]),
        "languages": [{"code": k, "name": v,
                       "support": "rule-based phrase matching; small synthetic test set; experimental"
                       } for k, v in SUPPORTED_LANGUAGES.items()],
        "retry_policy": {"max_attempts_default": s.max_call_attempts, "backoff_minutes": s.retry_backoff_minutes,
                         "retry_on": ["failed", "busy", "no_answer", "voicemail"]},
        "data_location": s.data_location_note,
        "transcription": ("ElevenLabs speech-to-text for the browser demo call only; phone-call audio without text is routed to human review"
                          if s.elevenlabs_api_key else "none configured; speech audio without text is routed to human review"),
    }


# ---- events ----------------------------------------------------------------
def _event(db: Session, eid: int) -> Event:
    e = db.get(Event, eid)
    if not e:
        raise ApiError(404, "not_found", f"event {eid} not found")
    return e


def _event_out(db, e: Event) -> EventOut:
    out = EventOut.model_validate(e)
    out.campaign_count = db.scalar(select(func.count()).select_from(Campaign).where(Campaign.event_id == e.id))
    return out


@router.post("/events", response_model=EventOut, status_code=201)
def create_event(body: EventIn, db: Session = Depends(get_db)):
    e = Event(**body.model_dump())
    db.add(e)
    db.commit()
    return _event_out(db, e)


@router.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    return [_event_out(db, e) for e in db.scalars(select(Event).order_by(Event.id))]


@router.get("/events/{eid}", response_model=EventOut)
def get_event(eid: int, db: Session = Depends(get_db)):
    return _event_out(db, _event(db, eid))


@router.patch("/events/{eid}", response_model=EventOut)
def patch_event(eid: int, body: EventPatch, db: Session = Depends(get_db)):
    e = _event(db, eid)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k == "organizer_contact":
            setattr(e, k, v)
    db.commit()
    return _event_out(db, e)


# ---- campaigns -----------------------------------------------------------
@router.post("/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(body: CampaignIn, db: Session = Depends(get_db)):
    event = _event(db, body.event_id)
    data = body.model_dump()
    # A campaign is "simulated" (is_demo) when it belongs to the sample event or was created while the
    # demo provider is configured. Simulated campaigns can never reach a real provider.
    c = Campaign(**data, is_demo=event.is_demo or get_settings().call_provider == "demo")
    db.add(c)
    db.commit()
    return _out(db, c)


@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), status: str | None = None, event_id: int | None = None):
    q = select(Campaign).order_by(Campaign.id.desc())
    if status:
        q = q.where(Campaign.status == status)
    if event_id:
        q = q.where(Campaign.event_id == event_id)
    return [_out(db, c) for c in db.scalars(q)]


@router.get("/campaigns/overview")
def campaigns_overview(db: Session = Depends(get_db), event_id: int | None = None):
    """Campaign management view: progress, what needs attention and a rule-based next step per campaign."""
    return overview_svc.overview(db, event_id)


@router.post("/campaigns/{cid}/duplicate", status_code=201)
def duplicate_campaign(cid: int, body: DuplicateIn, db: Session = Depends(get_db)):
    new, counts = overview_svc.duplicate(db, _campaign(db, cid), body.name, body.copy_participants)
    return {"campaign": _out(db, new), **counts}


@router.get("/campaigns/{cid}", response_model=CampaignOut)
def get_campaign(cid: int, db: Session = Depends(get_db)):
    return _out(db, _campaign(db, cid))


@router.patch("/campaigns/{cid}", response_model=CampaignOut)
def patch_campaign(cid: int, body: CampaignPatch, db: Session = Depends(get_db)):
    c = _campaign(db, cid)
    if c.status not in ("draft", "scheduled"):
        raise ApiError(409, "invalid_state", "only draft/scheduled campaigns can be edited")
    data = body.model_dump(exclude_unset=True)
    if "messages" in data:
        data["messages"] = {**c.messages, **data["messages"]}
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    return _out(db, c)


@router.post("/campaigns/{cid}/cancel", response_model=CampaignOut)
def cancel_campaign(cid: int, db: Session = Depends(get_db)):
    c = _campaign(db, cid)
    try:
        svc.set_campaign_status(c, "cancelled")
    except InvalidTransition as exc:
        raise ApiError(409, "invalid_state", str(exc))
    db.commit()
    return _out(db, c)


@router.post("/campaigns/{cid}/start")
def start_campaign(cid: int, request: Request, db: Session = Depends(get_db)):
    c = _campaign(db, cid)
    if not c.recipients:
        raise ApiError(422, "no_recipients", "add recipients before starting")
    try:
        return svc.start_campaign(db, provider_for(request, c), get_settings(), c)
    except InvalidTransition as exc:
        raise ApiError(409, "invalid_state", str(exc))


@router.post("/campaigns/{cid}/clarify")
def clarify_campaign(cid: int, request: Request, db: Session = Depends(get_db)):
    """Clarify-once: one short yes/no call to each participant whose attendance answer was unclear."""
    c = _campaign(db, cid)
    if c.status not in ("running", "completed"):
        raise ApiError(409, "invalid_state", f"cannot clarify in a {c.status} campaign")
    return svc.clarify(db, provider_for(request, c), get_settings(), c, list(c.recipients))


@router.post("/recipients/{rid}/clarify")
def clarify_recipient(rid: int, request: Request, db: Session = Depends(get_db)):
    r = db.get(Recipient, rid)
    if not r:
        raise ApiError(404, "not_found", "recipient not found")
    c = _campaign(db, r.campaign_id)
    provider = provider_for(request, c)
    why = svc.clarify_blocker(c, r, provider)
    if why:
        raise ApiError(409, "clarify_not_allowed", why)
    return svc.clarify(db, provider, get_settings(), c, [r])


@router.post("/campaigns/{cid}/retry-due")
def retry_due(cid: int, request: Request, force: bool = False, db: Session = Depends(get_db)):
    c = _campaign(db, cid)
    try:
        return svc.retry_due(db, provider_for(request, c), get_settings(), c, force=force)
    except InvalidTransition as exc:
        raise ApiError(409, "invalid_state", str(exc))


# ---- recipients ------------------------------------------------------------
def _add_recipient(db, c: Campaign, body: RecipientIn, opted_out: bool = False) -> Recipient:
    if c.status not in ("draft", "scheduled", "running"):
        raise ApiError(409, "invalid_state", f"cannot add recipients to a {c.status} campaign")
    if body.preferred_language and body.preferred_language not in c.languages:
        raise ApiError(422, "validation_error", "preferred_language is not enabled for this campaign")
    r = Recipient(campaign_id=c.id, is_demo=c.is_demo, **body.model_dump())
    if opted_out:
        r.opted_out, r.outcome, r.consent_status = True, "opted_out", "revoked"
    db.add(r)
    return r


@router.post("/campaigns/{cid}/recipients", response_model=RecipientOut, status_code=201)
def add_recipient(cid: int, body: RecipientIn, db: Session = Depends(get_db)):
    c = _campaign(db, cid)
    r = _add_recipient(db, c, body)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "duplicate", "this phone number is already in the campaign")
    return r


@router.post("/campaigns/{cid}/recipients/import")
async def import_recipients(cid: int, file: UploadFile = File(...), consent_confirmed: bool = Form(False),
                            db: Session = Depends(get_db)):
    """CSV columns: name,phone[,participant_id][,language][,segment][,opted_out]. consent_confirmed=true marks
    rows consent=granted; rows with opted_out=yes/true/1 are imported as opted out (never called)."""
    c = _campaign(db, cid)
    raw = (await file.read())
    if len(raw) > 1_000_000:
        raise ApiError(413, "too_large", "CSV limited to 1 MB")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except UnicodeDecodeError:
        raise ApiError(422, "bad_csv", "CSV must be UTF-8")
    if not rows or not {"name", "phone"} <= set(rows[0].keys()):
        raise ApiError(422, "bad_csv", "CSV needs header columns: name, phone (optional: language, segment)")
    existing = set(db.scalars(select(Recipient.phone).where(Recipient.campaign_id == cid)))
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
            _add_recipient(db, c, body, opted_out=opt)
            existing.add(body.phone)
            imported += 1
        except (ValidationError, ValueError, ApiError) as exc:
            msg = exc.errors()[0]["msg"].removeprefix("Value error, ") if isinstance(exc, ValidationError) else str(getattr(exc, "detail", exc))
            errors.append({"line": line, "error": msg})
    db.add(ImportRun(kind="participants", event_id=c.event_id, campaign_id=c.id, filename=(file.filename or "")[:200],
                     rows_total=len(rows), imported=imported, rejected=len(errors), is_demo=c.is_demo,
                     reasons=dict(Counter(e["error"] for e in errors))))
    db.commit()
    return {"imported": imported, "rejected": len(errors), "errors": errors[:50]}


@router.get("/campaigns/{cid}/recipients", response_model=list[RecipientOut])
def list_recipients(cid: int, db: Session = Depends(get_db), outcome: str | None = None):
    _campaign(db, cid)
    q = select(Recipient).where(Recipient.campaign_id == cid).order_by(Recipient.id)
    if outcome:
        q = q.where(Recipient.outcome == outcome)
    return list(db.scalars(q))


@router.post("/campaigns/{cid}/recipients/copy-from/{src}")
def copy_participants(cid: int, src: int, db: Session = Depends(get_db)):
    """Reuse the eligible participants of another campaign of the SAME event. Opted-out and
    consent-revoked participants are never copied; consent/language/ref carry over."""
    c, s = _campaign(db, cid), _campaign(db, src)
    if c.event_id != s.event_id:
        raise ApiError(422, "different_event", "source campaign belongs to a different event")
    if c.id == s.id:
        raise ApiError(422, "validation_error", "source and target are the same campaign")
    have = set(db.scalars(select(Recipient.phone).where(Recipient.campaign_id == cid)))
    copied = skipped = 0
    for r in s.recipients:
        if r.phone in have:
            skipped += 1
        elif r.opted_out or r.consent_status == "revoked":
            skipped += 1
        else:
            lang = r.preferred_language if r.preferred_language in c.languages else None
            db.add(Recipient(campaign_id=cid, external_ref=r.external_ref, name=r.name, phone=r.phone,
                             preferred_language=lang, segment=r.segment, consent_status=r.consent_status,
                             is_demo=c.is_demo))
            copied += 1
    db.commit()
    return {"copied": copied, "skipped": skipped}


@router.get("/recipients", response_model=list[RecipientOut])
def list_all_recipients(db: Session = Depends(get_db), outcome: str | None = None,
                        language: str | None = None, event_id: int | None = None,
                        campaign_id: int | None = None, attention: bool = False,
                        opted_out: bool | None = None, retry_eligible: bool = False,
                        limit: int = Query(200, le=500), offset: int = 0):
    """attention=true -> unresolved cases (unclear, human-required, callback, info request, not reached)."""
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
    rows = list(db.scalars(q))
    if retry_eligible:
        rows = [r for r in rows if svc.retry_eligible(db.get(Campaign, r.campaign_id), r)]
    return rows[offset:offset + limit]


@router.get("/recipients/{rid}/history")
def recipient_history(rid: int, db: Session = Depends(get_db)):
    r = db.get(Recipient, rid)
    if not r:
        raise ApiError(404, "not_found", "recipient not found")
    return {
        "recipient": RecipientOut.model_validate(r),
        "attempts": [AttemptOut.model_validate(a) for a in r.attempts],
        "intents": [IntentOut.model_validate(i) for i in db.scalars(
            select(IntentResult).where(IntentResult.recipient_id == rid).order_by(IntentResult.id))],
        "followups": [FollowUpOut.model_validate(f) for f in db.scalars(
            select(FollowUp).where(FollowUp.recipient_id == rid).order_by(FollowUp.id))],
    }


@router.post("/recipients/{rid}/opt-out", response_model=RecipientOut)
def opt_out(rid: int, db: Session = Depends(get_db)):
    """Operator-recorded opt-out (e.g. received outside the call). Cancels open follow-ups."""
    r = db.get(Recipient, rid)
    if not r:
        raise ApiError(404, "not_found", "recipient not found")
    r.opted_out, r.consent_status, r.outcome = True, "revoked", "opted_out"
    for fu in db.scalars(select(FollowUp).where(FollowUp.recipient_id == rid,
                                                FollowUp.status.in_(("pending", "scheduled")))):
        fu.status, fu.note = "cancelled", "recipient opted out"
    db.commit()
    return r


# ---- attempts / intents / follow-ups ---------------------------------------
@router.get("/campaigns/{cid}/attempts", response_model=list[AttemptOut])
def list_attempts(cid: int, db: Session = Depends(get_db)):
    _campaign(db, cid)
    return list(db.scalars(select(CallAttempt).where(CallAttempt.campaign_id == cid).order_by(CallAttempt.id)))


@router.get("/campaigns/{cid}/intents", response_model=list[IntentOut])
def list_intents(cid: int, db: Session = Depends(get_db)):
    _campaign(db, cid)
    return list(db.scalars(select(IntentResult).where(IntentResult.campaign_id == cid).order_by(IntentResult.id)))


@router.get("/followups/queue", response_model=list[QueueItem])
def followup_queue(db: Session = Depends(get_db), event_id: int | None = None, campaign_id: int | None = None):
    """Open follow-ups ordered by rule-based priority (1 = most urgent)."""
    return build_queue(db, event_id, campaign_id)


@router.get("/followups", response_model=list[FollowUpOut])
def list_followups(db: Session = Depends(get_db), campaign_id: int | None = None, status: str | None = None):
    q = select(FollowUp).order_by(FollowUp.id.desc())
    if campaign_id:
        q = q.where(FollowUp.campaign_id == campaign_id)
    if status:
        q = q.where(FollowUp.status == status)
    return list(db.scalars(q))


@router.patch("/followups/{fid}", response_model=FollowUpOut)
def patch_followup(fid: int, body: FollowUpPatch, db: Session = Depends(get_db)):
    f = db.get(FollowUp, fid)
    if not f:
        raise ApiError(404, "not_found", "follow-up not found")
    if f.status in ("completed", "cancelled"):
        raise ApiError(409, "invalid_state", f"follow-up already {f.status}")
    rec = db.get(Recipient, f.recipient_id)
    if body.status in ("scheduled",) and rec.opted_out:
        raise ApiError(409, "opted_out", "recipient opted out; cannot schedule contact")
    if body.scheduled_at:
        f.scheduled_at = body.scheduled_at
        if not body.status and f.status == "pending":
            f.status = "scheduled"
    if body.status == "scheduled" and not f.scheduled_at:
        raise ApiError(422, "validation_error", "scheduled_at required to schedule a follow-up")
    if body.status:
        f.status = body.status
        if body.status == "completed":
            f.completed_at = utcnow()
    db.commit()
    return f


# ---- analytics / demo ------------------------------------------------------
@router.get("/analytics")
def analytics(db: Session = Depends(get_db), campaign_id: int | None = None, event_id: int | None = None,
              source: str = Query("all", pattern="^(all|real|simulated)$")):
    return compute(db, campaign_id, source, event_id)


# ---- leads (lead generation) -----------------------------------------------------
def _lead(db: Session, lid: int) -> Lead:
    lead = db.get(Lead, lid)
    if not lead:
        raise ApiError(404, "not_found", f"lead {lid} not found")
    return lead


@router.post("/events/{eid}/leads", response_model=LeadOut, status_code=201)
def capture_lead(eid: int, body: LeadIn, db: Session = Depends(get_db)):
    """Capture one lead (registration form, walk-in, referral or by hand). A self-serve form must send
    consent_status=granted only if the person ticked the consent box."""
    ev = _event(db, eid)
    lead = Lead(event_id=eid, is_demo=ev.is_demo, **body.model_dump())
    db.add(lead)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "duplicate", "this phone number is already a lead for this event")
    return lead_svc.lead_out(db, lead)


@router.get("/events/{eid}/leads", response_model=list[LeadOut])
def list_leads(eid: int, db: Session = Depends(get_db), status: str | None = None, source: str | None = None,
               q: str | None = None, limit: int = Query(300, le=500)):
    _event(db, eid)
    stmt = select(Lead).where(Lead.event_id == eid).order_by(Lead.id.desc())
    if status:
        stmt = stmt.where(Lead.status == status)
    if source:
        stmt = stmt.where(Lead.source == source)
    rows = list(db.scalars(stmt))
    if q:
        needle = q.strip().lower()
        rows = [x for x in rows if needle in x.name.lower() or needle in (x.email or "").lower()]
    out = [lead_svc.lead_out(db, x) for x in rows]
    out.sort(key=lambda o: (-o.score, -o.id))      # most contact-ready first
    return out[:limit]


@router.get("/events/{eid}/leads/summary")
def leads_summary(eid: int, db: Session = Depends(get_db)):
    _event(db, eid)
    return lead_svc.summary(db, eid)


@router.post("/events/{eid}/leads/import")
async def import_leads(eid: int, file: UploadFile = File(...), consent_confirmed: bool = Form(False),
                       source: str = Form("csv_import"), db: Session = Depends(get_db)):
    """CSV columns: name,phone[,email][,interest][,language]. consent_confirmed=true records consent=granted
    for every row - only tick it if the organiser holds consent for these contacts."""
    ev = _event(db, eid)
    if source not in LEAD_SOURCES:
        raise ApiError(422, "validation_error", f"source must be one of {sorted(LEAD_SOURCES)}")
    raw = await file.read()
    if len(raw) > 1_000_000:
        raise ApiError(413, "too_large", "CSV limited to 1 MB")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except UnicodeDecodeError:
        raise ApiError(422, "bad_csv", "CSV must be UTF-8")
    if not rows or not {"name", "phone"} <= set(rows[0].keys()):
        raise ApiError(422, "bad_csv", "CSV needs header columns: name, phone (optional: email, interest, language)")
    have = set(db.scalars(select(Lead.phone).where(Lead.event_id == eid)))
    imported, errors = 0, []
    for line, row in enumerate(rows, start=2):
        try:
            body = LeadIn(name=(row.get("name") or "").strip(), phone=row.get("phone") or "",
                          email=row.get("email"), interest=(row.get("interest") or "").strip() or None,
                          preferred_language=(row.get("language") or "").strip() or None, source=source,
                          consent_status="granted" if consent_confirmed else "unknown")
            if body.phone in have:
                raise ValueError("duplicate phone")
            db.add(Lead(event_id=eid, is_demo=ev.is_demo, **body.model_dump()))
            have.add(body.phone)
            imported += 1
        except (ValidationError, ValueError) as exc:
            msg = exc.errors()[0]["msg"].removeprefix("Value error, ") if isinstance(exc, ValidationError) else str(exc)
            errors.append({"line": line, "error": msg})
    db.add(ImportRun(kind="leads", event_id=eid, filename=(file.filename or "")[:200], rows_total=len(rows),
                     imported=imported, rejected=len(errors), is_demo=ev.is_demo,
                     reasons=dict(Counter(e["error"] for e in errors))))
    db.commit()
    return {"imported": imported, "rejected": len(errors), "errors": errors[:50]}


@router.patch("/leads/{lid}", response_model=LeadOut)
def patch_lead(lid: int, body: LeadPatch, db: Session = Depends(get_db)):
    lead = _lead(db, lid)
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
    db.commit()
    return lead_svc.lead_out(db, lead)


@router.post("/leads/convert")
def convert_leads(body: ConvertIn, db: Session = Depends(get_db)):
    c = _campaign(db, body.campaign_id)
    if c.status not in ("draft", "scheduled", "running"):
        raise ApiError(409, "invalid_state", f"cannot add participants to a {c.status} campaign")
    found = list(db.scalars(select(Lead).where(Lead.id.in_(body.lead_ids))))
    missing = set(body.lead_ids) - {x.id for x in found}
    res = lead_svc.convert(db, c, found)
    res["skipped"] += [{"lead_id": m, "reason": "lead not found"} for m in sorted(missing)]
    return res


# ---- data & AI quality -----------------------------------------------------------
@router.get("/quality")
def quality(db: Session = Depends(get_db), event_id: int | None = None, source: str = "all"):
    if source not in ("all", "real", "simulated"):
        raise ApiError(422, "validation_error", "source must be all|real|simulated")
    return compute_quality(db, event_id=event_id, source=source)


@router.post("/demo/seed", response_model=CampaignOut, status_code=201)
def demo_seed(db: Session = Depends(get_db)):
    return _out(db, seed_demo(db))


@router.post("/demo/seed-leads", status_code=201)
def demo_seed_leads(db: Session = Depends(get_db)):
    """Add clearly-labelled sample leads to sample events that have none."""
    return {"leads_added": seed_sample_leads(db)}


@router.post("/demo/seed-all", status_code=201)
def demo_seed_all(run: bool = False, db: Session = Depends(get_db)):
    """Create the three labelled sample events (each with a draft campaign). run=true also executes the
    simulated calls + retry rounds through the normal code path (clarify-once is left for you to click)."""
    camps = seed_all(db, get_settings(), run=run)
    return {"ran": run, "campaigns": [_out(db, c) for c in camps],
            "events": [_event_out(db, db.get(Event, c.event_id)) for c in camps]}


@router.delete("/demo")
def demo_reset(db: Session = Depends(get_db)):
    return {"deleted_campaigns": reset_demo(db)}


# ---- webhooks --------------------------------------------------------------
def _attempt_by_call_id(db, provider: str, call_id: str) -> CallAttempt:
    a = db.scalar(select(CallAttempt).where(CallAttempt.provider == provider, CallAttempt.provider_call_id == call_id))
    if not a:
        raise ApiError(404, "unknown_call", "no attempt for that provider call id")
    return a


@router.post("/webhooks/demo")
def webhook_demo(body: WebhookEventIn, db: Session = Depends(get_db)):
    """Inject a SIMULATED provider event (duplicate/ordering tests, manual demos). Demo attempts only."""
    a = _attempt_by_call_id(db, "demo", body.provider_call_id)
    ev = PEvent(body.event_id, body.provider_call_id, body.kind, body.status, body.text, body.dtmf)
    return {"result": apply_event(db, "demo", a, ev, get_settings())}


def _exotel_guard(token: str) -> None:
    """Exotel documents no webhook signature, so a shared secret in the URL is required."""
    s = get_settings()
    if not s.exotel_webhook_token:
        raise ApiError(503, "webhook_disabled", "EXOTEL_WEBHOOK_TOKEN not configured")
    if not hmac.compare_digest(token, s.exotel_webhook_token):
        raise ApiError(401, "unauthorized", "bad webhook token")


async def _payload(request: Request) -> dict:
    """Merge query params with a JSON or form body (Passthru sends GET query params; StatusCallback can be JSON)."""
    data: dict = dict(request.query_params)
    if request.method == "POST":
        ctype = request.headers.get("content-type", "")
        try:
            data.update(await request.json() if "json" in ctype else dict(await request.form()))
        except Exception:
            raise ApiError(422, "unrecognised_payload", "body is not valid JSON/form data")
    return data


def _exotel_attempt(db, payload: dict) -> tuple[str, CallAttempt]:
    """Find our attempt by CallSid, else by CustomField (= our attempt id, set when the call was placed)."""
    sid = str(payload.get("CallSid") or "")
    a = db.scalar(select(CallAttempt).where(CallAttempt.provider == "exotel", CallAttempt.provider_call_id == sid)) if sid else None
    if not a and str(payload.get("CustomField", "")).isdigit():
        a = db.get(CallAttempt, int(payload["CustomField"]))
        if a and a.provider != "exotel":
            a = None
    if not a:
        raise ApiError(404, "unknown_call", "no attempt matches CallSid/CustomField")
    return sid or a.provider_call_id or str(a.id), a


@router.post("/webhooks/exotel")
async def webhook_exotel(request: Request, token: str = "", db: Session = Depends(get_db)):
    """Exotel StatusCallback (documented JSON/form fields: CallSid, Status, ...). Only documented `Status`
    values are interpreted. Verify against your account's real payload on first live call."""
    _exotel_guard(token)
    payload = await _payload(request)
    status = str(payload.get("Status", "")).lower()
    from member3.integrations.exotel.provider import STATUS_MAP
    if not payload.get("CallSid") or status not in STATUS_MAP:
        raise ApiError(422, "unrecognised_payload", "missing CallSid or unrecognised Status")
    sid, a = _exotel_attempt(db, payload)
    mapped = STATUS_MAP[status]
    if mapped == "initiating":
        return {"result": "ignored"}
    return {"result": apply_event(db, "exotel", a, PEvent(f"{sid}:{status}", sid, "status", mapped), get_settings())}


@router.api_route("/webhooks/exotel/response", methods=["GET", "POST"])
async def webhook_exotel_response(request: Request, token: str = "", db: Session = Depends(get_db)):
    """Target of the flow's Passthru applet (after a Gather). Documented: Passthru sends CallSid, CustomField and
    `digits` (wrapped in double quotes). Reaching this point means the callee answered, so we record
    'answered' first, then the keypad response."""
    _exotel_guard(token)
    payload = await _payload(request)
    digits = str(payload.get("digits", "")).strip().strip('"').strip("'").strip()
    sid, a = _exotel_attempt(db, payload)
    s = get_settings()
    apply_event(db, "exotel", a, PEvent(f"{sid}:passthru-answered", sid, "status", "answered"), s)
    db.refresh(a)
    if not digits:
        return {"result": "no digits received"}
    return {"result": apply_event(db, "exotel", a, PEvent(f"{sid}:digits:{digits}", sid, "response", dtmf=digits), s)}


@router.get("/settings/exotel-readiness")
def exotel_readiness():
    """What is still missing before real calls can be placed. Names only - never values."""
    s = get_settings()
    req = [("EXOTEL_ACCOUNT_SID", s.exotel_account_sid), ("EXOTEL_API_KEY", s.exotel_api_key),
           ("EXOTEL_API_TOKEN", s.exotel_api_token), ("EXOTEL_CALLER_ID", s.exotel_caller_id),
           ("EXOTEL_FLOW_URL", s.exotel_flow_url), ("EXOTEL_WEBHOOK_TOKEN", s.exotel_webhook_token),
           ("PUBLIC_BASE_URL", s.public_base_url)]
    checks = [{"name": n, "ok": bool(v), "required": True} for n, v in req]
    checks += [{"name": "EXOTEL_ALLOWED_NUMBERS", "ok": bool(s.exotel_allowed_numbers.strip()), "required": False,
                "detail": "recommended: restricts real calls to approved test numbers"},
               {"name": "EXOTEL_CLARIFY_FLOW_URL", "ok": bool(s.exotel_clarify_flow_url), "required": False,
                "detail": "needed for clarify-once calls on Exotel"},
               {"name": "CALL_PROVIDER=exotel", "ok": s.call_provider == "exotel", "required": True}]
    base = s.public_base_url.rstrip("/")
    return {
        "ready": all(c["ok"] for c in checks if c["required"]),
        "checks": checks,
        "urls": {
            "status_callback": f"{base}/api/webhooks/exotel?token=<EXOTEL_WEBHOOK_TOKEN>" if base else None,
            "passthru_response": f"{base}/api/webhooks/exotel/response?token=<EXOTEL_WEBHOOK_TOKEN>" if base else None,
        },
        "note": "Real operation has never been verified from this codebase; run scripts/exotel_check.py first.",
    }


# ---- browser demo call (ElevenLabs voice; NOT a phone call) -----------------
MAX_AUDIO_BYTES = 5 * 1024 * 1024


class BrowserReplyIn(BaseModel):
    dtmf: str | None = Field(default=None, max_length=1)
    text: str | None = Field(default=None, max_length=500)


def _voice(request: Request) -> ElevenLabsClient:
    override = getattr(request.app.state, "elevenlabs_override", None)
    if override:
        return override
    s = get_settings()
    if not s.elevenlabs_api_key:
        raise ApiError(503, "voice_unavailable", "ELEVENLABS_API_KEY is not set in .env; voice and speech are off")
    return ElevenLabsClient(s.elevenlabs_api_key, voice_id=s.elevenlabs_voice_id,
                            tts_model=s.elevenlabs_tts_model, stt_model=s.elevenlabs_stt_model)


@router.get("/voice/status")
def voice_status():
    """Whether the ElevenLabs key is configured. Never returns the key."""
    s = get_settings()
    return {"configured": bool(s.elevenlabs_api_key), "voice_id": s.elevenlabs_voice_id,
            "tts_model": s.elevenlabs_tts_model, "stt_model": s.elevenlabs_stt_model,
            "note": "Browser demo call: a person plays the participant. It is not a phone call and is recorded as simulated."}


def _attempt_message(db, a: CallAttempt) -> str:
    c = db.get(Campaign, a.campaign_id)
    if a.mode == "clarify":
        return svc.CLARIFY_MESSAGES.get(a.call_language) or svc.CLARIFY_MESSAGES["en"]
    return c.messages.get(a.call_language, "")


def _open_browser_attempt(db, aid: int) -> CallAttempt:
    a = db.get(CallAttempt, aid)
    if not a or a.provider != "browser_demo":
        raise ApiError(404, "not_found", "no browser demo call with that id")
    if a.status != "answered":
        raise ApiError(409, "call_not_open", f"this demo call is {a.status}; start a new one")
    return a


@router.post("/campaigns/{cid}/recipients/{rid}/browser-call", status_code=201)
def start_browser_call(cid: int, rid: int, mode: str = "main", db: Session = Depends(get_db)):
    c = _campaign(db, cid)
    r = db.get(Recipient, rid)
    if not r or r.campaign_id != cid:
        raise ApiError(404, "not_found", f"participant {rid} not found in campaign {cid}")
    if not c.is_demo:
        raise ApiError(409, "not_demo", "browser demo calls are only for sample (demo) campaigns, so a real "
                                         "participant's outcome is never set by someone role-playing")
    if mode not in ("main", "clarify"):
        raise ApiError(422, "validation_error", "mode must be main or clarify")
    prov = BrowserDemoProvider()
    if mode == "clarify":
        why = svc.clarify_blocker(c, r, prov)
    else:
        ok, reason = svc.is_eligible(c, r)
        why = None if ok else reason
        if not why and svc._live_attempt(r):
            why = "a call is already in progress"
        if not why and len(r.attempts) >= c.max_attempts:
            why = "no attempts left for this participant"
    if why:
        raise ApiError(409, "not_allowed", why)
    a = svc.dispatch(db, prov, get_settings(), c, r, mode=mode)
    if not a:
        raise ApiError(409, "not_allowed", "this participant cannot be called right now")
    return {"attempt_id": a.id, "status": a.status, "mode": a.mode, "language": a.call_language,
            "message": _attempt_message(db, a), "simulated": True, "participant": r.name}


@router.post("/browser-calls/{aid}/speak")
def browser_call_speak(aid: int, request: Request, db: Session = Depends(get_db)):
    """Speak this call's own script (never arbitrary text) with the configured ElevenLabs voice."""
    a = _open_browser_attempt(db, aid)
    voice = _voice(request)
    try:
        audio = voice.speak(_attempt_message(db, a))
    except ProviderError as exc:
        raise ApiError(502, "voice_failed", str(exc))
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


def _finish_browser_reply(db, a: CallAttempt, *, text: str | None, dtmf: str | None) -> dict:
    s = get_settings()
    apply_event(db, "browser_demo", a, PEvent(f"{a.provider_call_id}:response", a.provider_call_id,
                                              "response", text=text, dtmf=dtmf), s)
    apply_event(db, "browser_demo", a, PEvent(f"{a.provider_call_id}:completed", a.provider_call_id,
                                              "status", "completed"), s)
    db.refresh(a)
    rec = db.get(Recipient, a.recipient_id)
    ir = db.scalar(select(IntentResult).where(IntentResult.call_attempt_id == a.id))
    camp = db.get(Campaign, a.campaign_id)
    # An unclear attendance answer gets exactly one spoken yes/no question (clarify-once rules apply).
    nxt = "clarify" if (a.mode == "main" and rec.outcome == "unclear"
                        and not svc.clarify_blocker(camp, rec, BrowserDemoProvider())) else "close"
    return {"attempt_id": a.id, "status": a.status, "heard": text, "outcome": rec.outcome, "simulated": True, "next": nxt,
            "intent": ir.intent if ir else None, "method": ir.method if ir else None,
            "next_action": ir.next_action if ir else None, "needs_review": ir.needs_review if ir else None,
            "evidence": ir.evidence if ir else None, "notes": ir.notes if ir else []}


@router.post("/browser-calls/{aid}/respond")
def browser_call_respond(aid: int, body: BrowserReplyIn, db: Session = Depends(get_db)):
    a = _open_browser_attempt(db, aid)
    if not (body.dtmf or (body.text and body.text.strip())):
        raise ApiError(422, "validation_error", "send a keypad digit or some text")
    return _finish_browser_reply(db, a, text=(body.text or "").strip() or None, dtmf=body.dtmf)


@router.post("/browser-calls/{aid}/respond-audio")
async def browser_call_respond_audio(aid: int, request: Request, file: UploadFile = File(...),
                                     db: Session = Depends(get_db)):
    """Transcribe the spoken reply with ElevenLabs, then classify the TEXT with the same rules as any reply.
    If transcription fails nothing is recorded (the call stays open): a reply is never guessed."""
    a = _open_browser_attempt(db, aid)
    voice = _voice(request)
    audio = await file.read(MAX_AUDIO_BYTES + 1)
    if not audio:
        raise ApiError(422, "validation_error", "no audio received")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ApiError(413, "too_large", "recording is too long; keep it under a minute")
    try:
        heard = voice.transcribe(audio, file.filename or "reply.webm", file.content_type or "audio/webm")
    except ProviderError as exc:
        raise ApiError(502, "transcription_failed", f"{exc}. Nothing was recorded; try again or press a key.")
    return _finish_browser_reply(db, a, text=heard or None, dtmf=None)


@router.post("/browser-calls/{aid}/hangup")
def browser_call_hangup(aid: int, db: Session = Depends(get_db)):
    """Ends the demo call with no reply. The participant stays 'pending'; nothing is guessed."""
    a = _open_browser_attempt(db, aid)
    apply_event(db, "browser_demo", a, PEvent(f"{a.provider_call_id}:completed", a.provider_call_id,
                                              "status", "completed"), get_settings())
    db.refresh(a)
    return {"attempt_id": a.id, "status": a.status, "simulated": True}


def _approved_answer(db, ir: IntentResult | None) -> str | None:
    """The organiser-approved answer attached to this reply's follow-up, if there is one. Never invented."""
    if not ir:
        return None
    fu = db.scalar(select(FollowUp).where(FollowUp.source_intent_id == ir.id, FollowUp.action_type == "send_information"))
    marker = "Approved answer: "
    return fu.note.split(marker, 1)[1] if fu and marker in (fu.note or "") else None


@router.post("/browser-calls/{aid}/speak-reply")
def browser_call_speak_reply(aid: int, request: Request, db: Session = Depends(get_db)):
    """Voice the agent's closing line for a finished browser call. The line is chosen from fixed text by the
    classified intent (and the organiser's approved answer for questions); callers cannot supply text."""
    a = db.get(CallAttempt, aid)
    if not a or a.provider != "browser_demo":
        raise ApiError(404, "not_found", "no browser demo call with that id")
    ir = db.scalar(select(IntentResult).where(IntentResult.call_attempt_id == a.id))
    if not ir:
        raise ApiError(409, "no_reply", "this call has no recorded reply to respond to")
    voice = _voice(request)
    line = closing_line(ir.intent, a.call_language, _approved_answer(db, ir))
    try:
        audio = voice.speak(line)
    except ProviderError as exc:
        raise ApiError(502, "voice_failed", str(exc))
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store", "X-Spoken-Text": _ascii_header(line)})


def _ascii_header(text: str) -> str:
    """HTTP headers are latin-1; percent-encode so Malayalam captions survive."""
    from urllib.parse import quote
    return quote(text, safe="")
