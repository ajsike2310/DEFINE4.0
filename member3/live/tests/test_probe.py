from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from member3.live.probe import create_probe_router


def test_probe_sends_both_formats_then_closes():
    app = FastAPI()
    app.include_router(create_probe_router("s", delays=(0.05, 0.05, 0.05)))
    with TestClient(app).websocket_connect("/live/exotel/s") as ws:
        ws.send_json({"event": "start", "stream_sid": "S", "start": {"stream_sid": "S", "media_format": {"sample_rate": "8000"}}})
        a, b = ws.receive_json(), ws.receive_json()
        assert set(a) == {"event", "stream_sid", "media"} and b["sequence_number"] == 1
        try:
            ws.receive_json()
            raise AssertionError("expected close")
        except WebSocketDisconnect:
            pass
