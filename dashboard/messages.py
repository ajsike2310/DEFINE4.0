"""Message templates and per-person rendering.

A campaign template uses {variables}. For each person the dashboard fills them in (their own name, the event's spoken
date/time, any extra CSV column such as {amount}); a person's own message *in that campaign* (`calls.custom_message`, passed in as `participant["custom_message"]`)
replaces the template entirely.
Hindi and Tamil wording is not native-reviewed (see member3/NATIVE_REVIEW.md)."""
import re
from datetime import date, datetime
from datetime import time as dtime

from member3.live.campaign import spoken_date, spoken_time

LANGUAGES = {"en": "English", "hi": "Hindi", "ta": "Tamil"}
PURPOSES = {"invite": "Invitation / RSVP", "reminder": "Reminder", "update": "Event update",
            "thanks": "Thank-you / follow-up"}
ASKS_QUESTION = {"invite", "reminder"}          # these end by asking the person to answer yes / no

EVENT_TYPES = {
    "webinar": {"label": "Webinar", "mode": "online", "kind": "generic"},
    "hackathon": {"label": "Hackathon", "mode": "in_person", "kind": "generic"},
    "seminar": {"label": "Seminar", "mode": "in_person", "kind": "generic"},
    "workshop": {"label": "Workshop", "mode": "in_person", "kind": "generic"},
    "conference": {"label": "Conference", "mode": "in_person", "kind": "generic"},
    "clinic": {"label": "Clinic appointment", "mode": "in_person", "kind": "clinic"},
    "school": {"label": "School / parent meeting", "mode": "in_person", "kind": "school"},
    "payment": {"label": "Payment reminder", "mode": "online", "kind": "payment"},
    "custom": {"label": "Other", "mode": "in_person", "kind": "generic"},
}

_NOUN = {   # how the event type is said on the call
    "webinar": {"en": "webinar", "hi": "वेबिनार", "ta": "வெபினார்"},
    "hackathon": {"en": "hackathon", "hi": "हैकाथॉन", "ta": "ஹேக்கத்தான்"},
    "seminar": {"en": "seminar", "hi": "सेमिनार", "ta": "கருத்தரங்கு"},
    "workshop": {"en": "workshop", "hi": "कार्यशाला", "ta": "பயிலரங்கு"},
    "conference": {"en": "conference", "hi": "सम्मेलन", "ta": "மாநாடு"},
}

_G = {   # generic events
    "invite": {
        "en": "Hello {first_name}! This is an automated call from {organiser}. You are invited to the {event} {event_type}{when}.{where} Will you be attending?",
        "hi": "नमस्ते {first_name}! यह {organiser} की ओर से एक स्वचालित कॉल है। आपको {event} {event_type} में आमंत्रित किया गया है।{when}{where} क्या आप शामिल होंगे?",
        "ta": "வணக்கம் {first_name}! இது {organiser} சார்பில் ஒரு தானியங்கி அழைப்பு. {event} {event_type}க்கு உங்களை அழைக்கிறோம்.{when}{where} நீங்கள் கலந்துகொள்வீர்களா?"},
    "reminder": {
        "en": "Hello {first_name}! This is a reminder from {organiser} about the {event} {event_type}{when}.{where} Can we confirm that you will be attending?",
        "hi": "नमस्ते {first_name}! यह {organiser} की ओर से {event} {event_type} की याद दिलाने वाली कॉल है।{when}{where} क्या हम आपकी उपस्थिति पक्की मानें?",
        "ta": "வணக்கம் {first_name}! இது {organiser} சார்பில் {event} {event_type} பற்றிய நினைவூட்டல்.{when}{where} நீங்கள் கலந்துகொள்வதை உறுதிப்படுத்தலாமா?"},
    "update": {
        "en": "Hello {first_name}, this is {organiser} with an update on the {event} {event_type}.{when}{where} Thank you.",
        "hi": "नमस्ते {first_name}, {organiser} की ओर से {event} {event_type} की नई जानकारी।{when}{where} धन्यवाद।",
        "ta": "வணக்கம் {first_name}, {organiser} சார்பில் {event} {event_type} பற்றிய புதிய தகவல்.{when}{where} நன்றி."},
    "thanks": {
        "en": "Hello {first_name}, this is {organiser}. Thank you for being part of the {event} {event_type}. We hope to see you again.",
        "hi": "नमस्ते {first_name}, यह {organiser} है। {event} {event_type} का हिस्सा बनने के लिए धन्यवाद। उम्मीद है आपसे फिर मिलेंगे।",
        "ta": "வணக்கம் {first_name}, இது {organiser}. {event} {event_type}ல் பங்கேற்றதற்கு நன்றி. மீண்டும் சந்திப்போம்."},
}
_KIND = {
    "clinic": {
        "reminder": {
            "en": "Hello {first_name}! This is a reminder from {organiser}. You have an appointment{when}.{where} Will you be able to come?",
            "hi": "नमस्ते {first_name}! {organiser} की ओर से याद दिलाना है कि आपकी अपॉइंटमेंट है।{when}{where} क्या आप आ पाएँगे?",
            "ta": "வணக்கம் {first_name}! {organiser} சார்பில் நினைவூட்டல். உங்களுக்கு ஒரு சந்திப்பு உள்ளது.{when}{where} நீங்கள் வருவீர்களா?"}},
    "school": {
        "reminder": {
            "en": "Hello {first_name}! This is {organiser} calling about the {event}.{when}{where} Will you be able to attend?",
            "hi": "नमस्ते {first_name}! यह {organiser} की ओर से {event} के बारे में कॉल है।{when}{where} क्या आप आ पाएँगे?",
            "ta": "வணக்கம் {first_name}! {organiser} சார்பில் {event} பற்றிய அழைப்பு.{when}{where} நீங்கள் வருவீர்களா?"}},
    "payment": {
        "reminder": {
            "en": "Hello {first_name}! This is a reminder from {organiser}. A payment of {amount} for {event} is due.{when} Will you be able to pay on time?",
            "hi": "नमस्ते {first_name}! {organiser} की ओर से याद दिलाना है कि {event} के लिए {amount} का भुगतान देय है।{when} क्या आप समय पर भुगतान कर पाएँगे?",
            "ta": "வணக்கம் {first_name}! {organiser} சார்பில் நினைவூட்டல். {event}க்கான {amount} செலுத்த வேண்டும்.{when} நீங்கள் சரியான நேரத்தில் செலுத்துவீர்களா?"}},
}

BUILTIN_VARS = ["name", "first_name", "event", "event_type", "date", "time", "venue", "organiser", "when", "where"]
_OPTIONAL_VARS = {"when", "where", "event_type"}         # may legitimately render empty


def default_template(event_type: str, purpose: str, lang: str) -> str:
    lang = lang if lang in LANGUAGES else "en"
    kind = EVENT_TYPES.get(event_type, EVENT_TYPES["custom"])["kind"]
    by_purpose = _KIND.get(kind, {}).get(purpose) or _G.get(purpose) or _G["invite"]
    return by_purpose[lang]


def _parse_date(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _parse_time(v) -> dtime | None:
    try:
        return datetime.strptime(str(v)[:5], "%H:%M").time()
    except (ValueError, TypeError):
        return None


def _safe_key(k: str) -> str:
    return re.sub(r"\W+", "_", str(k).strip().lower()).strip("_")


def variables_for(event: dict, participant: dict, lang: str) -> dict[str, str]:
    lang = lang if lang in LANGUAGES else "en"
    name = (participant.get("name") or "").strip()
    etype = event.get("type", "custom")
    d = spoken_date(_parse_date(event.get("event_date")), lang)
    t = spoken_time(_parse_time(event.get("event_time")), lang)
    online = event.get("mode") == "online"
    venue = event.get("venue") or ("online" if online else "")
    v = {"name": name, "first_name": name.split(" ")[0] if name else "", "event": event.get("name", ""),
         "event_type": _NOUN.get(etype, {}).get(lang, ""), "date": d, "time": t, "venue": venue,
         "organiser": event.get("organiser", "")}
    # {when}/{where} are used by the built-in templates and vanish cleanly when the data is missing.
    if lang == "hi":
        when = f"{d} को {t}" if d and t else (f"{d} को" if d else t)
        v["when"] = f" यह {when} होगा।" if when else ""
        v["where"] = (f" स्थान: {venue}।" if venue else "")
    elif lang == "ta":
        when = " ".join(p for p in (d, t) if p)
        v["when"] = f" இது {when} நடைபெறும்." if when else ""
        v["where"] = (f" இடம்: {venue}." if venue else "")
    else:
        v["when"] = (f" on {d}" + (f" at {t}" if t else "")) if d else (f" at {t}" if t else "")
        v["where"] = (" It will be held online." if online and not event.get("venue")
                      else f" The venue is {venue}." if venue else "")
    for k, val in (participant.get("fields") or {}).items():
        v.setdefault(_safe_key(k), str(val))
    return v


_VAR = re.compile(r"\{(\w+)\}")


def render(template: str, variables: dict[str, str]) -> tuple[str, list[str]]:
    """-> (text, names of variables that had no value). Missing variables render empty rather than as `{x}`."""
    missing: list[str] = []

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if variables.get(key):
            return variables[key]
        if key not in _OPTIONAL_VARS:
            missing.append(key)
        return ""
    text = _VAR.sub(sub, template or "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.!?।])", r"\1", text)
    return text.strip(), sorted(set(missing))


QUESTION = {"en": " Will you be attending?", "hi": " क्या आप शामिल होंगे?", "ta": " நீங்கள் கலந்துகொள்வீர்களா?"}


def compose(campaign: dict, event: dict, participant: dict) -> tuple[str, str, list[str]]:
    """-> (spoken text, language, missing variables) for one person in one campaign."""
    lang = participant.get("language") or campaign.get("language") or "en"
    lang = lang if lang in LANGUAGES else "en"
    own = (participant.get("custom_message") or "").strip()
    template = campaign["template"]
    camp_lang = campaign.get("language") or "en"
    if lang != camp_lang and template.strip() == default_template(event.get("type", "custom"), campaign.get("purpose", "invite"), camp_lang):
        # the organiser kept the suggested script, so each person gets it in their own language
        template = default_template(event.get("type", "custom"), campaign.get("purpose", "invite"), lang)
    text, missing = render(own or template, variables_for(event, participant, lang))
    if campaign.get("purpose") in ASKS_QUESTION and "?" not in text:
        text += QUESTION[lang]          # the agent needs a question to listen for an answer to
    return text, lang, missing
