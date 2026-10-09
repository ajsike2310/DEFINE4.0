"""Follow-up task updates (operator actions on the queue)."""
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..core.errors import ApiError
from ..models import FollowUp
from ..repositories import recipients as recipients_repo
from ..schemas.api import FollowUpPatch


def patch(db: Session, f: FollowUp, body: FollowUpPatch) -> FollowUp:
    if f.status in ("completed", "cancelled"):
        raise ApiError(409, "invalid_state", f"follow-up already {f.status}")
    rec = recipients_repo.get(db, f.recipient_id)
    if body.status == "scheduled" and rec.opted_out:
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
