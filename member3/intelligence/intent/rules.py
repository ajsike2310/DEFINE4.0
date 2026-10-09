"""Rule-based multilingual intent matcher.

Phrase lists are SMALL, hand-written examples for English, Malayalam script and
romanised Malayalam. They are not evidence of real-world language performance.
Matching is by normalized substring (whole-word for Latin script). Any conflict
between categories, or any hedging phrase, yields UNCLEAR: we prefer
under-claiming to a wrong confirmation.
"""
import re

from ..language.normalize import normalize_text
from .rules_hi_ta import HEDGES_HI_TA, PHRASES_HI_TA
from .taxonomy import Intent

PHRASES: dict[Intent, list[str]] = {
    Intent.OPT_OUT: [
        "do not call", "don't call", "stop calling", "remove my number",
        "unsubscribe", "never call", "stop these calls",
        "take me off", "dont ever call", "do not ever call", "remove me from", "stop calling",
        "വിളിക്കരുത്", "വിളിക്കല്ലേ", "vilikkaruth", "vilikkalle",
    ],
    Intent.CALLBACK: [
        "call me later", "call me tomorrow", "call back", "call again", "i am busy", "i'm busy",
        "busy now", "not a good time", "call me in", "call tomorrow",
        "call me after", "call me at", "call me back", "in a meeting", "i am driving", "im driving", "call later",
        "not now", "talk later",
        "പിന്നീട് വിളിക്കൂ", "നാളെ വിളിക്കൂ", "തിരക്കിലാണ്", "pinneed vilikku", "nale vilikku",
        "thirakkilanu", "pinne vilikku",
    ],
    Intent.INFO: [
        "more information", "more info", "what time", "where is", "where's the venue", "what is the venue",
        "venue address", "what is this", "tell me more", "who is this", "what is it about", "which date",
        "what is the schedule", "when does it start", "when is it",
        "where is it", "where will it be", "whats the venue", "what is the time", "whats the time", "what date",
        "what day", "which place", "where exactly", "what is the address",
        "കൂടുതൽ വിവരങ്ങൾ", "എപ്പോൾ", "എവിടെ", "kooduthal vivarangal", "eppol", "evide",
    ],
    Intent.ACK: [
        "noted", "got it", "understood", "i understand", "thank you", "thanks", "received", "ok noted",
        "okay noted", "അറിഞ്ഞു", "നന്ദി", "arinju", "nanni",
    ],
    Intent.DECLINE: [
        "will not come", "won't come", "can't come", "cannot come",
        "not coming", "not attending", "can't attend", "cannot attend", "no thanks", "not interested",
        "not going to come", "not going to attend", "not gonna come", "not able to come", "not able to attend",
        "unable to come", "unable to attend", "can't make it", "cannot make it", "won't make it",
        "won't be coming", "won't be attending", "won't be able to come", "won't be able to attend",
        "won't be able to make it", "will not be coming", "will not be attending", "will not be able to come",
        "will not be able to attend", "will not be able to make it",
        "not this time", "sorry no", "i cant", "i can not", "i wont", "i dont think i can", "i will not",
        "i decline", "decline", "no",
        "വരില്ല", "പറ്റില്ല", "ഇല്ല", "വേണ്ട", "varilla", "pattilla", "illa", "venda",
    ],
    Intent.CONFIRM: [
        "yes", "yeah", "yep", "i will attend", "i'll attend", "i will come", "i'll come",
        "i will be there", "i'll be there", "confirmed", "confirm", "sure", "okay", "ok", "sounds good",
        "count me in", "i can make it", "i cant wait", "cant wait", "i wont miss it", "wont miss it", "wouldnt miss it", "ill be coming", "i will be coming", "i am coming", "im coming",
        "i will join", "ill join", "i am attending", "im attending", "will attend", "will come", "definitely",
        "absolutely", "of course", "for sure", "yes please", "see you there", "why not", "i would love to",
        "അതെ", "ശരി", "വരാം", "വരും", "athe", "shari", "varam", "varum", "sheri",
    ],
}

HEDGES = [
    "maybe", "not sure", "i'll see", "i will see", "let me think", "might", "perhaps", "don't know",
    "probably", "depends", "not certain", "will try", "ill try", "i'll try", "try to", "cant promise",
    "if possible", "let you know", "ഒരുപക്ഷേ", "അറിയില്ല", "നോക്കാം", "orupakshe", "ariyilla", "nokkam",
]


# Hindi and Tamil lists live in rules_hi_ta.py so native speakers can review them in one place.
for _intent, _phrases in PHRASES_HI_TA.items():
    PHRASES[_intent].extend(_phrases)
HEDGES.extend(HEDGES_HI_TA)

_DEVANAGARI = re.compile("[ऀ-ॿ]")


def _whole_word(p: str) -> bool:
    """Latin and Devanagari phrases match as whole words. Malayalam and Tamil are agglutinative (suffixes attach to
    the stem), so their phrases match as substrings and must be long enough to avoid false hits."""
    return p.isascii() or bool(_DEVANAGARI.search(p))


def _contains(text: str, phrase: str) -> bool:
    p = normalize_text(phrase)
    if not p:
        return False
    if _whole_word(p):
        return f" {p} " in f" {text} "
    return p in text


def _parts(phrase: str) -> list[str]:
    """A phrase written "a+b" matches when ALL its parts are present, in any order. Used where speech recognition
    garbles the middle of a request (Tamil "இனி ... வேண்டாம்", "from now on ... don't") but its frame survives."""
    return [normalize_text(x) for x in phrase.split("+")]


def _length(phrase: str) -> int:
    return sum(len(x) for x in _parts(phrase)) + len(_parts(phrase)) - 1


def match_intents(text: str) -> tuple[set[Intent], list[str], bool]:
    """Return (matched intents, matched phrases, hedged)."""
    norm = normalize_text(text)
    hedged = any(_contains(norm, h) for h in HEDGES)
    found: set[Intent] = set()
    evidence: list[str] = []
    remaining = f" {norm} "
    # Longest phrases first; matched spans are consumed so "no thanks" is not
    # also counted as bare "no".
    entries = sorted(((p, i) for i, ps in PHRASES.items() for p in ps), key=lambda x: -_length(x[0]))
    for phrase, intent in entries:
        parts = [x for x in _parts(phrase) if x]
        if parts and all(_contains(remaining.strip(), x) for x in parts):
            found.add(intent)
            evidence.append(phrase)
            for n in parts:
                remaining = remaining.replace(f" {n} " if _whole_word(n) else n, "  ", 1)
    return found, evidence, hedged
