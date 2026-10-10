"""Mid-call helpers for the conversational mode of `LiveSession`: spotting a request to switch language, and
recognising which known fact a caller is asking about.

Everything here is deterministic and conservative. The agent never improvises an answer: a question is answered only
from the organiser's own campaign data (`CampaignInfo.info_answers`), and anything else goes to a human as before.
Hindi and Tamil wording is not native-reviewed (see member3/NATIVE_REVIEW.md).
"""
import re

from ..intelligence.language.normalize import normalize_text
from ..intelligence.policies.next_action import info_topic

# Names a caller may use for a language: English words, the native script, and common romanisations.
_NAMES = {
    "en": ("english", "inglish", "अंग्रेज़ी", "अंग्रेजी", "इंग्लिश", "ஆங்கிலம்", "ஆங்கிலத்தில்", "angrezi"),
    "hi": ("hindi", "हिंदी", "हिन्दी", "ஹிந்தி", "இந்தி", "hindhi"),
    "ta": ("tamil", "tamizh", "thamizh", "तमिल", "தமிழ்", "தமிழில்"),
}
# A language name only counts as a request when it is phrased like one: "speak (in) Hindi", "in Tamil", "Hindi please",
# "हिंदी में बोलिए". A mention such as "my friend speaks Tamil" is not.
_BEFORE = re.compile(r"(\b(speak|talk|say|reply|respond|answer|switch|change|continue|go)\s+(in|to|into)?|\b(in|to|into))\s*$")
_AFTER = re.compile(r"^\s*[,.]?\s*(please|plz|pls|mein|me\b|bolo|boliye|baat|में|बोल|बात|कृपया|பேசு|தயவு)")


def detect_language_switch(text: str, current: str) -> str | None:
    """-> 'en' | 'hi' | 'ta' when the caller asks to continue in a different language, else None."""
    low = (text or "").lower().strip()
    hits = []
    for lang, names in _NAMES.items():
        if lang == current:
            continue
        for n in names:
            pos = low.find(n)
            if pos >= 0:
                hits.append((pos, pos + len(n)))
    hits.sort()
    for start, end in hits:
        if _BEFORE.search(low[max(0, start - 24):start]) or _AFTER.search(low[end:end + 16]) or len(low.split()) <= 3:
            return next(lang for lang, names in _NAMES.items() if any(low[start:end] == n for n in names))
    return None


# Questions beyond venue/schedule that the organiser's data can answer.
_TOPICS = {
    "organiser": ("organis", "organiz", "who is conducting", "who is hosting", "hosted by", "who are you", "who is calling",
                  "who's calling", "आयोजक", "कौन आयोजित", "कौन कर रहा", "आप कौन", "யார் நடத்", "ஏற்பாடு", "நீங்கள் யார்"),
    "about": ("what is this", "what's this", "what event", "which event", "about the event", "what is the event",
              "what is it about", "tell me about", "किस बारे", "क्या कार्यक्रम", "ये क्या है", "यह क्या है", "இது என்ன",
              "என்ன நிகழ்ச்சி", "எதைப் பற்றி"),
}


def question_topic(text: str) -> str | None:
    """'venue' | 'schedule' | 'organiser' | 'about' | None: what known fact the caller is asking for."""
    norm = normalize_text(text)
    topic = info_topic(norm)
    if topic:
        return topic
    low = (text or "").lower()
    for name, keys in _TOPICS.items():
        if any(k in low or normalize_text(k) in norm for k in keys):
            return name
    return None


SWITCH_LINE = {"en": "Sure, I will continue in English.",
               "hi": "ज़रूर, अब हम हिंदी में बात करेंगे।",
               "ta": "சரி, இனி தமிழில் பேசுகிறேன்."}
ASK_AGAIN_LINE = {"en": "Will you be attending?", "hi": "क्या आप शामिल होंगे?", "ta": "நீங்கள் கலந்துகொள்வீர்களா?"}
