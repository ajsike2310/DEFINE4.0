"""Campaign lifecycle and management."""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...repositories import campaigns as campaigns_repo
from ...repositories import intents as intents_repo
from ...schemas.api import (AttemptOut, CampaignIn, CampaignOut, CampaignPatch, DuplicateIn, IntentOut, ScheduleIn)
from ...services import campaigns as svc
from ...services import catalog
from ...services import overview as overview_svc
from ...services import participants as participant_svc
from ...services import reconcile, scheduler
from ...services.presenters import campaign_out, campaigns_out
from ...services.states import InvalidTransition
from ..deps import ApiError, get_campaign, get_db, get_event, provider_for

router = APIRouter(tags=["campaigns"])


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(body: CampaignIn, db: Session = Depends(get_db)):
    return campaign_out(db, catalog.create_campaign(db, get_event(db, body.event_id), body))


@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), status: str | None = None, event_id: int | None = None):
    return campaigns_out(db, campaigns_repo.list_filtered(db, status=status, event_id=event_id))


@router.get("/campaigns/overview")
def campaigns_overview(db: Session = Depends(get_db), event_id: int | None = None):
    """Campaign management view: progress, what needs attention and a rule-based next step per campaign."""
    return overview_svc.overview(db, event_id)


@router.post("/campaigns/{cid}/duplicate", status_code=201)
def duplicate_campaign(cid: int, body: DuplicateIn, db: Session = Depends(get_db)):
    new, counts = overview_svc.duplicate(db, get_campaign(db, cid), body.name, body.copy_participants)
    return {"campaign": campaign_out(db, new), **counts}


@router.get("/campaigns/{cid}", response_model=CampaignOut)
def read_campaign(cid: int, db: Session = Depends(get_db)):
    return campaign_out(db, get_campaign(db, cid))


@router.patch("/campaigns/{cid}", response_model=CampaignOut)
def patch_campaign(cid: int, body: CampaignPatch, db: Session = Depends(get_db)):
    return campaign_out(db, catalog.patch_campaign(db, get_campaign(db, cid), body))


@router.post("/campaigns/{cid}/cancel", response_model=CampaignOut)
def cancel_campaign(cid: int, db: Session = Depends(get_db)):
    c = get_campaign(db, cid)
    try:
        svc.set_campaign_status(c, "cancelled")
    except InvalidTransition as exc:
        raise ApiError(409, "invalid_state", str(exc))
    db.commit()
    return campaign_out(db, c)


@router.post("/campaigns/{cid}/schedule", response_model=CampaignOut)
def schedule_campaign(cid: int, body: ScheduleIn, db: Session = Depends(get_db)):
    """Queue a draft campaign to start by itself at `scheduled_at` (needs the scheduler to be running, or a call
    to POST /api/scheduler/tick once the time has passed)."""
    return campaign_out(db, scheduler.schedule(db, get_campaign(db, cid), body.scheduled_at))


@router.post("/campaigns/{cid}/unschedule", response_model=CampaignOut)
def unschedule_campaign(cid: int, db: Session = Depends(get_db)):
    return campaign_out(db, scheduler.unschedule(db, get_campaign(db, cid)))


@router.post("/campaigns/{cid}/start")
def start_campaign(cid: int, request: Request, db: Session = Depends(get_db)):
    c = get_campaign(db, cid)
    if not c.recipients:
        raise ApiError(422, "no_recipients", "add recipients before starting")
    try:
        return svc.start_campaign(db, provider_for(request, c), get_settings(), c)
    except InvalidTransition as exc:
        raise ApiError(409, "invalid_state", str(exc))


@router.post("/campaigns/{cid}/clarify")
def clarify_campaign(cid: int, request: Request, db: Session = Depends(get_db)):
    """Clarify-once: one short yes/no call to each participant whose attendance answer was unclear."""
    c = get_campaign(db, cid)
    if c.status not in ("running", "completed"):
        raise ApiError(409, "invalid_state", f"cannot clarify in a {c.status} campaign")
    return svc.clarify(db, provider_for(request, c), get_settings(), c, list(c.recipients))


@router.post("/campaigns/{cid}/retry-due")
def retry_due(cid: int, request: Request, force: bool = False, db: Session = Depends(get_db)):
    c = get_campaign(db, cid)
    try:
        return svc.retry_due(db, provider_for(request, c), get_settings(), c, force=force)
    except InvalidTransition as exc:
        raise ApiError(409, "invalid_state", str(exc))


@router.post("/campaigns/{cid}/reconcile")
def reconcile_campaign(cid: int, request: Request, minutes: int | None = Query(None, ge=0, le=1440),
                       db: Session = Depends(get_db)):
    """Ask the provider about real calls that never reported a result (default: older than STALE_CALL_MINUTES;
    `minutes=0` checks every open real call). The answer goes through the same path as a callback."""
    c = get_campaign(db, cid)
    provider = provider_for(request, c)
    if getattr(provider, "is_simulated", True):
        raise ApiError(409, "not_real", "this campaign uses simulated calls; there is nothing to reconcile")
    return reconcile.reconcile(db, get_settings(), provider, c, minutes=minutes)


@router.get("/campaigns/{cid}/attempts", response_model=list[AttemptOut])
def list_attempts(cid: int, db: Session = Depends(get_db)):
    get_campaign(db, cid)
    return participant_svc.list_attempts(db, cid)


@router.get("/campaigns/{cid}/intents", response_model=list[IntentOut])
def list_intents(cid: int, db: Session = Depends(get_db)):
    get_campaign(db, cid)
    return intents_repo.in_campaign(db, cid)
