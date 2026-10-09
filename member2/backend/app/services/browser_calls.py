"""Browser demo calls: a person plays the participant. Simulated, never a phone call.

Replies (keypad, typed text or transcribed speech) go through the same event pipeline as every provider response,
so opt-out wins, ambiguity is never confirmation, and clarify-once applies.
"""
from sqlalchemy.orm import Session

from member3.integrations.base import ProviderEvent as PEvent
from member3.integrations.browser_demo.provider import BrowserDemoProvider
from member3.intelligence.policies.closing_lines import closing_line

from ..core.errors import ApiError
from ..models import CallAttempt, Campaign, Recipient
from ..repositories import attempts as attempts_repo
from ..repositories import campaigns as campaigns_repo
from ..repositories import followups as followups_repo
from ..repositories import intents as intents_repo
from ..repositories import recipients as recipients_repo
from . import campaigns as svc
from .events import apply_event

PROVIDER = "browser_demo"


def attempt_message(db: Session, a: CallAttempt) -> str:
    if a.mode == "clarify":
        return svc.CLARIFY_MESSAGES.get(a.call_language) or svc.CLARIFY_MESSAGES["en"]
    return campaigns_repo.get(db, a.campaign_id).messages.get(a.call_language, "")


def open_attempt(db: Session, aid: int) -> CallAttempt:
    a = attempts_repo.get(db, aid)
    if not a or a.provider != PROVIDER:
        raise ApiError(404, "not_found", "no browser demo call with that id")
    if a.status != "answered":
        raise ApiError(409, "call_not_open", f"this demo call is {a.status}; start a new one")
    return a


def start(db: Session, settings, c: Campaign, r: Recipient, mode: str) -> dict:
    if not c.is_demo:
        raise ApiError(409, "not_demo", "browser demo calls are only for sample (demo) campaigns, so a real "
                                         "participant's outcome is never set by someone role-playing")
    if mode not in ("main", "clarify"):
        raise ApiError(422, "validation_error", "mode must be main or clarify")
    prov = BrowserDemoProvider()
    if mode == "clarify":
        why = svc.clarify_blocker(c, r, prov)
    else:
        ok, reason = svc.is_eligible(c, r)
        why = None if ok else reason
        if not why and svc._live_attempt(r):
            why = "a call is already in progress"
        if not why and len(r.attempts) >= c.max_attempts:
            why = "no attempts left for this participant"
    if why:
        raise ApiError(409, "not_allowed", why)
    a = svc.dispatch(db, prov, settings, c, r, mode=mode)
    if not a:
        raise ApiError(409, "not_allowed", "this participant cannot be called right now")
    return {"attempt_id": a.id, "status": a.status, "mode": a.mode, "language": a.call_language,
            "message": attempt_message(db, a), "simulated": True, "participant": r.name}


def finish_reply(db: Session, settings, a: CallAttempt, *, text: str | None, dtmf: str | None) -> dict:
    apply_event(db, PROVIDER, a, PEvent(f"{a.provider_call_id}:response", a.provider_call_id, "response",
                                        text=text, dtmf=dtmf), settings)
    apply_event(db, PROVIDER, a, PEvent(f"{a.provider_call_id}:completed", a.provider_call_id, "status", "completed"),
                settings)
    db.refresh(a)
    rec = recipients_repo.get(db, a.recipient_id)
    ir = intents_repo.for_attempt(db, a.id)
    camp = campaigns_repo.get(db, a.campaign_id)
    # An unclear attendance answer gets exactly one spoken yes/no question (clarify-once rules apply).
    nxt = "clarify" if (a.mode == "main" and rec.outcome == "unclear"
                        and not svc.clarify_blocker(camp, rec, BrowserDemoProvider())) else "close"
    return {"attempt_id": a.id, "status": a.status, "heard": text, "outcome": rec.outcome, "simulated": True, "next": nxt,
            "intent": ir.intent if ir else None, "method": ir.method if ir else None,
            "next_action": ir.next_action if ir else None, "needs_review": ir.needs_review if ir else None,
            "evidence": ir.evidence if ir else None, "notes": ir.notes if ir else []}


def hangup(db: Session, settings, a: CallAttempt) -> dict:
    """Ends the demo call with no reply. The participant stays as they were; nothing is guessed."""
    apply_event(db, PROVIDER, a, PEvent(f"{a.provider_call_id}:completed", a.provider_call_id, "status", "completed"),
                settings)
    db.refresh(a)
    return {"attempt_id": a.id, "status": a.status, "simulated": True}


def closing_for(db: Session, aid: int) -> str:
    """The agent's closing line for a finished call: fixed text by classified intent, plus the organiser's approved
    answer for a question. Never free text."""
    a = attempts_repo.get(db, aid)
    if not a or a.provider != PROVIDER:
        raise ApiError(404, "not_found", "no browser demo call with that id")
    ir = intents_repo.for_attempt(db, a.id)
    if not ir:
        raise ApiError(409, "no_reply", "this call has no recorded reply to respond to")
    fu = followups_repo.send_information_for_intent(db, ir.id)
    marker = "Approved answer: "
    answer = fu.note.split(marker, 1)[1] if fu and marker in (fu.note or "") else None
    return closing_line(ir.intent, a.call_language, answer)
