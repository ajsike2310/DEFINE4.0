"""Campaign management: per-campaign progress and a rule-based "next step", plus duplication."""
from sqlalchemy.orm import Session

from ..models import Campaign
from ..repositories import campaigns as campaigns_repo
from . import campaigns as svc
from . import participants

ATTENTION = ("unclear", "human_required", "callback_requested", "information_requested", "no_response")


def campaign_row(c: Campaign) -> dict:
    rs = list(c.recipients)
    total = len(rs)
    resolved = sum(1 for r in rs if r.outcome != "pending")
    attention = sum(1 for r in rs if not r.opted_out and r.outcome in ATTENTION)
    retries = sum(1 for r in rs if svc.retry_eligible(c, r))
    no_consent = sum(1 for r in rs if c.require_consent and r.consent_status != "granted" and not r.opted_out)
    contacted = sum(1 for r in rs if r.attempts)
    if c.status == "cancelled":
        step = "Cancelled"
    elif total == 0:
        step = "Add participants"
    elif c.status in ("draft", "scheduled"):
        step = "Ready to start" + (f" ({no_consent} will be skipped: no recorded consent)" if no_consent else "")
    elif retries:
        step = f"{retries} retry-eligible: run retries"
    elif attention:
        step = f"{attention} need follow-up"
    elif c.status == "running":
        step = "Waiting for call results"
    else:
        step = "Done"
    return {"campaign_id": c.id, "event_id": c.event_id, "name": c.name, "purpose": c.purpose, "status": c.status,
            "is_demo": c.is_demo, "participants": total, "contacted": contacted, "resolved": resolved,
            "needs_attention": attention, "retry_eligible": retries, "missing_consent": no_consent,
            "progress": round(resolved / total, 4) if total else None,   # resolved / participants
            "next_step": step, "created_at": c.created_at}


def overview(db: Session, event_id: int | None) -> dict:
    rows = [campaign_row(c) for c in campaigns_repo.with_participants(db, event_id)]
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {"by_status": by_status, "campaigns": rows,
            "totals": {"participants": sum(r["participants"] for r in rows),
                       "needs_attention": sum(r["needs_attention"] for r in rows),
                       "retry_eligible": sum(r["retry_eligible"] for r in rows)}}


def duplicate(db: Session, src: Campaign, name: str | None, copy_participants: bool) -> tuple[Campaign, dict]:
    """New DRAFT with the same settings. Participants are copied by the same safe rules as copy-from
    (opted-out / revoked are never copied); outcomes and call history are never copied."""
    new = Campaign(event_id=src.event_id, name=name or f"{src.name} (copy)"[:200], purpose=src.purpose,
                   messages=dict(src.messages), languages=list(src.languages), status="draft",
                   max_attempts=src.max_attempts, require_consent=src.require_consent, is_demo=src.is_demo)
    db.add(new)
    db.flush()
    if copy_participants:
        return new, participants.copy_from(db, new, src)     # same safe rules, incl. numbers that opted out elsewhere
    db.commit()
    return new, {"copied": 0, "skipped": 0}
