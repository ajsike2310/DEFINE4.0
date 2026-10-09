"""Follow-up work queue with transparent, rule-based priorities (no AI scoring)."""
from datetime import timedelta

from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import FollowUp, IntentResult
from ..repositories import followups as followups_repo
from .campaigns import clarify_blocker

RECOMMENDED = {
    "callback": "Call the participant back at their requested time, then mark complete.",
    "human_review": "Ask one clarifying yes/no question (if offered), otherwise contact the participant yourself.",
    "send_information": "Relay the approved information to the participant, then mark complete.",
}


def _priority(f: FollowUp, intent: IntentResult | None) -> tuple[int, str]:
    now = utcnow()
    if f.action_type == "callback" and f.scheduled_at and f.scheduled_at <= now + timedelta(hours=1):
        return 1, "scheduled callback is due or overdue"
    if f.action_type == "human_review":
        return 2, "response could not be understood safely" if intent and intent.intent in ("unclear", "human_required") \
            else "needs a person to answer"
    if f.action_type == "callback":
        return 2, "callback requested; time not confirmed"
    return 3, "participant asked for information"


def build_queue(db: Session, event_id: int | None = None, campaign_id: int | None = None,
                include_closed: bool = False) -> list[dict]:
    items = []
    for f, camp, rec, intent, att in followups_repo.queue_rows(db, event_id=event_id, campaign_id=campaign_id,
                                                              include_closed=include_closed):
        prio, why = _priority(f, intent)
        tried = any(a.mode == "clarify" for a in rec.attempts)
        items.append(dict(
            can_clarify=f.action_type == "human_review" and clarify_blocker(camp, rec) is None,
            clarification_attempted=tried,
            followup_id=f.id, campaign_id=camp.id, campaign_name=camp.name, event_id=camp.event_id,
            recipient_id=rec.id, participant_name=rec.name, participant_ref=rec.external_ref,
            reason=(intent.intent.replace("_", " ") if intent else f.action_type.replace("_", " ")),
            action_type=f.action_type, status=f.status, priority=prio, priority_reason=why,
            latest_outcome=rec.outcome, recommended_action=RECOMMENDED.get(f.action_type, ""),
            scheduled_at=f.scheduled_at, note=f.note, is_simulated=bool(att and att.is_simulated),
            created_at=f.created_at))
    items.sort(key=lambda i: (i["priority"], i["scheduled_at"] is None, i["scheduled_at"] or i["created_at"], i["followup_id"]))
    return items
