"""Script-based language hint. NOT a real language-ID model.

Malayalam, Devanagari (reported as Hindi) and Tamil are detected by Unicode block. Latin-script text is reported as
'en' even though it may be romanised Malayalam/Hindi/Tamil; the rule classifier handles common romanised phrases
separately. Devanagari is also used by Marathi and Nepali, which this cannot tell apart from Hindi.
"""
import re

_SCRIPTS = {
    "ml": re.compile(r"[ഀ-ൿ]"),
    "hi": re.compile(r"[ऀ-ॿ]"),
    "ta": re.compile(r"[஀-௿]"),
    "en": re.compile(r"[A-Za-z]"),
}


def detect_language(text: str) -> str:
    """Return 'ml', 'hi', 'ta', 'en', 'mixed' (more than one script) or 'unknown'."""
    present = [lang for lang, rx in _SCRIPTS.items() if rx.search(text)]
    if not present:
        return "unknown"
    return present[0] if len(present) == 1 else "mixed"
