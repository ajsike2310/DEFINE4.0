import base64

import httpx
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from member3.integrations.elevenlabs.client import ElevenLabsClient
from member3.live.exotel_ws import create_router
from member3.live.session import LiveSession

RATE = 8000


def tone(ms):
    t = np.arange(int(RATE * ms / 1000))
    return (4000 * np.sin(2 * np.pi * 300 * t / RATE)).astype("<i2").tobytes()


def quiet(ms):
    return bytes(int(RATE * ms / 1000) * 2)


def media(pcm):
    return {"event": "media", "stream_sid": "S", "media": {"payload": base64.b64encode(pcm).decode()}}


def build(token="", reply="Yes, I will come"):
    events, seen = [], []

    def factory(info):
        seen.append(info)
        if info.call_sid == "unknown":
            return None
        return LiveSession(provider_call_id=info.call_sid, greeting="Will you attend?", tts=lambda t: quiet(500),
                           stt=lambda wav: reply, emit=events.append)

    app = FastAPI()
    app.include_router(create_router(session_factory=factory, token=token, close_margin_ms=50))
    return TestClient(app), events, seen


def start(call_sid="C1"):
    return {"event": "start", "stream_sid": "S", "start": {"stream_sid": "S", "call_sid": call_sid,
            "media_format": {"encoding": "raw", "sample_rate": "8000"}, "custom_parameters": {}}}


def drain(ws):
    frames = []
    try:
        while True:
            frames.append(ws.receive_json())
    except WebSocketDisconnect:
        return frames


def test_full_call_over_websocket():
    client, events, seen = build()
    with client.websocket_connect("/live/exotel") as ws:
        ws.send_json({"event": "connected"})
        ws.send_json(start())
        greeting = [ws.receive_json() for _ in range(3)]           # 8000 B -> 3200 + 3200 + 1600
        sizes = [len(base64.b64decode(m["media"]["payload"])) for m in greeting]
        assert sizes == [3200, 3200, 1600] and all(s % 320 == 0 for s in sizes)
        assert greeting[0]["stream_sid"] == "S" and set(greeting[0]) == {"event", "stream_sid", "media"}
        assert set(greeting[0]["media"]) == {"payload"}      # extra fields make Exotel cancel the stream
        for pcm in (quiet(600), tone(400), quiet(900)):
            ws.send_json(media(pcm))
        closing = drain(ws)                                        # goodbye audio, then the server closes
        assert closing and all(m["event"] == "media" for m in closing)
    assert seen[0].call_sid == "C1" and seen[0].sample_rate == 8000
    assert len(events) == 1 and events[0].text == "Yes, I will come" and events[0].provider_call_id == "C1"


def test_dtmf_over_websocket():
    client, events, _ = build()
    with client.websocket_connect("/live/exotel") as ws:
        ws.send_json(start())
        [ws.receive_json() for _ in range(3)]
        ws.send_json({"event": "dtmf", "stream_sid": "S", "dtmf": {"digit": "2", "duration": "100"}})
        frames = drain(ws)
        assert frames[0]["event"] == "clear"
    assert events[0].dtmf == "2"


def test_hangup_before_answer_emits_nothing():
    client, events, _ = build()
    with client.websocket_connect("/live/exotel") as ws:
        ws.send_json(start())
        [ws.receive_json() for _ in range(3)]
        ws.send_json({"event": "stop", "stream_sid": "S", "stop": {"call_sid": "C1", "reason": "callended"}})
    assert events == []


def test_rejects_bad_token_and_unknown_call():
    client, _, _ = build(token="secret")
    try:
        with client.websocket_connect("/live/exotel?token=wrong"):
            raise AssertionError("should be refused")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008
    client, _, _ = build(token="secret")
    with client.websocket_connect("/live/exotel?token=secret") as ws:
        ws.send_json(start("unknown"))
        assert drain(ws) == []


def test_speak_pcm_requests_pcm_format():
    seen = {}

    def handler(req):
        seen["q"] = dict(req.url.params)
        return httpx.Response(200, content=b"\x00\x01")
    c = ElevenLabsClient("k", voice_id="v", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert c.speak_pcm("hi", 8000) == b"\x00\x01" and seen["q"] == {"output_format": "pcm_8000"}


def test_secret_in_path_is_accepted_and_wrong_path_secret_refused():
    client, events, _ = build(token="secret")
    with client.websocket_connect("/live/exotel/secret") as ws:
        ws.send_json(start())
        assert ws.receive_json()["event"] == "media"
    try:
        with client.websocket_connect("/live/exotel/nope"):
            raise AssertionError("should be refused")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008
    try:
        with client.websocket_connect("/live/exotel"):          # what Exotel actually sent: no secret at all
            raise AssertionError("should be refused")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008
