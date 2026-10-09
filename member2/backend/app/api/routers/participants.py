"""Participants (recipients) of campaigns."""
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...repositories import recipients as recipients_repo
from ...schemas.api import RecipientIn, RecipientOut
from ...services import campaigns as svc
from ...services import csv_io
from ...services import participants as participant_svc
from ..deps import ApiError, get_campaign, get_db, get_recipient, provider_for

router = APIRouter(tags=["participants"])


@router.post("/campaigns/{cid}/recipients", response_model=RecipientOut, status_code=201)
def add_recipient(cid: int, body: RecipientIn, db: Session = Depends(get_db)):
    return participant_svc.add(db, get_campaign(db, cid), body)


@router.post("/campaigns/{cid}/recipients/import")
async def import_recipients(cid: int, file: UploadFile = File(...), consent_confirmed: bool = Form(False),
                            db: Session = Depends(get_db)):
    """CSV columns: name,phone[,participant_id][,language][,segment][,opted_out]. consent_confirmed=true marks
    rows consent=granted; rows with opted_out=yes/true/1 are imported as opted out (never called)."""
    c = get_campaign(db, cid)
    raw = await file.read(csv_io.MAX_CSV_BYTES + 1)
    return participant_svc.import_csv(db, c, raw, file.filename or "", consent_confirmed)


@router.get("/campaigns/{cid}/recipients", response_model=list[RecipientOut])
def list_recipients(cid: int, db: Session = Depends(get_db), outcome: str | None = None):
    get_campaign(db, cid)
    return recipients_repo.in_campaign(db, cid, outcome)


@router.post("/campaigns/{cid}/recipients/copy-from/{src}")
def copy_participants(cid: int, src: int, db: Session = Depends(get_db)):
    """Reuse the eligible participants of another campaign of the SAME event."""
    return participant_svc.copy_from(db, get_campaign(db, cid), get_campaign(db, src))


@router.get("/recipients", response_model=list[RecipientOut])
def list_all_recipients(db: Session = Depends(get_db), outcome: str | None = None,
                        language: str | None = None, event_id: int | None = None,
                        campaign_id: int | None = None, attention: bool = False,
                        opted_out: bool | None = None, retry_eligible: bool = False,
                        limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0)):
    """attention=true -> unresolved cases (unclear, human-required, callback, info request, not reached)."""
    return participant_svc.list_filtered(db, outcome=outcome, language=language, event_id=event_id,
                                         campaign_id=campaign_id, attention=attention, opted_out=opted_out,
                                         retry_eligible=retry_eligible, limit=limit, offset=offset)


@router.get("/recipients/{rid}/history")
def recipient_history(rid: int, db: Session = Depends(get_db)):
    return participant_svc.history(db, get_recipient(db, rid))


@router.post("/recipients/{rid}/opt-out", response_model=RecipientOut)
def opt_out(rid: int, db: Session = Depends(get_db)):
    """Operator-recorded opt-out (e.g. received outside the call). Applies to every record of the same number."""
    return participant_svc.opt_out(db, get_recipient(db, rid))


@router.post("/recipients/{rid}/clarify")
def clarify_recipient(rid: int, request: Request, db: Session = Depends(get_db)):
    r = get_recipient(db, rid)
    c = get_campaign(db, r.campaign_id)
    provider = provider_for(request, c)
    why = svc.clarify_blocker(c, r, provider)
    if why:
        raise ApiError(409, "clarify_not_allowed", why)
    return svc.clarify(db, provider, get_settings(), c, [r])
