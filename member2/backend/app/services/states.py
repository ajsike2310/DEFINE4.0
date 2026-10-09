"""Centralised state rules. Call status (technical) is separate from recipient outcome (meaning)."""

CALL_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"initiating", "cancelled", "failed"},
    # "completed" straight from initiating/ringing covers a terminal-only provider callback (the 'answered'
    # event may be lost or never subscribed); the service then stamps answered_at.
    "initiating": {"ringing", "answered", "completed", "failed", "busy", "no_answer", "voicemail", "cancelled"},
    "ringing": {"answered", "completed", "failed", "busy", "no_answer", "voicemail", "cancelled"},
    "answered": {"completed", "failed"},
    "completed": set(), "failed": set(), "busy": set(), "no_answer": set(),
    "voicemail": set(), "cancelled": set(),
}
TERMINAL_CALL = {s for s, nxt in CALL_TRANSITIONS.items() if not nxt}
# Only these technical outcomes can trigger an automatic retry (never intent outcomes).
RETRYABLE = {"failed", "busy", "no_answer", "voicemail"}

CAMPAIGN_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"scheduled", "running", "cancelled"},
    "scheduled": {"running", "cancelled", "draft"},
    "running": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

# Recipient outcomes after which the system must not call again automatically.
RESOLVED_OUTCOMES = {"confirmed", "declined", "opted_out", "information_requested", "acknowledged",
                     "callback_requested", "unclear", "human_required"}
# Outcomes that still allow (bounded) technical retries.
OPEN_OUTCOMES = {"pending", "no_response"}

INTENT_TO_OUTCOME = {
    "confirm": "confirmed", "decline": "declined", "callback_requested": "callback_requested",
    "information_requested": "information_requested", "opt_out": "opted_out",
    "acknowledgement": "acknowledged",
    "unclear": "unclear", "human_required": "human_required",
}


class InvalidTransition(Exception):
    pass


def check_call_transition(current: str, new: str) -> None:
    if new not in CALL_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"call status {current} -> {new} not allowed")


def check_campaign_transition(current: str, new: str) -> None:
    if new not in CAMPAIGN_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"campaign status {current} -> {new} not allowed")
