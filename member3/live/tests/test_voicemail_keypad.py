"""Answering-machine detection and keypad prompts (both opt-in; the default one-answer behaviour is covered in test_live)."""
import pytest

from member3.live.campaign import CampaignInfo, build_greeting
from member3.live.dialogue import KEYPAD_OPTIONS, looks_like_voicemail, mentions_keypad, voicemail_message
from member3.live.session import Clear, Hangup, Say
from member3.live.tests.test_live import make, quiet, speak, tone

INFO = {"en": {"venue": "The event is at Main Hall", "schedule": "The event is on May 5th at 10 AM"}}


def vm(replies=(), **kw):
    kw.setdefault("detect_voicemail", True)
    return make(list(replies), info_answers=lambda lang: INFO.get(lang, INFO["en"]), **kw)


@pytest.mark.parametrize("text,yes", [
    ("Hi, you have reached Priya. Please leave a message after the beep.", True),
    ("The person you are calling is not available. Please leave your message after the tone.", True),
    ("The number you have dialled is switched off.", True),
    ("आपके द्वारा डायल किया गया नंबर उपलब्ध नहीं है, कृपया बीप के बाद संदेश छोड़ें", True),
    ("பீப் ஒலிக்குப் பிறகு செய்தியை விடுங்கள்", True),
    ("I'm not available right now, call me later", False),          # a person: never a machine
    ("Yes who is this?", False), ("Hello? Can you hear me", False)])
def test_voicemail_phrases(text, yes):
    assert looks_like_voicemail(text) is yes


def test_a_person_saying_hello_gets_the_greeting_after_the_pickup_window():
    s, events = vm(["Hello"])
    assert s.start() == []                                             # listens first, says nothing yet
    assert s.on_audio(tone(600)) == []
    out = s.on_audio(quiet(900))                                       # "hello" ended: short, so a person
    assert [type(a) for a in out] == [Say] and out[0].text == "Hello, will you attend?" and not s.voicemail


def test_silence_at_pickup_still_gets_the_greeting():
    s, _ = vm()
    s.start()
    out = s.on_audio(quiet(1700))
    assert [type(a) for a in out] == [Say] and not s.voicemail


def test_a_long_recorded_greeting_is_a_machine_even_without_known_phrases():
    s, events = vm()
    ended = []
    s._on_end = lambda sess: ended.append(sess)
    s.start()
    out = s.on_audio(tone(8000)) + s.on_audio(quiet(900))
    assert [type(a) for a in out] == [Hangup] and s.voicemail and s.done
    assert len(ended) == 1 and s.decision is None                      # reported once, with no answer recorded
    s.on_stop()
    assert len(ended) == 1 and events == []                            # no second report, no response event


def test_a_medium_greeting_is_transcribed_and_matched_on_phrases():
    s, _ = vm(["Please leave a message after the beep"])
    s.start()
    out = s.on_audio(tone(4500)) + s.on_audio(quiet(900))
    assert [type(a) for a in out] == [Hangup] and s.voicemail
    s2, _ = vm(["yes hello who am I speaking with right now please"])
    s2.start()
    out = s2.on_audio(tone(4500)) + s2.on_audio(quiet(900))
    assert [type(a) for a in out] == [Say] and not s2.voicemail        # a talkative person is still greeted


def test_optional_short_note_names_only_the_organiser_and_event_after_a_pause_for_the_beep():
    s, _ = vm(voicemail_message=lambda lang: voicemail_message("TechFest", "Acme College", lang))
    s.start()
    out = s.on_audio(tone(8000)) + s.on_audio(quiet(900))
    assert [type(a) for a in out] == [Say, Hangup]
    assert out[0].text == "Hello, this is an automated call from Acme College about the TechFest event. We will try again later. Goodbye."
    assert out[0].pcm[:3000] == bytes(3000)                            # leading silence so the note lands after the beep
    assert "Priya" not in out[0].text and out[1].delay_ms > 0


def test_a_machine_that_only_starts_after_our_greeting_is_still_caught():
    s, _ = vm(["Please leave your message after the tone"], detect_voicemail=True)
    s.start()
    s.on_audio(quiet(1700))                                            # pickup was silent, greeting played
    out = speak(s)
    assert [type(a) for a in out] == [Hangup] and s.voicemail


def test_default_mode_never_probes_or_hangs_up_on_machines():
    s, _ = make(["Please leave a message after the beep"])
    assert isinstance(s.start()[0], Say)                               # speaks at once, exactly as before
    out = speak(s)
    assert s.voicemail is False and "I want to be sure" in out[0].text   # treated as an ordinary unclear reply instead


# ------------------------------------------------------------------ keypad
def test_keypad_keys_resolve_the_call_at_any_point():
    for digit, intent in (("1", "confirm"), ("2", "decline"), ("3", "callback_requested"), ("9", "opt_out")):
        s, events = vm(detect_voicemail=False, keypad_hint=True)
        s.start()
        out = s.on_dtmf(digit)
        assert isinstance(out[-1], Hangup) and s.decision.intent.value == intent and events[0].dtmf == digit


def test_keypad_works_even_while_the_agent_is_still_listening_for_a_person_or_machine():
    s, events = vm(keypad_hint=True)
    s.start()
    out = s.on_dtmf("1")                                               # pressed during the pickup window
    assert isinstance(out[-1], Hangup) and s.decision.intent.value == "confirm" and not s._probing


def test_silence_offers_the_keypad_and_then_a_key_press_answers():
    s, events = vm(detect_voicemail=False, keypad_hint=True)
    s.start()
    out = s.on_audio(quiet(8000))                                      # nobody speaks
    assert [type(a) for a in out] == [Say] and "press 1 to confirm" in out[0].text and "9 to stop" in out[0].text
    out = s.on_dtmf("2")
    assert s.decision.intent.value == "decline" and isinstance(out[-1], Hangup)


def test_without_keypad_hint_the_original_prompts_are_unchanged():
    s, _ = make([])
    s.start()
    out = s.on_audio(quiet(8000))
    assert out[0].text == "Sorry, I did not catch that. Will you be attending the event?"


def test_unclear_answer_or_unknown_key_re_asks_once_with_the_keys():
    s, _ = vm(["hmm not sure"], detect_voicemail=False, keypad_hint=True)
    s.start()
    out = speak(s)
    assert [type(a) for a in out] == [Say] and "press 1 for yes and 2 for no" in out[0].text
    s2, _ = vm(detect_voicemail=False, keypad_hint=True)
    s2.start()
    out = s2.on_dtmf("7")                                              # not an option
    assert [type(a) for a in out] == [Clear, Say] and "press 1 for yes" in out[1].text and not s2.done


def test_key_4_reads_out_what_we_know_then_asks_again_with_the_keys():
    s, events = vm(detect_voicemail=False, keypad_hint=True, conversational=True)
    s.start()
    out = s.on_dtmf("4")
    text = out[-1].text
    assert "May 5th at 10 AM" in text and "Main Hall" in text and "press 1 for yes" in text and not s.done
    assert isinstance(s.on_dtmf("1")[-1], Hangup) and s.decision.intent.value == "confirm"
    # nothing known: falls back to the normal "a team member will follow up"
    s2, _ = make([], conversational=True, keypad_hint=True)
    s2.start()
    assert isinstance(s2.on_dtmf("4")[-1], Hangup) and s2.decision.intent.value == "information_requested"


def test_builtin_greeting_offers_the_keypad_only_when_asked():
    c = CampaignInfo(name="TechFest", organiser="Acme", language="hi")
    assert KEYPAD_OPTIONS["hi"] not in build_greeting(c)
    c.keypad = True
    assert build_greeting(c).endswith(KEYPAD_OPTIONS["hi"])
    c.greeting_override = "Custom script. Will you come?"
    assert build_greeting(c) == "Custom script. Will you come?"        # organiser wording is never altered here
    assert mentions_keypad("Press 1 to confirm") and mentions_keypad("1 दबाएँ") and not mentions_keypad("Will you come?")
