"""Live call conversation: greet -> listen -> classify -> (clarify once) -> close.

Transport-free state machine. A transport (see `exotel_ws`, to be written once Exotel's Voicebot
protocol is verified) feeds inbound PCM / keypad digits and plays back the returned actions.

Contract with the rest of Member 3:
  * Decisions come from `process_response` and spoken lines from `closing_line`, so the agent only ever
    says reviewed text and never guesses an unclear answer.
  * The result leaves as ONE `ProviderEvent(kind="response")` through `emit`, the same shape the webhook
    delivers today, so the backend needs no changes. Call status stays with Exotel's StatusCallback.

The clock is the amount of inbound audio received, so the transport must keep streaming audio (silence
included) for timeouts to fire.
"""
from collections.abc import Callable
from dataclasses import dataclass

from ..integrations.base import ProviderEvent
from ..intelligence.intent.taxonomy import Intent, NextAction
from ..intelligence.pipeline import IntentDecision, ResponseInput, process_response
from ..intelligence.policies.closing_lines import CLARIFY_LINE, REPROMPT_LINE, closing_line, prompt_line
from .audio import UtteranceSegmenter, pcm_duration_ms, pcm16_to_wav
from .dialogue import (ASK_AGAIN_KEYPAD, ASK_AGAIN_LINE, KEYPAD_CLARIFY, KEYPAD_REPROMPT, SWITCH_LINE, VOICEMAIL_CHECK_MS,
                       VOICEMAIL_LONG_MS, VOICEMAIL_PROBE_MS, detect_language_switch, looks_like_voicemail, question_topic)


@dataclass
class Say:
    text: str
    pcm: bytes


@dataclass
class Clear:
    """Stop any queued playback (caller interrupted)."""


@dataclass
class Hangup:
    delay_ms: int = 0       # let the closing line finish playing first


Action = Say | Clear | Hangup


class LiveSession:
    def __init__(self, *, provider_call_id: str, greeting: str, tts: Callable[[str], bytes],
                 stt: Callable[[bytes], str], emit: Callable[[ProviderEvent], None],
                 sample_rate: int = 8000, language: str = "en", info_answers: "dict[str, str] | Callable[[str], dict[str, str]] | None" = None,
                 barge_in: bool = False, no_speech_timeout_ms: int = 7000,
                 segmenter: UtteranceSegmenter | None = None,
                 on_end: Callable[["LiveSession"], None] | None = None,
                 conversational: bool = False, greeting_for: Callable[[str], str | None] | None = None,
                 detect_voicemail: bool = False, keypad_hint: bool = False,
                 voicemail_message: Callable[[str], str | None] | None = None):
        """`conversational=True` lets the caller switch language and ask known questions (venue, time, organiser, what the
        event is) without ending the call; the default keeps the original one-answer behaviour. `greeting_for(lang)`
        returns the opening in another language, used after a switch.
        `detect_voicemail=True` listens for a moment after pickup before speaking and hangs up on an answering machine
        (a recorded greeting is long; a person says a short "hello"); `voicemail_message(lang)` is an optional short note to
        leave first. `keypad_hint=True` also offers the keypad (1 yes, 2 no, ...) when the caller is silent or unclear."""
        self.call_id, self.greeting = provider_call_id, greeting
        self._tts, self._stt, self._emit, self._on_end = tts, stt, emit, on_end
        self._ended = False
        self.rate, self.language = sample_rate, language
        self.info_answers = info_answers or {}      # a dict, or a function of the reply language
        self.barge_in, self.no_speech_timeout_ms = barge_in, no_speech_timeout_ms
        self.seg = segmenter or UtteranceSegmenter(sample_rate=sample_rate)
        self.transcript: list[tuple[str, str]] = []     # (role, text); keep out of logs, it is personal data
        self.decision: IntentDecision | None = None
        self.done = False
        self._speaking_until = 0
        self._clarifications = 0
        self._reprompts = 0
        self.conversational, self._greeting_for = conversational, greeting_for
        self._switches = self._info_turns = 0
        self._lang_locked = False                      # the caller explicitly chose a language: keep using it
        self.detect_voicemail, self.keypad_hint, self._voicemail_note = detect_voicemail, keypad_hint, voicemail_message
        self.voicemail = False
        self._probing = detect_voicemail               # listen briefly before speaking, to tell a person from a machine

    # ---- transport entry points -------------------------------------------------------------
    def start(self) -> list[Action]:
        if self._probing:
            return []
        return [self._say(self.greeting)]

    def on_audio(self, pcm: bytes) -> list[Action]:
        if self.done:
            return []
        utterances = self.seg.feed(pcm)
        clock = self.seg.elapsed_ms
        if self._probing:
            return self._probe(utterances, clock)
        actions: list[Action] = []
        if clock < self._speaking_until:
            if not (self.barge_in and (utterances or self.seg.speech_ms >= 300)):
                self.seg.reset()                       # our own audio / talk-over: ignore
                return []
            actions.append(Clear())
            self._speaking_until = clock
        for utt in utterances:
            actions += self._on_utterance(utt)
            if self.done:
                return actions
        if (not utterances and not self.seg.in_speech
                and clock - self._speaking_until >= self.no_speech_timeout_ms):
            actions += self._on_silence()
        return actions

    def on_dtmf(self, digit: str) -> list[Action]:
        if self.done:
            return []
        self._probing = False
        actions: list[Action] = [Clear()]
        self._speaking_until = self.seg.elapsed_ms
        if self.conversational and digit.strip() == "4" and self._info_turns < 3:
            details = self._known_details()
            if details:                               # key 4 = "more information": say what we know, then ask again
                self._info_turns += 1
                actions.append(self._say(f"{details} {self._ask_again(self.language)}"))
                return actions
        decision = process_response(ResponseInput(dtmf=digit))
        if decision.intent == Intent.UNCLEAR and self._clarifications < 1:
            self._clarifications += 1
            actions.append(self._say(self._clarify_line(self.language)))
            return actions
        return actions + self._finish(decision, text=None, dtmf=digit)

    def on_stop(self) -> None:
        """Caller hung up or the stream ended. If no answer was reached, `on_end` (optional) is told once so the
        backend can record a no-response outcome; the normal result was already emitted by `_finish`."""
        self.done = True
        if self.decision is None and self._on_end is not None and not self._ended:
            self._ended = True
            self._on_end(self)

    # ---- internals --------------------------------------------------------------------------
    def _say(self, text: str) -> Say:
        pcm = self._tts(text)
        self._speaking_until = max(self._speaking_until, self.seg.elapsed_ms) + pcm_duration_ms(pcm, self.rate)
        self.transcript.append(("agent", text))
        return Say(text, pcm)

    def _lang(self, decision: IntentDecision) -> str:
        if self._lang_locked:
            return self.language
        return decision.language if decision.language in ("en", "ml", "hi", "ta") else self.language

    def _on_utterance(self, pcm: bytes) -> list[Action]:
        try:
            text = self._stt(pcm16_to_wav(pcm, self.rate))
        except Exception:                              # STT outage must not strand the caller
            decision = process_response(ResponseInput(audio_ref="stt-failed"))   # -> HUMAN review
            return self._finish(decision, text=None)
        self.transcript.append(("user", text))
        if self.detect_voicemail and looks_like_voicemail(text):
            return self._voicemail()
        if self.conversational:
            handled = self._converse(text)
            if handled is not None:
                return handled
        decision = process_response(ResponseInput(text=text))
        if decision.next_action == NextAction.CLARIFY and self._clarifications < 1:
            self._clarifications += 1
            return [self._say(self._clarify_line(self._lang(decision)))]
        return self._finish(decision, text=text)

    # ---- keypad wording and what we know -----------------------------------------------------
    def _clarify_line(self, lang: str) -> str:
        return prompt_line(KEYPAD_CLARIFY if self.keypad_hint else CLARIFY_LINE, lang)

    def _ask_again(self, lang: str) -> str:
        table = ASK_AGAIN_KEYPAD if self.keypad_hint else ASK_AGAIN_LINE
        return table.get(lang, table["en"])

    def _known_details(self) -> str:
        lang = self.language
        answers = self.info_answers(lang) if callable(self.info_answers) else self.info_answers
        parts = [answers[k].strip().rstrip(".।") for k in ("schedule", "venue", "organiser", "about") if answers.get(k)][:3]
        stop = "।" if lang == "hi" else "."
        return "".join(f"{p}{stop} " for p in parts).strip()

    # ---- answering machines ------------------------------------------------------------------
    def _probe(self, utterances: list[bytes], clock: int) -> list[Action]:
        """Pickup window: a person says a short "hello" and waits; a machine plays a long recorded greeting."""
        for utt in utterances:
            dur = pcm_duration_ms(utt, self.rate)
            if dur >= VOICEMAIL_LONG_MS:
                return self._voicemail()
            if dur >= VOICEMAIL_CHECK_MS:
                try:
                    text = self._stt(pcm16_to_wav(utt, self.rate))
                except Exception:
                    text = ""
                if looks_like_voicemail(text):
                    return self._voicemail()
            return self._end_probe()
        if self.seg.in_speech:
            return self._end_probe() if clock >= 20000 else []     # still talking: wait for the end of it
        return self._end_probe() if clock >= VOICEMAIL_PROBE_MS else []

    def _end_probe(self) -> list[Action]:
        self._probing = False
        self.seg.reset()
        return [self._say(self.greeting)]

    def _voicemail(self) -> list[Action]:
        """A machine answered. Say nothing personal; optionally leave a short note after a pause for the beep; report it."""
        self.voicemail, self.done, self._probing = True, True, False
        note = self._voicemail_note(self.language) if self._voicemail_note else None
        actions: list[Action] = [Hangup()]
        if note:
            pcm = bytes(int(self.rate * 1.5) * 2) + self._tts(note)
            actions = [Say(note, pcm), Hangup(delay_ms=pcm_duration_ms(pcm, self.rate))]
        if not self._ended and self._on_end is not None:
            self._ended = True
            self._on_end(self)
        return actions

    def _converse(self, text: str) -> list[Action] | None:
        """Conversational turns that do not end the call. Returns None when the normal flow should take over."""
        if self._switches < 2:
            lang = detect_language_switch(text, self.language)
            if lang:
                self._switches += 1
                self.language, self._lang_locked = lang, True
                self._clarifications = self._reprompts = 0
                opening = (self._greeting_for(lang) if self._greeting_for else None) or self._clarify_line(lang)
                return [self._say(f"{SWITCH_LINE[lang]} {opening}")]
        if self._info_turns >= 3:
            return None
        decision = process_response(ResponseInput(text=text))
        if decision.intent not in (Intent.INFO, Intent.UNCLEAR):
            return None                                # a clear yes / no / opt-out always wins over a question
        topic = decision.info_topic if decision.intent == Intent.INFO else None
        topic = topic or question_topic(text)
        lang = self._lang(decision)
        answers = self.info_answers(lang) if callable(self.info_answers) else self.info_answers
        approved = answers.get(topic or "")
        if not approved:
            return None                                # unknown question: the existing hand-over to a human applies
        self._info_turns += 1
        self._reprompts = 0
        stop = "।" if lang == "hi" else "."
        return [self._say(f"{approved.strip().rstrip('.।')}{stop} {self._ask_again(lang)}")]

    def _on_silence(self) -> list[Action]:
        if self._reprompts < 1:
            self._reprompts += 1
            return [self._say(prompt_line(KEYPAD_REPROMPT if self.keypad_hint else REPROMPT_LINE, self.language))]
        return self._finish(process_response(ResponseInput(text=None)), text=None)

    def _finish(self, decision: IntentDecision, text: str | None, dtmf: str | None = None) -> list[Action]:
        self.decision, self.done = decision, True
        lang = self._lang(decision)
        answers = self.info_answers(lang) if callable(self.info_answers) else self.info_answers
        approved = answers.get(decision.info_topic or "") if decision.intent == Intent.INFO else None
        line = closing_line(decision.intent.value, lang, approved)
        say = self._say(line)
        self._emit(ProviderEvent(f"{self.call_id}:response", self.call_id, "response", text=text, dtmf=dtmf))
        return [say, Hangup(delay_ms=pcm_duration_ms(say.pcm, self.rate))]
