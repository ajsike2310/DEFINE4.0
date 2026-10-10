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


# ---------------------------------------------------------------- keypad: spoken options and re-asks
KEYPAD_OPTIONS = {
    "en": "You can also use your keypad: press 1 to confirm, 2 if you cannot attend, 3 for a call back, 4 for more information, or 9 to stop receiving calls.",
    "hi": "आप कीपैड भी इस्तेमाल कर सकते हैं: पुष्टि के लिए 1, न आ पाने पर 2, वापस कॉल के लिए 3, ज़्यादा जानकारी के लिए 4, और कॉल बंद करवाने के लिए 9 दबाएँ।",
    "ta": "நீங்கள் கீபேடையும் பயன்படுத்தலாம்: உறுதிப்படுத்த 1, கலந்துகொள்ள முடியாவிட்டால் 2, மீண்டும் அழைக்க 3, மேலும் தகவலுக்கு 4, அழைப்புகளை நிறுத்த 9 அழுத்தவும்.",
}
KEYPAD_CLARIFY = {
    "en": "Sorry, I want to be sure. Will you attend the event? Please say yes or no, or press 1 for yes and 2 for no.",
    "hi": "माफ़ कीजिए, पक्का करने के लिए पूछ रहे हैं। क्या आप कार्यक्रम में शामिल होंगे? कृपया हाँ या ना कहें, या हाँ के लिए 1 और ना के लिए 2 दबाएँ।",
    "ta": "மன்னிக்கவும், உறுதிப்படுத்திக்கொள்ள கேட்கிறோம். நீங்கள் நிகழ்ச்சியில் கலந்துகொள்வீர்களா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள், அல்லது ஆம் என்றால் 1, இல்லை என்றால் 2 அழுத்தவும்.",
}
KEYPAD_REPROMPT = {
    "en": "Sorry, I did not hear you. You can also answer with your keypad: press 1 to confirm, 2 if you cannot attend, 3 for a call back, 4 for more information, or 9 to stop calls.",
    "hi": "माफ़ कीजिए, आवाज़ सुनाई नहीं दी। आप कीपैड से भी जवाब दे सकते हैं: पुष्टि के लिए 1, न आ पाने पर 2, वापस कॉल के लिए 3, जानकारी के लिए 4, कॉल बंद करने के लिए 9 दबाएँ।",
    "ta": "மன்னிக்கவும், உங்கள் குரல் கேட்கவில்லை. கீபேடிலும் பதிலளிக்கலாம்: உறுதிப்படுத்த 1, கலந்துகொள்ள முடியாவிட்டால் 2, மீண்டும் அழைக்க 3, தகவலுக்கு 4, நிறுத்த 9 அழுத்தவும்.",
}
ASK_AGAIN_KEYPAD = {
    "en": "Will you be attending? Say yes or no, or press 1 for yes and 2 for no.",
    "hi": "क्या आप शामिल होंगे? हाँ या ना कहें, या हाँ के लिए 1 और ना के लिए 2 दबाएँ।",
    "ta": "நீங்கள் கலந்துகொள்வீர்களா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள், அல்லது ஆம் என்றால் 1, இல்லை என்றால் 2 அழுத்தவும்.",
}
_MENTIONS_KEYS = re.compile(r"\b(press|dial)\b|दबा|அழுத்த", re.IGNORECASE)


def mentions_keypad(text: str) -> bool:
    return bool(_MENTIONS_KEYS.search(text or ""))


# ---------------------------------------------------------------- voicemail / answering machine
# Multi-word phrases only: a person saying "I'm not available, call me later" must never be mistaken for a machine.
_VOICEMAIL_PHRASES = (
    "leave a message", "leave your message", "leave me a message", "after the beep", "after the tone", "at the tone", "at the beep",
    "voicemail", "voice mail", "mailbox", "record your message", "please record", "unable to take your call", "cannot take your call",
    "can't take your call", "not available to take your call", "is not available right now", "the person you are calling",
    "the number you have dialed", "the number you have dialled", "the number you are calling", "is switched off", "not reachable",
    "currently unavailable", "is not answering", "please call again later",
    "संदेश छोड़", "मैसेज छोड़", "बीप के बाद", "वॉइसमेल", "वॉयस मेल", "आपके द्वारा डायल किया गया", "कॉल का जवाब नहीं", "स्विच ऑफ", "पहुँच से बाहर",
    "பீப் ஒலிக்குப் பிறகு", "செய்தியை விடுங்கள்", "செய்தி விடுங்கள்", "குரல் அஞ்சல்", "நீங்கள் அழைத்த எண்", "அழைப்பை ஏற்க முடியவில்லை", "ஸ்விட்ச் ஆஃப்",
)
VOICEMAIL_PROBE_MS = 1500        # how long to listen at pickup before speaking
VOICEMAIL_LONG_MS = 7000         # this much unbroken speech at pickup is a recorded greeting, not a person saying hello
VOICEMAIL_CHECK_MS = 3500        # speech longer than this at pickup is transcribed and checked for machine phrases


def looks_like_voicemail(text: str) -> bool:
    low = (text or "").lower()
    norm = normalize_text(text or "")
    return any(p in low or normalize_text(p) in norm for p in _VOICEMAIL_PHRASES)


VOICEMAIL_NOTE = {
    "en": "Hello, this is an automated call{org}{about}. We will try again later. Goodbye.",
    "hi": "नमस्ते, यह{org} एक स्वचालित कॉल है{about}। हम बाद में फिर कोशिश करेंगे। अलविदा।",
    "ta": "வணக்கம், இது{org} ஒரு தானியங்கி அழைப்பு{about}. நாங்கள் பிறகு மீண்டும் அழைக்கிறோம். வணக்கம்.",
}


def voicemail_message(event_name: str, organiser: str, lang: str) -> str:
    """The short note left on a machine. It names the organiser and event only: never the person, their answer or any detail."""
    lang = lang if lang in VOICEMAIL_NOTE else "en"
    org = {"en": f" from {organiser}", "hi": f" {organiser} की ओर से", "ta": f" {organiser} சார்பில்"}[lang] if organiser else ""
    about = {"en": f" about the {event_name} event", "hi": f", {event_name} कार्यक्रम के बारे में", "ta": f", {event_name} நிகழ்ச்சி பற்றி"}[lang] if event_name else ""
    return VOICEMAIL_NOTE[lang].format(org=org, about=about)
