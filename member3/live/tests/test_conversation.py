"""Conversational mode: language switches and known questions keep the call going; the default mode is unchanged."""
import pytest

from member3.live.campaign import CampaignInfo
from member3.live.dialogue import detect_language_switch, question_topic
from member3.live.session import Hangup, Say
from member3.live.tests.test_live import make, speak

INFO = {"en": {"venue": "The event is at Main Hall", "schedule": "The event is on May 5th at 10 AM",
               "organiser": "This event is organised by Acme College", "about": "A one day hands-on coding event"},
        "hi": {"venue": "कार्यक्रम का स्थान मुख्य हॉल है"}}


def conv(replies, **kw):
    return make(replies, conversational=True, info_answers=lambda lang: INFO.get(lang, INFO["en"]),
                greeting_for=lambda lang: {"hi": "नमस्ते! क्या आप शामिल होंगे?", "ta": "வணக்கம்!"}.get(lang), **kw)


@pytest.mark.parametrize("text,current,expected", [
    ("Can you speak in Hindi please", "en", "hi"), ("Hindi please", "en", "hi"), ("हिंदी में बोलिए", "en", "hi"),
    ("தமிழில் பேசுங்கள்", "en", "ta"), ("english please", "hi", "en"), ("Please talk in Tamil", "hi", "ta"),
    ("Hindi please", "hi", None),                                      # already in it
    ("Yes I will come, thank you very much for calling today", "en", None),
    ("I am coming but my friend speaks Tamil and will not be able to join us at all", "en", None)])
def test_language_switch_detection(text, current, expected):
    assert detect_language_switch(text, current) == expected


@pytest.mark.parametrize("text,topic", [
    ("Who is organising this?", "organiser"), ("what is this about", "about"), ("Where is it?", "venue"),
    ("What time does it start", "schedule"), ("I like pizza", None)])
def test_question_topics(text, topic):
    assert question_topic(text) == topic


def test_language_switch_keeps_call_open_and_closes_in_new_language():
    s, events = conv(["Can you speak in Hindi please", "yes I will come"])
    s.start()
    out = speak(s)
    assert [type(a) for a in out] == [Say] and "हिंदी" in out[0].text and "क्या आप शामिल होंगे" in out[0].text
    assert not s.done and events == []
    out = speak(s)                                                     # the English "yes" still closes in the chosen language
    assert isinstance(out[1], Hangup) and "धन्यवाद" in out[0].text
    assert len(events) == 1 and s.decision.intent.value == "confirm"


def test_known_question_is_answered_then_the_question_is_asked_again():
    s, events = conv(["What time does it start?", "Where is it?", "Who is organising this?", "yes"])
    s.start()
    out = speak(s)
    assert [type(a) for a in out] == [Say] and out[0].text == "The event is on May 5th at 10 AM. Will you be attending?"
    assert "Main Hall" in speak(s)[0].text and "Acme College" in speak(s)[0].text
    final = speak(s)
    assert isinstance(final[1], Hangup) and s.decision.intent.value == "confirm" and len(events) == 1


def test_unknown_question_goes_through_the_normal_clarify_then_human_hand_over():
    s, events = conv(["Is there parking and food?", "hmm not sure"])
    s.start()
    out = speak(s)
    assert [type(a) for a in out] == [Say] and "I want to be sure" in out[0].text            # existing one-time clarification
    out = speak(s)
    assert isinstance(out[-1], Hangup) and "team member" in out[0].text and s.decision.needs_review


def test_questions_are_capped_so_a_call_cannot_loop_forever():
    s, _ = conv(["Where is it?"] * 4)
    s.start()
    for _ in range(3):
        out = speak(s)
        assert [type(a) for a in out] == [Say] and out[0].text.endswith("Will you be attending?")
    last = speak(s)                                                    # the 4th question ends the call normally
    assert isinstance(last[-1], Hangup) and s.done


def test_a_yes_with_a_question_is_answered_and_the_question_asked_again():
    s, _ = conv(["yes I will come, where is it?", "yes"])
    s.start()
    out = speak(s)
    assert "Main Hall" in out[0].text and not s.done
    assert isinstance(speak(s)[-1], Hangup) and s.decision.intent.value == "confirm"


def test_default_mode_is_unchanged():
    s, events = make(["What time does it start?"], info_answers={"schedule": "10 AM"})
    s.start()
    assert speak(s)[0].text == "10 AM. Goodbye."                      # answers once and ends, as before
    s2, _ = make(["Can you speak in Hindi please", "x"])
    s2.start()
    out = speak(s2)
    assert "हिंदी" not in out[0].text and "want to be sure" in out[0].text   # no switching unless asked for


def test_campaign_info_answers_include_organiser_and_about():
    c = CampaignInfo(name="TechFest", organiser="Acme", description="A coding day.")
    a = c.info_answers("en")
    assert a["organiser"].endswith("Acme") and a["about"] == "A coding day."
    assert CampaignInfo(name="x").info_answers() == {}
