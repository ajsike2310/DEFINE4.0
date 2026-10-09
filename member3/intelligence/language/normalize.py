import re
import unicodedata

# Keep letters AND combining vowel signs of Malayalam (U+0D00-0D7F), Devanagari (U+0900-097F) and Tamil (U+0B80-0BFF);
# without the explicit ranges the vowel signs count as punctuation and words fall apart.
_PUNCT = re.compile(r"[^\w\sഀ-ൿऀ-ॿ஀-௿]", re.UNICODE)
_WS = re.compile(r"\s+")


# Scribe often writes common loanwords in Latin inside Hindi/Tamil speech ("बाद में phone करना"). Both the incoming text
# and the phrase lists pass through here, so the Devanagari/Tamil spellings below become the Latin word and match.
_LOANWORDS = {
    "फोन": "phone", "कॉल": "call", "बिजी": "busy", "मीटिंग": "meeting", "नंबर": "number", "लिस्ट": "list",
    "इंटरेस्ट": "interest", "एड्रेस": "address", "टाइम": "time",
    "கால்": "call", "போன்": "phone", "பிஸி": "busy", "நம்பர்": "number",
}


def normalize_text(text: str) -> str:
    # Apostrophes are dropped (not spaced) so "don't" -> "dont"; phrase lists are normalized the same way.
    text = unicodedata.normalize("NFC", text or "").lower().replace("'", "").replace("’", "")
    # Devanagari spelling variants collapse: nukta is dropped (ज़->ज, फ़->फ) and chandrabindu becomes anusvara
    # (हाँ->हां, हूँ->हूं), so "हाँ" and "हां" are the same word.
    text = text.replace("़", "").replace("ँ", "ं")
    text = text.replace("।", " ").replace("॥", " ")        # Devanagari danda (full stop) is punctuation
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    return " ".join(_LOANWORDS.get(w, w) for w in text.split(" ")) if text else text
