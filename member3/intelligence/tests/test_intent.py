"""Intent tests. All phrases are SYNTHETIC examples written by the team, not real
call data; passing them says nothing about real-world accuracy."""
import pytest

from member3.intelligence.intent.taxonomy import Intent, NextAction
from member3.intelligence.pipeline import ResponseInput, process_response

from member3.intelligence.eval_cases import CASES


@pytest.mark.parametrize("cat,text,expected", CASES, ids=[f"{c}:{t[:20]}" for c, t, _ in CASES])
def test_text_cases(cat, text, expected):
    assert process_response(ResponseInput(text=text)).intent == expected


def test_ambiguity_never_confirms_and_needs_action():
    d = process_response(ResponseInput(text="Maybe. I'll see."))
    assert d.intent == Intent.UNCLEAR and d.next_action == NextAction.CLARIFY and d.needs_review


def test_dtmf():
    assert process_response(ResponseInput(dtmf="1")).intent == Intent.CONFIRM
    assert process_response(ResponseInput(dtmf="9")).intent == Intent.OPT_OUT
    assert process_response(ResponseInput(dtmf="7")).intent == Intent.UNCLEAR


def test_audio_without_transcriber_requires_human():
    d = process_response(ResponseInput(audio_ref="rec://1"))
    assert d.intent == Intent.HUMAN and d.next_action == NextAction.HUMAN_REVIEW


def test_transcriber_failure_path_and_success_path():
    class Fake:
        def transcribe(self, ref, language_hint=None):
            return "yes"
    assert process_response(ResponseInput(audio_ref="x"), Fake()).intent == Intent.CONFIRM


def test_callback_time_only_when_explicit():
    assert process_response(ResponseInput(text="call me tomorrow")).requested_time is None
    d = process_response(ResponseInput(text="I'm busy, call me in 2 hours"))
    assert d.intent == Intent.CALLBACK and d.requested_time is not None


def test_callback_time_hint_is_note_only():
    d = process_response(ResponseInput(text="I'm busy. Call me after 5 PM."))
    assert d.intent == Intent.CALLBACK and d.time_hint == "after 5 PM"
    assert d.requested_time is None          # date unknown -> never auto-scheduled


def test_info_topics():
    assert process_response(ResponseInput(text="Where is the venue?")).info_topic == "venue"
    assert process_response(ResponseInput(text="What time does it start?")).info_topic == "schedule"
    assert process_response(ResponseInput(text="more info please")).info_topic is None


def test_optout_wins_over_other_signals():
    d = process_response(ResponseInput(text="yes but stop calling me"))
    assert d.intent == Intent.OPT_OUT and d.needs_review


import pytest as _pytest

from member3.intelligence.intent.taxonomy import Intent as _Intent
from member3.intelligence.pipeline import ResponseInput as _RI, process_response as _pr


@_pytest.mark.parametrize("text", [
    "Sorry, I am not going to come", "I'm not going to come", "I won't be able to make it",
    "I can't make it", "I will not be able to attend", "unfortunately I'm unable to come",
])
def test_common_english_declines(text):
    assert _pr(_RI(text=text)).intent == _Intent.DECLINE


@_pytest.mark.parametrize("text", ["Maybe I can make it", "I might not be able to come", "yes I can make it, thanks"])
def test_decline_phrases_do_not_override_hedges_or_confirms(text):
    assert _pr(_RI(text=text)).intent != _Intent.DECLINE


@_pytest.mark.parametrize("text,expected", [
    ("count me in", _Intent.CONFIRM), ("I can make it", _Intent.CONFIRM), ("definitely, I'll be coming", _Intent.CONFIRM),
    ("I can't wait to come!", _Intent.CONFIRM), ("I won't miss it", _Intent.CONFIRM), ("yes please", _Intent.CONFIRM),
    ("not this time", _Intent.DECLINE), ("I can't", _Intent.DECLINE), ("I don't think I can", _Intent.DECLINE),
    ("I'll try to come", _Intent.UNCLEAR), ("it depends", _Intent.UNCLEAR), ("can't promise", _Intent.UNCLEAR),
    ("call me after 5", _Intent.CALLBACK), ("I'm in a meeting", _Intent.CALLBACK), ("I'm driving", _Intent.CALLBACK),
    ("where is it", _Intent.INFO), ("what is the address", _Intent.INFO),
    ("take me off your list", _Intent.OPT_OUT), ("don't ever call me", _Intent.OPT_OUT),
])
def test_wider_english_phrasing(text, expected):
    assert _pr(_RI(text=text)).intent == expected
