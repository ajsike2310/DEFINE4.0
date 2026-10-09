"""Diagnostic WebSocket for Exotel (DEV_EXPERIMENT=probe). Sends NO TTS; logs a timeline so we can tell what makes Exotel
cancel the stream:
  t=0        stream starts; we send nothing  -> if `stop` arrives at ~2.5 s anyway, it is not our audio (timer/account)
  t=+delay1  one 100 ms silence chunk, MINIMAL message  {event, stream_sid, media:{payload}}
  t=+delay2  one 100 ms silence chunk, DOCS-format message {event, sequence_number, stream_sid, media:{chunk,timestamp,payload}}
  then wait, then close.  A `stop` right after a send names the message format Exotel dislikes.
Logs event names, timings and non-personal start fields only.
"""
import asyncio
import base64
import hmac
import logging
import time

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

log = logging.getLogger("member3.probe")
SILENCE_100MS = base64.b64encode(bytes(3200)).decode()      # 100 ms of 8 kHz 16-bit silence


def create_probe_router(token: str, delays: tuple[float, float, float] = (6.0, 3.0, 8.0)) -> APIRouter:
    router = APIRouter()

    @router.websocket("/live/exotel/{secret}")
    async def probe(ws: WebSocket, secret: str):
        if token and not hmac.compare_digest(secret.encode(), token.encode()):
            await ws.close(code=1008)
            return
        await ws.accept()
        t0 = time.monotonic()
        now = lambda: f"t={time.monotonic() - t0:5.2f}s"
        seen: dict[str, int] = {}
        stream_sid = ""
        script: asyncio.Task | None = None

        async def send(label: str, msg: dict) -> None:
            await ws.send_json(msg)
            log.info("%s SENT %s", now(), label)

        async def run_script() -> None:
            d1, d2, d3 = delays
            await asyncio.sleep(d1)
            await send("minimal media", {"event": "media", "stream_sid": stream_sid, "media": {"payload": SILENCE_100MS}})
            await asyncio.sleep(d2)
            await send("docs-format media", {"event": "media", "sequence_number": 1, "stream_sid": stream_sid,
                                             "media": {"chunk": 1, "timestamp": "0", "payload": SILENCE_100MS}})
            await asyncio.sleep(d3)
            log.info("%s closing socket (script finished)", now())
            await ws.close()

        try:
            while True:
                msg = await ws.receive_json()
                ev = msg.get("event")
                seen[ev] = seen.get(ev, 0) + 1
                if ev == "start":
                    s = msg.get("start") or {}
                    stream_sid = s.get("stream_sid") or msg.get("stream_sid", "")
                    log.info("%s START media_format=%s custom_parameters=%s top_keys=%s", now(), s.get("media_format"),
                             s.get("custom_parameters"), sorted(msg))
                    script = asyncio.create_task(run_script())
                elif ev == "stop":
                    log.info("%s STOP %s", now(), msg.get("stop"))
                    break
                elif ev != "media" or seen[ev] == 1:
                    log.info("%s event=%s %s", now(), ev, {k: v for k, v in msg.items() if k != "media"} if ev != "media" else "(first media)")
        except (WebSocketDisconnect, RuntimeError) as exc:
            log.info("%s ws ended: %s", now(), type(exc).__name__)
        finally:
            if script:
                script.cancel()
            log.info("%s events received: %s", now(), seen)

    return router
