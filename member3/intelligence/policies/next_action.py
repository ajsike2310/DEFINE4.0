"""Maps a classified intent to a next action. Central, testable decision layer."""
import re
from datetime import datetime, timedelta, timezone

from ..intent.taxonomy import Intent, NextAction
from ..language.normalize import normalize_text

_REL = re.compile(r"\bin (\d{1,2}) (minute|minutes|min|hour|hours|hr|hrs)\b")


def parse_requested_time(norm_text: str, now: datetime | None = None) -> datetime | None:
    """Only interpret unambiguous relative offsets ("in 2 hours"). Anything
    vaguer ("tomorrow", "later") returns None so a human/clarification must
    supply the time instead of us guessing."""
    now = now or datetime.now(timezone.utc)
    m = _REL.search(norm_text)
    if not m:
        return None
    n = int(m.group(1))
    return now + (timedelta(minutes=n) if m.group(2).startswith("min") else timedelta(hours=n))


_CLOCK = re.compile(r"\b(after|before|at|around)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b")
_VENUE = tuple(normalize_text(k) for k in (
    "venue", "where", "location", "address", "evide", "എവിടെ",
    "कहाँ", "जगह", "स्थान", "पता क्या", "kahan", "jagah",
    "எங்கே", "எங்க இருக்கு", "இடம்", "முகவரி", "enge", "enga irukku"))
_SCHED = tuple(normalize_text(k) for k in (
    "what time", "when", "schedule", "timing", "which date", "eppol", "എപ്പോൾ",
    "कब", "कितने बजे", "समय", "तारीख", "कौन सा दिन", "किस दिन", "kab", "kitne baje",
    "எப்போது", "நேரம்", "தேதி", "மணிக்கு", "eppodhu", "enna neram"))


def extract_time_hint(norm_text: str) -> str | None:
    """Human-readable clock hint such as 'after 5 PM'. The DATE is unknown, so this is
    only a note for the organiser and never becomes a scheduled time."""
    m = _CLOCK.search(norm_text)
    if not m:
        return None
    prefix, h, mins, ap = m.groups()
    return f"{prefix + ' ' if prefix else ''}{h}{':' + mins if mins else ''} {ap.upper()}"


def info_topic(norm_text: str) -> str | None:
    """'venue' | 'schedule' | None. Used to look up ORGANISER-APPROVED event info only."""
    if any(k in norm_text for k in _VENUE):
        return "venue"
    if any(k in norm_text for k in _SCHED):
        return "schedule"
    return None


def select_next_action(intent: Intent) -> NextAction:
    return {
        Intent.CONFIRM: NextAction.RECORD_OUTCOME,
        Intent.ACK: NextAction.RECORD_OUTCOME,
        Intent.DECLINE: NextAction.RECORD_OUTCOME,
        Intent.CALLBACK: NextAction.CREATE_FOLLOWUP,
        Intent.INFO: NextAction.SEND_INFO,
        Intent.OPT_OUT: NextAction.SUPPRESS_CONTACT,
        Intent.UNCLEAR: NextAction.CLARIFY,
        Intent.HUMAN: NextAction.HUMAN_REVIEW,
    }[intent]
