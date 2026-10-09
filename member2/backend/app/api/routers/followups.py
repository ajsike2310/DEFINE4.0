"""Follow-up queue and tasks."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...repositories import followups as followups_repo
from ...schemas.api import FollowUpOut, FollowUpPatch, QueueItem
from ...services import followups as followup_svc
from ...services.queue import build_queue
from ..deps import ApiError, get_db

router = APIRouter(tags=["follow-ups"])


@router.get("/followups/queue", response_model=list[QueueItem])
def followup_queue(db: Session = Depends(get_db), event_id: int | None = None, campaign_id: int | None = None):
    """Open follow-ups ordered by rule-based priority (1 = most urgent)."""
    return build_queue(db, event_id, campaign_id)


@router.get("/followups", response_model=list[FollowUpOut])
def list_followups(db: Session = Depends(get_db), campaign_id: int | None = None, status: str | None = None):
    return followups_repo.filtered(db, campaign_id=campaign_id, status=status)


@router.patch("/followups/{fid}", response_model=FollowUpOut)
def patch_followup(fid: int, body: FollowUpPatch, db: Session = Depends(get_db)):
    f = followups_repo.get(db, fid)
    if not f:
        raise ApiError(404, "not_found", "follow-up not found")
    return followup_svc.patch(db, f, body)
