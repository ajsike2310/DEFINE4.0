import base64
import json
import logging
from datetime import date, time

import httpx
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from member3.live.campaign import (CallContext, CampaignInfo, InMemoryCallRegistry, build_greeting, spoken_date,
                                   spoken_time)
from member3.live.config import LiveSettings
from member3.live.logging_utils import RedactSecretPath, redact
from member3.live.results import HttpResultSink, build_result
from member3.live.service import LiveService
from member3.live.tts_cache import TtsCache
from member3.intelligence.pipeline import ResponseInput, process_response

RATE = 8000
CAMPAIGN = CampaignInfo(name="TechFest", venue="the main auditorium", event_date=date(2026, 11, 15),
                        event_time=time(10, 0), organiser="Cadence College")


def ctx(sid="C1", name="Asha Nair"):
    return CallContext(provider_call_id=sid, attempt_id=7, participant_id="p_1", campaign_id="c_9",
                       campaign=CAMPAIGN, participant_name=name)


def tone(ms):
    t = np.arange(int(RATE * ms / 1000))
    return (4000 * np.sin(2 * np.pi * 300 * t / RATE)).astype("<i2").tobytes()


def quiet(ms):
    return bytes(int(RATE * ms / 1000) * 2)


# ---- campaign -----------------------------------------------------------------------------------
def test_spoken_formats():
    assert spoken_date(date(2026, 11, 15)) == "November 15th" and spoken_date(date(2026, 3, 1)) == "March 1st"
    assert spoken_date(date(2026, 3, 22)) == "March 22nd" and spoken_date(date(2026, 3, 11)) == "March 11th"
    assert spoken_time(time(10, 0)) == "10 AM" and spoken_time(time(14, 30)) == "2:30 PM"
    assert spoken_time(time(0, 5)) == "12:05 AM" and spoken_time("evening") == "evening"


def test_greeting_template_and_override():
    g = build_greeting(CAMPAIGN, "Asha Nair")
    assert g == ("Hello Asha! This is an automated call from Cadence College about the TechFest event on "
                 "November 15th at 10 AM. The event will take place at the main auditorium. Will you be attending?")
    assert build_greeting(CampaignInfo(name="Quiz")).startswith("Hello! This is an automated call about the Quiz event.")
    assert build_greeting(CampaignInfo(name="x", greeting_override="  Custom script  ")) == "Custom script"


def test_info_answers_come_only_from_campaign_data():
    a = CAMPAIGN.info_answers()
    assert a["venue"] == "The event will take place at the main auditorium"
    assert a["schedule"] == "The event is on November 15th at 10 AM"
    assert CampaignInfo(name="x").info_answers() == {}


def test_registry_waits_for_late_registration_and_evicts_oldest():
    import threading
    import time as t
    reg = InMemoryCallRegistry(max_items=2)
    threading.Timer(0.15, lambda: reg.register(ctx("late"))).start()
    assert reg.get("late", wait_s=2.0) is not None
    assert reg.get("never", wait_s=0.1) is None
    reg.register(ctx("a")); reg.register(ctx("b"))
    assert reg.get("late") is None and reg.get("b") is not None


# ---- results ------------------------------------------------------------------------------------
def test_build_result_for_answer_and_for_hangup():
    r = build_result(ctx(), process_response(ResponseInput(text="Yes, I will come")), call_outcome="completed")
    assert (r.attendance, r.call_outcome, r.participant_id, r.campaign_id) == ("confirmed", "completed", "p_1", "c_9")
    assert r.event_id == "C1:result" and not r.needs_review
    u = build_result(ctx(), process_response(ResponseInput(text="maybe")), call_outcome="completed")
    assert u.attendance == "unclear" and u.needs_review
    h = build_result(ctx(), None, call_outcome="hung_up")
    assert h.attendance == "no_response" and h.needs_review and h.intent is None


def _result():
    return build_result(ctx(), process_response(ResponseInput(dtmf="1")), call_outcome="completed")


def test_http_sink_retries_then_succeeds_with_idempotency_key():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(503 if len(calls) < 3 else 200)
    sink = HttpResultSink("http://backend/r", "tok", client=httpx.Client(transport=httpx.MockTransport(handler)),
                          sleep=lambda s: None, dead_letter_path=None)
    sink(_result())
    assert len(calls) == 3 and calls[0].headers["Idempotency-Key"] == "C1:result"
    assert calls[0].headers["Authorization"] == "Bearer tok" and json.loads(calls[0].content)["attendance"] == "confirmed"


def test_http_sink_dead_letters_when_backend_is_down_but_not_on_success(tmp_path):
    dl = tmp_path / "x" / "unsent.jsonl"
    down = HttpResultSink("http://b/r", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
                          sleep=lambda s: None, dead_letter_path=str(dl))
    down(_result())
    assert json.loads(dl.read_text().splitlines()[0])["provider_call_id"] == "C1"
    bad_req = HttpResultSink("http://b/r", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(422))),
                             sleep=lambda s: None, dead_letter_path=str(dl))
    bad_req(_result())
    assert len(dl.read_text().splitlines()) == 2        # 4xx is not retried but is still kept


# ---- cache, config, logging -----------------------------------------------------------------------
def test_tts_cache_hits_and_evicts():
    n = []
    c = TtsCache(lambda text, rate: n.append(text) or text.encode(), max_items=2)
    c.speak("a", 8000); c.speak("a", 8000); c.speak("a", 16000)
    assert n == ["a", "a"]                                # rate is part of the key
    c.speak("b", 8000)
    c.speak("a", 8000)
    assert n == ["a", "a", "b", "a"]                      # ("a",8000) was evicted
    c.prewarm(["z"], 8000).join(2)
    assert "z" in n


def test_settings_from_env():
    s = LiveSettings.from_env({"EXOTEL_WEBHOOK_TOKEN": "t", "LIVE_BARGE_IN": "yes", "LIVE_NO_SPEECH_TIMEOUT_MS": "5000"})
    assert s.webhook_token == "t" and s.barge_in and s.no_speech_timeout_ms == 5000 and not s.log_transcript


def test_secret_path_is_redacted_from_logs():
    assert redact('WebSocket /live/exotel/abc-DEF_123 [accepted]') == 'WebSocket /live/exotel/<redacted> [accepted]'
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s"', ("1.2.3.4:0", "WebSocket", "/live/exotel/SECRETVALUE"), None)
    RedactSecretPath().filter(rec)
    assert "SECRETVALUE" not in rec.getMessage()


# ---- full service over the websocket -----------------------------------------------------------------
def build(stt_reply="Yes, I will come"):
    results, events = [], []
    svc = LiveService(LiveSettings(webhook_token="s", register_wait_s=0.3), results.append,
                      tts=lambda text, rate: quiet(300), stt=lambda wav: stt_reply, on_event=events.append)
    app = FastAPI()
    app.include_router(svc.router)
    return svc, TestClient(app), results, events


def start(sid):
    return {"event": "start", "stream_sid": "S", "start": {"stream_sid": "S", "call_sid": sid,
            "media_format": {"encoding": "base64", "sample_rate": "8000"}}}


def media(pcm):
    return {"event": "media", "stream_sid": "S", "media": {"payload": base64.b64encode(pcm).decode()}}


def drain(ws):
    try:
        while True:
            ws.receive_json()
    except WebSocketDisconnect:
        pass


def test_service_delivers_a_confirmed_result_with_participant_and_campaign():
    svc, client, results, events = build()
    svc.register_call(ctx("C1"))
    with client.websocket_connect("/live/exotel/s") as ws:
        ws.send_json(start("C1"))
        ws.receive_json()
        for pcm in (quiet(500), tone(400), quiet(900)):
            ws.send_json(media(pcm))
        drain(ws)
    assert len(results) == 1
    r = results[0]
    assert (r.attendance, r.call_outcome, r.participant_id, r.campaign_id, r.attempt_id) == ("confirmed", "completed", "p_1", "c_9", 7)
    assert len(events) == 1 and events[0].text == "Yes, I will come"      # legacy ProviderEvent path still available


def test_unregistered_call_is_refused_and_nothing_is_delivered():
    svc, client, results, _ = build()
    with client.websocket_connect("/live/exotel/s") as ws:
        ws.send_json(start("UNKNOWN"))
        drain(ws)
    assert results == []


def test_hangup_before_answer_reports_no_response():
    svc, client, results, _ = build()
    svc.register_call(ctx("C2"))
    with client.websocket_connect("/live/exotel/s") as ws:
        ws.send_json(start("C2"))
        ws.receive_json()
        ws.send_json({"event": "stop", "stream_sid": "S", "stop": {"call_sid": "C2", "reason": "callended"}})
    assert [(r.attendance, r.call_outcome, r.needs_review) for r in results] == [("no_response", "hung_up", True)]


def test_a_failing_sink_does_not_break_the_call():
    def boom(r):
        raise RuntimeError("backend bug")
    svc = LiveService(LiveSettings(webhook_token="s"), boom, tts=lambda t, r: quiet(300), stt=lambda w: "yes")
    svc.register_call(ctx("C3"))
    app = FastAPI(); app.include_router(svc.router)
    with TestClient(app).websocket_connect("/live/exotel/s") as ws:
        ws.send_json(start("C3"))
        ws.receive_json()
        for pcm in (quiet(500), tone(400), quiet(900)):
            ws.send_json(media(pcm))
        drain(ws)                                             # closes normally instead of crashing


def test_tts_failure_ends_the_call_and_flags_review():
    def bad_tts(text, rate):
        raise RuntimeError("elevenlabs down")
    results = []
    svc = LiveService(LiveSettings(webhook_token="s"), results.append, tts=bad_tts, stt=lambda w: "yes")
    svc.register_call(ctx("C4"))
    app = FastAPI(); app.include_router(svc.router)
    with TestClient(app).websocket_connect("/live/exotel/s") as ws:
        ws.send_json(start("C4"))
        drain(ws)
    assert [(r.attendance, r.needs_review) for r in results] == [("no_response", True)]


# ---- Hindi / Tamil conversations (fake speech services; wording is NOT native-reviewed) ---------------------
def _talk(campaign, heard_text, sid, trailing_silence_ms=0):
    """Run one call; returns (spoken lines in order, results)."""
    said, results = [], []
    svc = LiveService(LiveSettings(webhook_token="s", register_wait_s=0.3), results.append,
                      tts=lambda text, rate: said.append(text) or quiet(200), stt=lambda wav: heard_text)
    svc.register_call(CallContext(provider_call_id=sid, attempt_id=1, participant_id="p", campaign_id="c",
                                  campaign=campaign, participant_name="Asha"))
    app = FastAPI(); app.include_router(svc.router)
    with TestClient(app).websocket_connect("/live/exotel/s") as ws:
        ws.send_json(start(sid))
        ws.receive_json()
        for pcm in (quiet(300), tone(400), quiet(900)):
            ws.send_json(media(pcm))
        try:
            for _ in range(trailing_silence_ms // 500):        # real audio is a steady stream of small frames
                ws.send_json(media(quiet(500)))
        except Exception:                                      # server already said goodbye and hung up
            pass
        drain(ws)
    return said, results


def test_hindi_campaign_greets_in_hindi_and_hindi_reply_gets_hindi_goodbye():
    hi = CampaignInfo(name="TechFest", venue="मुख्य सभागार", event_date=date(2026, 11, 15), event_time=time(10, 0),
                      organiser="Cadence College", language="hi")
    said, results = _talk(hi, "हाँ, मैं आऊँगा", "H1")
    assert said[0].startswith("नमस्ते Asha!") and "15 नवंबर को सुबह 10 बजे" in said[0]
    assert said[-1] == "धन्यवाद। हमने नोट कर लिया है कि आप शामिल होंगे। अलविदा।"
    assert results[0].attendance == "confirmed" and results[0].language == "hi"


def test_tamil_decline_gets_tamil_goodbye():
    ta = CampaignInfo(name="TechFest", venue="முதன்மை அரங்கம்", event_date=date(2026, 11, 15), event_time=time(10, 0), language="ta")
    said, results = _talk(ta, "இல்லை, நான் வரமாட்டேன்", "T1")
    assert said[0].startswith("வணக்கம் Asha!") and said[-1] == "சரி, தெரிவித்ததற்கு நன்றி. வணக்கம்."
    assert results[0].attendance == "declined" and results[0].language == "ta"


def test_where_question_is_answered_in_the_language_asked_from_campaign_data():
    camp = CampaignInfo(name="TechFest", venue="Main Hall", event_date=date(2026, 11, 15), event_time=time(10, 0))
    said, _ = _talk(camp, "कार्यक्रम कहाँ है?", "H2")                 # English campaign, Hindi question
    assert said[-1] == "कार्यक्रम का स्थान Main Hall है। अलविदा।"
    said, _ = _talk(camp, "எங்கே நடக்கிறது", "T2")
    assert said[-1] == "நிகழ்ச்சி நடைபெறும் இடம் Main Hall. வணக்கம்."
    said, _ = _talk(camp, "Where is the venue?", "E2")
    assert said[-1] == "The event will take place at Main Hall. Goodbye."


def test_unclear_hindi_gets_hindi_clarification_first():
    camp = CampaignInfo(name="TechFest", language="en")
    said, _ = _talk(camp, "शायद", "H3", trailing_silence_ms=17000)    # clarification, then silence ends the call
    assert "कृपया हाँ या ना कहें" in said[1]                           # clarification in the language the caller used


def test_elevenlabs_client_retries_a_transient_network_error_once():
    from member3.integrations.elevenlabs.client import ElevenLabsClient, ElevenLabsError
    calls = []

    def flaky(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("reset", request=req)
        return httpx.Response(200, content=b"\x00\x01")
    c = ElevenLabsClient("k", voice_id="v", client=httpx.Client(transport=httpx.MockTransport(flaky)))
    assert c.speak_pcm("hi") == b"\x00\x01" and len(calls) == 2

    def always(req):
        raise httpx.ConnectError("down", request=req)
    bad = ElevenLabsClient("k", voice_id="v", client=httpx.Client(transport=httpx.MockTransport(always)))
    try:
        bad.speak_pcm("hi")
        raise AssertionError("should fail")
    except ElevenLabsError as exc:
        assert "unreachable" in str(exc)
