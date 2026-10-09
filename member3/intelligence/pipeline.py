"""Response pipeline: raw input -> (transcribe) -> normalize -> classify -> decide.

Keypad input is authoritative; free text uses the rule matcher; audio-only
without a transcriber is HUMAN review (never guessed). `score` is an internal
heuristic indicator, NOT a calibrated probability.
"""
from dataclasses import dataclass, field
from datetime import datetime

from .intent.rules import match_intents
from .intent.taxonomy import DTMF_MAP, Intent, NextAction
from .language.detect import detect_language
from .language.normalize import normalize_text
from .policies.next_action import extract_time_hint, info_topic, parse_requested_time, select_next_action
from .transcription.base import NullTranscriber, Transcriber, TranscriptionUnavailable


@dataclass
class ResponseInput:
    text: str | None = None
    dtmf: str | None = None
    audio_ref: str | None = None


@dataclass
class IntentDecision:
    intent: Intent
    next_action: NextAction
    score: float                   # internal heuristic indicator, not a probability
    method: str                    # dtmf | rules | none
    language: str
    evidence: str                  # matched phrases / short normalized text (minimal)
    needs_review: bool
    requested_time: datetime | None = None
    notes: list[str] = field(default_factory=list)
    info_topic: str | None = None      # venue | schedule | None (information requests only)
    time_hint: str | None = None       # e.g. "after 5 PM"; informational, never auto-scheduled


def _decision(intent, score, method, language, evidence, review=False, notes=None, when=None):
    return IntentDecision(intent, select_next_action(intent), score, method, language,
                          evidence, review, when, notes or [])


def process_response(inp: ResponseInput, transcriber: Transcriber | None = None,
                     now: datetime | None = None) -> IntentDecision:
    transcriber = transcriber or NullTranscriber()
    if inp.dtmf:
        digit = inp.dtmf.strip()
        intent = DTMF_MAP.get(digit)
        if intent:
            return _decision(intent, 1.0, "dtmf", "unknown", f"dtmf:{digit}")
        return _decision(Intent.UNCLEAR, 0.0, "dtmf", "unknown", f"dtmf:{digit[:4]}",
                         notes=["unmapped keypad digit"])
    text = inp.text
    if not text and inp.audio_ref:
        try:
            text = transcriber.transcribe(inp.audio_ref)
        except TranscriptionUnavailable:
            return _decision(Intent.HUMAN, 0.0, "none", "unknown", "", True,
                             ["audio received but no transcription service available"])
    if not text or not normalize_text(text):
        return _decision(Intent.UNCLEAR, 0.0, "none", "unknown", "", False, ["empty response"])

    lang = detect_language(text)
    norm = normalize_text(text)
    found, evidence, hedged = match_intents(text)
    ev = ", ".join(evidence)[:200]
    if hedged:
        return _decision(Intent.UNCLEAR, 0.2, "rules", lang, ev or norm[:120], True, ["hedging language"])
    if len(found) > 1 and Intent.ACK in found:
        found.discard(Intent.ACK)      # "yes, thanks" is a confirmation; thanks adds nothing
    if len(found) == 1:
        intent = next(iter(found))
        notes: list[str] = []
        when = parse_requested_time(norm, now) if intent == Intent.CALLBACK else None
        hint = extract_time_hint(norm) if intent == Intent.CALLBACK else None
        if intent == Intent.CALLBACK and when is None:
            notes.append("callback time not reliably stated; follow-up left pending")
        d = _decision(intent, 0.8, "rules", lang, ev, False, notes, when)
        d.time_hint = hint
        d.info_topic = info_topic(norm) if intent == Intent.INFO else None
        return d
    if len(found) > 1:
        # Opt-out wins: honouring a do-not-call request is the safe direction.
        if Intent.OPT_OUT in found:
            return _decision(Intent.OPT_OUT, 0.7, "rules", lang, ev, True, ["mixed signals; opt-out honoured"])
        return _decision(Intent.UNCLEAR, 0.1, "rules", lang, ev, True,
                         ["conflicting signals: " + ", ".join(sorted(i.value for i in found))])
    return _decision(Intent.UNCLEAR, 0.0, "rules", lang, norm[:120], True, ["no known phrase matched"])
