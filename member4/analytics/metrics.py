"""Analytics computed from persisted rows only. Definitions (denominators) are in docs/DATA_MODEL.md.

source filter: "all" | "real" | "simulated" (simulated = demo provider / demo-seeded data).
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from member2.backend.app.models import CallAttempt, Campaign, FollowUp, IntentResult, Recipient

TECH_FAIL = {"failed", "busy", "no_answer", "voicemail"}
TERMINAL = TECH_FAIL | {"completed", "cancelled"}
OUTCOMES = ["confirmed", "acknowledged", "declined", "callback_requested", "information_requested", "unclear",
            "human_required", "opted_out", "no_response", "pending"]


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None   # None = undefined (zero denominator), never a fake 0


def headcount_range(recipients: list[Recipient], purposes: dict[int, str]) -> dict | None:
    """Honest attendance range from ATTENDANCE-confirmation campaigns only.

    One row per person (phone): the most recent attendance campaign wins.
      floor   = said they will attend (confirmed)
      ceiling = everyone who has not said they cannot attend (total - declined)
      certainty = share of people with a definite yes/no (confirmed + declined) / total
    This is a bound on stated intent, NOT a prediction and NOT verified check-in.
    """
    # One row per person: the most recent DEFINITE answer (confirmed/declined) wins; a later campaign that
    # has not produced a definite answer yet must not erase an earlier one. Otherwise the latest row.
    latest: dict[str, Recipient] = {}
    for r in sorted(recipients, key=lambda x: x.campaign_id):
        if purposes.get(r.campaign_id) != "attendance_confirmation":
            continue
        prev = latest.get(r.phone)
        definite = r.outcome in ("confirmed", "declined")
        if prev is None or definite or prev.outcome not in ("confirmed", "declined"):
            latest[r.phone] = r
    rows = list(latest.values())
    if not rows:
        return None
    total = len(rows)
    confirmed = sum(1 for r in rows if r.outcome == "confirmed")
    declined = sum(1 for r in rows if r.outcome == "declined")
    unknown: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.outcome not in ("confirmed", "declined"):
            unknown["opted_out" if r.opted_out else r.outcome] += 1
    return {"participants": total, "confirmed": confirmed, "declined": declined,
            "unknown": total - confirmed - declined, "unknown_breakdown": dict(unknown),
            "floor": confirmed, "ceiling": total - declined,
            "certainty": round((confirmed + declined) / total, 4)}


def compute(db: Session, campaign_id: int | None = None, source: str = "all", event_id: int | None = None) -> dict:
    camps = select(Campaign)
    if campaign_id:
        camps = camps.where(Campaign.id == campaign_id)
    if event_id:
        camps = camps.where(Campaign.event_id == event_id)
    campaigns = list(db.scalars(camps))
    if source != "all":
        campaigns = [c for c in campaigns if c.is_demo == (source == "simulated")]
    ids = [c.id for c in campaigns]
    recipients = list(db.scalars(select(Recipient).where(Recipient.campaign_id.in_(ids)))) if ids else []
    attempts = list(db.scalars(select(CallAttempt).where(CallAttempt.campaign_id.in_(ids)))) if ids else []
    intents = list(db.scalars(select(IntentResult).where(IntentResult.campaign_id.in_(ids)))) if ids else []
    followups = list(db.scalars(select(FollowUp).where(FollowUp.campaign_id.in_(ids)))) if ids else []

    outcome_counts = {o: 0 for o in OUTCOMES}
    for r in recipients:
        outcome_counts[r.outcome] = outcome_counts.get(r.outcome, 0) + 1
    finished = [a for a in attempts if a.status in TERMINAL]
    answered = [a for a in attempts if a.answered_at]
    responded = {i.recipient_id for i in intents}
    total = len(recipients)
    resolved = total - outcome_counts["pending"]

    by_lang: dict[str, dict] = defaultdict(lambda: {"recipients": 0, "attempts": 0, "answered": 0,
                                                    **{o: 0 for o in OUTCOMES}})
    for r in recipients:
        row = by_lang[r.preferred_language or "unspecified"]
        row["recipients"] += 1
        row[r.outcome] += 1
    rec_lang = {r.id: (r.preferred_language or "unspecified") for r in recipients}
    for a in attempts:
        row = by_lang[rec_lang[a.recipient_id]]
        row["attempts"] += 1
        row["answered"] += 1 if a.answered_at else 0

    return {
        "source": source,
        "totals": {
            "campaigns": len(campaigns), "recipients": total,
            "calls_attempted": len(attempts), "calls_finished": len(finished),
            "calls_answered": len(answered), "recipients_contacted": len({a.recipient_id for a in attempts}),
            "recipients_responded": len(responded), "retries": sum(1 for a in attempts if a.attempt_number > 1),
            "failed_or_unanswered": sum(1 for a in finished if a.status in TECH_FAIL),
            "simulated_calls": sum(1 for a in attempts if a.is_simulated),
            "real_calls": sum(1 for a in attempts if not a.is_simulated),
        },
        "outcomes": outcome_counts,
        "followups": {
            "pending": sum(1 for f in followups if f.status in ("pending", "scheduled")),
            "completed": sum(1 for f in followups if f.status == "completed"),
            "cancelled": sum(1 for f in followups if f.status == "cancelled"),
        },
        "rates": {   # each: numerator / denominator documented in DATA_MODEL.md
            "completion_rate": _rate(resolved, total),
            "answer_rate": _rate(len(answered), len(finished)),
            "failure_rate": _rate(sum(1 for a in finished if a.status in TECH_FAIL), len(finished)),
            "confirmation_rate": _rate(outcome_counts["confirmed"], len(responded)),
            "decline_rate": _rate(outcome_counts["declined"], len(responded)),
            "unclear_rate": _rate(outcome_counts["unclear"] + outcome_counts["human_required"], len(responded)),
        },
        "by_language": [{"language": k, **v} for k, v in sorted(by_lang.items())],
        "headcount": headcount_range(recipients, {c.id: c.purpose for c in campaigns}),
        "clarification": {
            "attempted": sum(1 for a in attempts if a.mode == "clarify"),
            "resolved": sum(1 for a in attempts if a.mode == "clarify" and any(
                i.call_attempt_id == a.id and i.intent in ("confirm", "decline") for i in intents)),
        },
        "needs_review": sum(1 for i in intents if i.needs_review),
        # unresolved participants: not opted out, outcome needs a person or a retry
        "needs_attention": sum(1 for r in recipients if not r.opted_out and r.outcome in (
            "unclear", "human_required", "callback_requested", "information_requested", "no_response")),
    }
