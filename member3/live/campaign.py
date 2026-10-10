"""Campaign data for a live call: what to say, and how the WebSocket finds the right campaign for a call.

The Exotel stream only tells us `call_sid` (custom parameters are not delivered on this API), so the backend
registers a `CallContext` under the Sid that `ExotelProvider.initiate_call` returned, right after dialling.

Greetings and "where / when" answers exist in English, Hindi and Tamil (`CampaignInfo.language`). The Hindi and Tamil
wording is not native-reviewed. Malayalam campaigns still get the English greeting.
"""
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as dtime
from typing import Protocol

from .dialogue import KEYPAD_OPTIONS

_MONTHS = {
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    "ta": ["ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்",
           "நவம்பர்", "டிசம்பர்"],
}
_DAY_PARTS = {
    "hi": {"morning": "सुबह", "noon": "दोपहर", "evening": "शाम", "night": "रात"},
    "ta": {"morning": "காலை", "noon": "மதியம்", "evening": "மாலை", "night": "இரவு"},
}


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _part_of_day(hour: int, lang: str) -> str:
    key = "morning" if 5 <= hour < 12 else "noon" if 12 <= hour < 16 else "evening" if 16 <= hour < 20 else "night"
    return _DAY_PARTS[lang][key]


def spoken_date(d: date | str | None, lang: str = "en") -> str:
    if not d:
        return ""
    if isinstance(d, date):
        if lang == "hi":
            return f"{d.day} {_MONTHS['hi'][d.month - 1]}"
        if lang == "ta":
            return f"{_MONTHS['ta'][d.month - 1]} {d.day} ஆம் தேதி"
        return f"{d.strftime('%B')} {_ordinal(d.day)}"
    return str(d).strip()


def spoken_time(t: dtime | datetime | str | None, lang: str = "en") -> str:
    if not t:
        return ""
    if isinstance(t, datetime):
        t = t.time()
    if isinstance(t, dtime):
        h = t.hour % 12 or 12
        clock = f"{h}" if t.minute == 0 else f"{h}:{t.minute:02d}"
        if lang == "hi":
            return f"{_part_of_day(t.hour, 'hi')} {clock} बजे"
        if lang == "ta":
            return f"{_part_of_day(t.hour, 'ta')} {clock} மணிக்கு"
        return f"{clock} {'AM' if t.hour < 12 else 'PM'}"
    return str(t).strip()


@dataclass
class CampaignInfo:
    name: str
    venue: str = ""
    event_date: date | str | None = None
    event_time: dtime | datetime | str | None = None
    organiser: str = ""
    language: str = "en"                       # language of the greeting and fallback for agent lines: en | hi | ta | ml
    greeting_override: str | None = None       # organiser-approved full script, used instead of the template
    keypad: bool = False                       # also offer the keypad (1 yes, 2 no, 3 call back, ...) in the built-in greeting
    description: str = ""                      # one or two organiser-written sentences about the event (answers "what is this?")

    def when(self, lang: str = "en") -> str:
        d, tm = spoken_date(self.event_date, lang), spoken_time(self.event_time, lang)
        if lang == "hi":
            return f"{d} को {tm}" if d and tm else (f"{d} को" if d else tm)
        if lang == "ta":
            return " ".join(p for p in (d, tm) if p)
        return " at ".join(p for p in (d, tm) if p)

    def info_answers(self, lang: str | None = None) -> dict[str, str]:
        """Answers to 'where / when' questions, in the language the caller used (English if unsupported).
        Built only from the organiser's own campaign data."""
        lang = lang if lang in ("hi", "ta") else "en"
        when = self.when(lang)
        out: dict[str, str] = {}
        if lang == "hi":
            if self.venue:
                out["venue"] = f"कार्यक्रम का स्थान {self.venue} है"
            if when:
                out["schedule"] = f"कार्यक्रम {when} आयोजित होगा"
        elif lang == "ta":
            if self.venue:
                out["venue"] = f"நிகழ்ச்சி நடைபெறும் இடம் {self.venue}"
            if when:
                out["schedule"] = f"நிகழ்ச்சி {when} நடைபெறும்"
        else:
            if self.venue:
                out["venue"] = f"The event will take place at {self.venue}"
            if when:
                out["schedule"] = f"The event is {'on' if self.event_date else 'at'} {when}"
        if self.organiser:
            out["organiser"] = {"hi": f"यह कार्यक्रम {self.organiser} आयोजित कर रहे हैं",
                                "ta": f"இந்த நிகழ்ச்சியை {self.organiser} நடத்துகிறார்கள்"}.get(
                lang, f"This event is organised by {self.organiser}")
        if self.description.strip():
            out["about"] = self.description.strip()
        return out


@dataclass
class CallContext:
    provider_call_id: str                      # the Exotel call Sid
    attempt_id: int | str
    participant_id: str
    campaign_id: str
    campaign: CampaignInfo
    participant_name: str = ""


def build_greeting(c: CampaignInfo, participant_name: str = "") -> str:
    text = _greeting(c, participant_name)
    if c.keypad and not c.greeting_override:
        text += " " + KEYPAD_OPTIONS[c.language if c.language in ("hi", "ta") else "en"]
    return text


def _greeting(c: CampaignInfo, participant_name: str = "") -> str:
    if c.greeting_override:
        return c.greeting_override.strip()
    first = participant_name.strip().split(" ")[0] if participant_name.strip() else ""
    lang = c.language if c.language in ("hi", "ta") else "en"
    when = c.when(lang)
    if lang == "hi":
        org = f" {c.organiser} की ओर से" if c.organiser else ""
        event = f" {when} आयोजित होगा" if when else " के बारे में यह कॉल है"
        where = f" स्थान: {c.venue}।" if c.venue else ""
        return (f"नमस्ते{' ' + first if first else ''}! यह{org} एक स्वचालित कॉल है। {c.name} कार्यक्रम{event}।{where} "
                "क्या आप शामिल होंगे?")
    if lang == "ta":
        org = f" {c.organiser} சார்பில்" if c.organiser else ""
        event = f" {when} நடைபெறும்" if when else " பற்றிய அழைப்பு இது"
        where = f" இடம்: {c.venue}." if c.venue else ""
        return (f"வணக்கம்{' ' + first if first else ''}! இது{org} ஒரு தானியங்கி அழைப்பு. {c.name} நிகழ்ச்சி{event}.{where} "
                "நீங்கள் கலந்துகொள்வீர்களா?")
    intro = f"Hello{' ' + first if first else ''}! This is an automated call"
    if c.organiser:
        intro += f" from {c.organiser}"
    about = f" about the {c.name} event"
    if when:
        about += f" {'on' if c.event_date else 'at'} {when}"
    where = f" The event will take place at {c.venue}." if c.venue else ""
    return f"{intro}{about}.{where} Will you be attending?"


class CallContextSource(Protocol):
    def get(self, call_sid: str, wait_s: float = 0.0) -> CallContext | None: ...


class InMemoryCallRegistry:
    """Single-process registry. Run ONE worker, or replace it with a shared-store source (same `get` signature)."""

    def __init__(self, on_register: Callable[[CallContext], None] | None = None, max_items: int = 5000):
        self._items: dict[str, CallContext] = {}
        self._lock = threading.Lock()
        self.on_register, self.max_items = on_register, max_items

    def register(self, ctx: CallContext) -> None:
        with self._lock:
            if len(self._items) >= self.max_items:                 # drop the oldest; calls are short-lived
                self._items.pop(next(iter(self._items)))
            self._items[ctx.provider_call_id] = ctx
        if self.on_register:
            self.on_register(ctx)

    def forget(self, call_sid: str) -> None:
        with self._lock:
            self._items.pop(call_sid, None)

    def get(self, call_sid: str, wait_s: float = 0.0) -> CallContext | None:
        """Waits briefly: the call can connect a moment before the backend finishes registering it."""
        deadline = time.monotonic() + wait_s
        while True:
            with self._lock:
                ctx = self._items.get(call_sid)
            if ctx or time.monotonic() >= deadline:
                return ctx
            time.sleep(0.05)
