"""Provider event handling: dedupe -> status transition / intent pipeline -> outcome + follow-ups."""
import logging
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from member3.integrations.base import ProviderEvent as PEvent
from member3.intelligence.intent.taxonomy import Intent, NextAction
from member3.intelligence.pipeline import ResponseInput, process_response

from ..core.db import utcnow
from ..models import CallAttempt, FollowUp, IntentResult, ProviderEvent, Recipient
from ..repositories import campaigns as campaigns_repo
from ..repositories import events as events_repo
from ..repositories import followups as followups_repo
from ..repositories import intents as intents_repo
from ..repositories import recipients as recipients_repo
from . import suppression
from .states import (INTENT_TO_OUTCOME, InvalidTransition, RETRYABLE, TERMINAL_CALL,
                     check_call_transition)

log = logging.getLogger("events")


def mask(phone: str) -> str:
    return phone[:3] + "*" * max(len(phone) - 5, 0) + phone[-2:]


def apply_event(db: Session, provider: str, attempt: CallAttempt, ev: PEvent, settings) -> str:
    """Apply one provider event idempotently. Returns 'applied' | 'duplicate' | 'ignored:<why>'."""
    ledger = ProviderEvent(provider=provider, event_id=ev.event_id, call_attempt_id=attempt.id, kind=ev.kind)
    db.add(ledger)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return "duplicate"
    try:
        result = _status(db, attempt, ev, settings) if ev.kind == "status" else _response(db, attempt, ev)
    except InvalidTransition as exc:
        result = f"ignored:{exc}"
    ledger.result = result[:100]
    db.commit()
    return result.split(":")[0] if result.startswith("ignored") else result


def _status(db, attempt: CallAttempt, ev: PEvent, settings) -> str:
    new = ev.status
    if new == attempt.status:
        return "ignored:no change"
    if attempt.status == "queued":          # provider event arrived before we recorded initiation
        attempt.status = "initiating"
    check_call_transition(attempt.status, new)
    now = utcnow()
    attempt.status = new
    if new == "answered" or (new == "completed" and not attempt.answered_at):
        attempt.answered_at = now
    if new in TERMINAL_CALL:
        attempt.completed_at = now
    if new in RETRYABLE:
        attempt.failure_reason = new
        after_technical_failure(db, attempt, settings)
    return "applied"


def _open_review(db, recipient_id: int) -> FollowUp | None:
    return followups_repo.open_review(db, recipient_id)


def after_technical_failure(db, attempt: CallAttempt, settings) -> None:
    """A call ended in a technical failure: schedule a bounded retry, or give up as `no_response`."""
    rec = recipients_repo.get(db, attempt.recipient_id)
    camp = campaigns_repo.get(db, attempt.campaign_id)
    if attempt.mode == "clarify":
        # The one clarification chance was used; outcome stays "unclear" and a person must follow up.
        fu = _open_review(db, rec.id)
        if fu:
            fu.note = f"clarification call {attempt.status}; needs a person"[:300]
        return
    can_retry = (attempt.attempt_number < camp.max_attempts and not rec.opted_out
                 and rec.consent_status != "revoked" and rec.outcome in ("pending", "no_response"))
    if can_retry:
        attempt.next_retry_at = utcnow() + timedelta(minutes=settings.retry_backoff_minutes)
        rec.outcome = "pending"
    elif rec.outcome in ("pending", "no_response"):
        rec.outcome = "no_response"        # retries exhausted: honest "never reached"


def _response(db, attempt: CallAttempt, ev: PEvent) -> str:
    if attempt.status not in ("answered", "completed") or not attempt.answered_at:
        return "ignored:response only accepted for an answered call"
    if intents_repo.for_attempt(db, attempt.id):
        return "ignored:attempt already has a classified response"
    rec = recipients_repo.get(db, attempt.recipient_id)
    camp = campaigns_repo.get(db, attempt.campaign_id)
    event = events_repo.get(db, camp.event_id)
    d = process_response(ResponseInput(text=ev.text, dtmf=ev.dtmf, audio_ref=ev.audio_ref))
    if d.intent == Intent.CONFIRM and camp.purpose != "attendance_confirmation":
        # "Yes/OK" to an announcement or reminder is NOT attendance confirmation.
        d.intent = Intent.ACK
        d.next_action = NextAction.RECORD_OUTCOME
        d.notes.append("affirmative reply to a non-attendance campaign recorded as acknowledgement")
    if attempt.mode == "clarify" and d.intent not in (Intent.CONFIRM, Intent.DECLINE, Intent.OPT_OUT):
        # Clarify-once: only a clear yes / no / opt-out settles it. Anything else goes to a person.
        d.intent, d.next_action, d.needs_review = Intent.UNCLEAR, NextAction.HUMAN_REVIEW, True
        d.notes.append("still unclear after clarification question")
    ir = IntentResult(call_attempt_id=attempt.id, recipient_id=rec.id, campaign_id=attempt.campaign_id,
                      intent=d.intent.value, score=d.score, method=d.method, detected_language=d.language,
                      evidence=d.evidence, notes=d.notes, needs_review=d.needs_review,
                      next_action=d.next_action.value)
    db.add(ir)
    db.flush()
    # Never overwrite an opt-out; otherwise latest classified response sets the outcome.
    if not rec.opted_out:
        rec.outcome = INTENT_TO_OUTCOME[d.intent.value]
    if d.intent == Intent.OPT_OUT:
        rec.opted_out = True
        rec.consent_status = "revoked"
        for fu in followups_repo.open_for_recipient(db, rec.id):
            fu.status, fu.note = "cancelled", "recipient opted out"
        spread = suppression.record_opt_out(db, rec)     # opt-out wins everywhere in scope, not just this campaign
        log.info("opt-out recorded for %s (also applied to %d other participant rows, %d leads)",
                 mask(rec.phone), spread["participants"], spread["leads"])
    elif d.next_action == NextAction.RECORD_OUTCOME and attempt.mode == "clarify":
        fu = _open_review(db, rec.id)      # clarification settled it: close the review task
        if fu:
            fu.status, fu.completed_at = "completed", utcnow()
            fu.note = (f"resolved by clarification call: {d.intent.value}")[:300]
    elif d.next_action == NextAction.CREATE_FOLLOWUP:
        db.add(FollowUp(campaign_id=attempt.campaign_id, recipient_id=rec.id, source_intent_id=ir.id,
                        action_type="callback", scheduled_at=d.requested_time,
                        status="scheduled" if d.requested_time else "pending",
                        note="; ".join(([f"participant said: {d.time_hint} (date not confirmed)"] if d.time_hint else [])
                                       + d.notes)[:300]))
    elif d.next_action in (NextAction.CLARIFY, NextAction.HUMAN_REVIEW):
        existing = _open_review(db, rec.id)
        if existing:      # one open review per participant; just update the context
            existing.note = ("clarification attempted; still unclear - needs a person. " + "; ".join(d.notes))[:300]
        else:
            db.add(FollowUp(campaign_id=attempt.campaign_id, recipient_id=rec.id, source_intent_id=ir.id,
                            action_type="human_review", status="pending",
                            note="unclear response; " + "; ".join(d.notes)[:250]))
    elif d.next_action == NextAction.SEND_INFO:
        answer = (event.approved_info or {}).get(d.info_topic or "")
        if answer:   # organiser-approved fact exists: operator can relay it; we never invent one
            db.add(FollowUp(campaign_id=attempt.campaign_id, recipient_id=rec.id, source_intent_id=ir.id,
                            action_type="send_information", status="pending",
                            note=f"asked about {d.info_topic}. Approved answer: {answer}"[:300]))
        else:
            db.add(FollowUp(campaign_id=attempt.campaign_id, recipient_id=rec.id, source_intent_id=ir.id,
                            action_type="human_review", status="pending",
                            note=("asked about " + d.info_topic if d.info_topic else "asked for information")
                            + "; no approved event information configured - answer manually"))
    return "applied"
