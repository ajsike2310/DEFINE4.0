"""Lead generation."""
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from ...repositories import leads as leads_repo
from ...schemas.api import ConvertIn, LeadIn, LeadOut, LeadPatch
from ...services import csv_io
from ...services import leads as lead_svc
from ..deps import ApiError, get_campaign, get_db, get_event, get_lead

router = APIRouter(tags=["leads"])


def _limit_public_signup(request: Request, body: LeadIn) -> None:
    """The public sign-up form is unauthenticated, so throttle it per client address. Organiser entries
    (manual, import, referral, walk-in) are not throttled."""
    if body.source != "registration_form":
        return
    wait = request.app.state.signup_limiter.hit(request.client.host if request.client else "unknown")
    if wait is not None:
        raise ApiError(429, "rate_limited", f"too many sign-ups from this connection; try again in {wait} seconds",
                       headers={"Retry-After": str(wait)})


@router.post("/events/{eid}/leads", response_model=LeadOut, status_code=201)
def capture_lead(eid: int, body: LeadIn, request: Request, db: Session = Depends(get_db)):
    """Capture one lead (registration form, walk-in, referral or by hand). A self-serve form must send
    consent_status=granted only if the person ticked the consent box."""
    ev = get_event(db, eid)
    _limit_public_signup(request, body)
    return lead_svc.capture(db, ev, body)


@router.get("/events/{eid}/leads", response_model=list[LeadOut])
def list_leads(eid: int, db: Session = Depends(get_db), status: str | None = None, source: str | None = None,
               q: str | None = None, limit: int = Query(300, ge=1, le=500)):
    get_event(db, eid)
    return lead_svc.list_for_event(db, eid, status=status, source=source, q=q, limit=limit)


@router.get("/events/{eid}/leads/summary")
def leads_summary(eid: int, db: Session = Depends(get_db)):
    get_event(db, eid)
    return lead_svc.summary(db, eid)


@router.post("/events/{eid}/leads/import")
async def import_leads(eid: int, file: UploadFile = File(...), consent_confirmed: bool = Form(False),
                       source: str = Form("csv_import"), db: Session = Depends(get_db)):
    """CSV columns: name,phone[,email][,interest][,language]. consent_confirmed=true records consent=granted
    for every row - only tick it if the organiser holds consent for these contacts."""
    ev = get_event(db, eid)
    raw = await file.read(csv_io.MAX_CSV_BYTES + 1)
    return lead_svc.import_csv(db, ev, raw, file.filename or "", consent_confirmed, source)


@router.patch("/leads/{lid}", response_model=LeadOut)
def patch_lead(lid: int, body: LeadPatch, db: Session = Depends(get_db)):
    return lead_svc.patch(db, get_lead(db, lid), body)


@router.post("/leads/convert")
def convert_leads(body: ConvertIn, db: Session = Depends(get_db)):
    c = get_campaign(db, body.campaign_id)
    if c.status not in ("draft", "scheduled", "running"):
        raise ApiError(409, "invalid_state", f"cannot add participants to a {c.status} campaign")
    found = leads_repo.by_ids(db, body.lead_ids)
    missing = set(body.lead_ids) - {x.id for x in found}
    res = lead_svc.convert(db, c, found)
    res["skipped"] += [{"lead_id": m, "reason": "lead not found"} for m in sorted(missing)]
    return res
