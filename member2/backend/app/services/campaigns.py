"""Campaign lifecycle: start, dispatch calls through the provider, retries, completion."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from member3.integrations.base import CallProvider, ProviderError

from ..core.db import utcnow
from ..models import CallAttempt, Campaign, Recipient
from .events import apply_event, mask
from .states import (OPEN_OUTCOMES, RETRYABLE, TERMINAL_CALL, InvalidTransition,
                     check_campaign_transition)

log = logging.getLogger("campaigns")


def set_campaign_status(c: Campaign, new: str) -> None:
    if c.status != new:
        check_campaign_transition(c.status, new)
        c.status = new


def is_eligible(c: Campaign, r: Recipient) -> tuple[bool, str]:
    if r.opted_out:
        return False, "opted out"
    if r.consent_status == "revoked":
        return False, "consent revoked"
    if c.require_consent and r.consent_status != "granted":
        return False, "consent not granted"
    if r.outcome not in OPEN_OUTCOMES:
        return False, f"already resolved ({r.outcome})"
    return True, ""


def retry_eligible(c: Campaign, r: Recipient) -> bool:
    """Last attempt ended in a retryable technical failure and attempts remain."""
    ok, _ = is_eligible(c, r)
    last = r.attempts[-1] if r.attempts else None
    return bool(ok and last and last.status in RETRYABLE and len(r.attempts) < c.max_attempts)


def _live_attempt(r: Recipient) -> CallAttempt | None:
    return next((a for a in r.attempts if a.status not in TERMINAL_CALL), None)


CLARIFY_MESSAGES = {
    "en": "Sorry, we were not sure about your answer. Will you attend the event? Press 1 for yes, or 2 for no.",
    "ml": "ക്ഷമിക്കണം, നിങ്ങളുടെ ഉത്തരം വ്യക്തമായില്ല. പരിപാടിയിൽ പങ്കെടുക്കുമോ? ഉണ്ടെങ്കിൽ 1, ഇല്ലെങ്കിൽ 2 അമർത്തുക.",
}


def clarify_blocker(c: Campaign, r: Recipient, provider: CallProvider | None = None) -> str | None:
    """Why a clarification call is NOT allowed (None = allowed). Rule: exactly one yes/no follow-up
    question for an unclear attendance answer; never for opted-out/no-consent people; never twice."""
    if c.purpose != "attendance_confirmation":
        return "clarification applies to attendance campaigns only"
    if r.opted_out or r.consent_status == "revoked":
        return "participant opted out"
    if c.require_consent and r.consent_status != "granted":
        return "consent not granted"
    if r.outcome != "unclear":
        return f"only unclear answers are clarified (outcome is {r.outcome})"
    if any(a.mode == "clarify" for a in r.attempts):
        return "clarification already attempted"
    if _live_attempt(r):
        return "a call is already in progress"
    if provider is not None and not getattr(provider, "supports_clarify", True):
        return "provider has no clarification flow configured"
    return None


def clarify(db, provider, settings, c: Campaign, recipients: list[Recipient]) -> dict:
    done, skipped = 0, []
    for r in recipients:
        why = clarify_blocker(c, r, provider)
        if why:
            if r.outcome == "unclear" or len(recipients) == 1:    # only report real candidates
                skipped.append({"recipient_id": r.id, "reason": why})
        elif dispatch(db, provider, settings, c, r, mode="clarify"):
            done += 1
    return {"dispatched": done, "skipped": skipped}


def dispatch(db: Session, provider: CallProvider, settings, c: Campaign, r: Recipient,
             mode: str = "main") -> CallAttempt | None:
    """Create the next attempt and place the call. Returns None if not allowed (no duplicates)."""
    if mode == "clarify":
        if clarify_blocker(c, r, provider):
            return None
    else:
        ok, _ = is_eligible(c, r)
        if not ok or _live_attempt(r) or len(r.attempts) >= c.max_attempts:
            return None
    lang = r.preferred_language if r.preferred_language in c.languages else c.languages[0]
    att = CallAttempt(campaign_id=c.id, recipient_id=r.id, provider=provider.name, mode=mode,
                      is_simulated=provider.is_simulated, attempt_number=len(r.attempts) + 1,
                      call_language=lang, status="queued")
    db.add(att)
    db.flush()                       # unique(recipient_id, attempt_number) guards double-dispatch
    r.attempts.append(att)
    att.status, att.started_at = "initiating", utcnow()
    try:
        message = (CLARIFY_MESSAGES.get(lang) or CLARIFY_MESSAGES["en"]) if mode == "clarify" else c.messages.get(lang, "")
        res = provider.initiate_call(attempt_id=att.id, attempt_number=att.attempt_number, to=r.phone,
                                     language=lang, message=message, mode=mode)
    except ProviderError as exc:
        att.status, att.completed_at, att.failure_reason = "failed", utcnow(), str(exc)[:200]
        db.commit()
        log.warning("provider error for %s: %s", mask(r.phone), exc)
        return att
    att.provider_call_id = res.provider_call_id
    db.commit()
    for ev in res.events:
        apply_event(db, provider.name, att, ev, settings)
    db.refresh(att)
    return att


def start_campaign(db, provider, settings, c: Campaign) -> dict:
    if c.status in ("draft", "scheduled"):
        set_campaign_status(c, "running")
    elif c.status != "running":
        raise InvalidTransition(f"campaign is {c.status}")
    dispatched, skipped = 0, []
    for r in list(c.recipients):
        ok, why = is_eligible(c, r)
        if not ok:
            skipped.append({"recipient_id": r.id, "reason": why})
            continue
        if r.attempts:      # follow-up attempts only via retry_due (respects backoff)
            continue
        if dispatch(db, provider, settings, c, r):
            dispatched += 1
    refresh_status(db, c)
    db.commit()
    return {"dispatched": dispatched, "skipped": skipped}


def retry_due(db, provider, settings, c: Campaign, force: bool = False) -> dict:
    if c.status != "running":
        raise InvalidTransition("retries only run for running campaigns")
    now, dispatched = utcnow(), 0
    for r in list(c.recipients):
        last = r.attempts[-1] if r.attempts else None
        if not last or last.status not in RETRYABLE or not last.next_retry_at:
            continue
        if not force and last.next_retry_at > now:
            continue
        if dispatch(db, provider, settings, c, r):
            dispatched += 1
    refresh_status(db, c)
    db.commit()
    return {"dispatched": dispatched}


def refresh_status(db, c: Campaign) -> None:
    """Complete a running campaign once no recipient can still be (automatically) contacted."""
    if c.status != "running":
        return
    for r in c.recipients:
        if _live_attempt(r):
            return
        ok, _ = is_eligible(c, r)
        if ok and r.outcome == "pending" and (not r.attempts or r.attempts[-1].next_retry_at):
            return
    set_campaign_status(c, "completed")
