"""WebSocket transport for Exotel's Voicebot applet (bidirectional stream).

Protocol per Exotel's "Working with the Stream and Voicebot Applet" article (read from the docs, NOT yet
exercised against a live account from this codebase):
  in : connected | start{stream_sid, call_sid, media_format, custom_parameters} | media{payload b64 PCM}
       | dtmf{digit} | mark | stop
  out: media{payload b64 PCM} | clear
  audio = 16-bit little-endian mono PCM; chunks sent to Exotel must be multiples of 320 bytes (3.2k-100k);
  there is no hang-up message: closing the socket ends the stream and the flow moves to the next applet.

Secret: put it in the PATH, wss://<host>/live/exotel/<EXOTEL_WEBHOOK_TOKEN>. The "Connect Voice AI" API was observed to
drop a ?token= query string (Exotel connected with a bare /live/exotel), so the query form is only a fallback.
The call is matched to a campaign attempt by `call_sid`, which is the Sid `ExotelProvider.initiate_call` returned.
"""
import asyncio
import base64
import hashlib
import hmac
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from .session import Clear, Hangup, LiveSession, Say

log = logging.getLogger("member3.live")


def fingerprint(secret: str) -> str:
    """Length + 6 hex of SHA-256: lets two sides confirm they hold the same secret without revealing it."""
    return f"len={len(secret)} sha={hashlib.sha256(secret.encode()).hexdigest()[:6]}"     # event names and counts only; never audio or transcripts


@dataclass
class StartInfo:
    call_sid: str
    stream_sid: str
    sample_rate: int = 8000
    from_number: str = ""
    to_number: str = ""
    custom_parameters: dict = field(default_factory=dict)


# Returns the session for this call, or None to refuse it (unknown call_sid). May block (DB lookup).
SessionFactory = Callable[[StartInfo], LiveSession | None]


def _start_info(msg: dict) -> StartInfo:
    s = msg.get("start") or {}
    try:
        rate = int((s.get("media_format") or {}).get("sample_rate") or 8000)
    except (TypeError, ValueError):
        rate = 8000
    return StartInfo(call_sid=s.get("call_sid", ""), stream_sid=s.get("stream_sid") or msg.get("stream_sid", ""),
                     sample_rate=rate, from_number=s.get("from", ""), to_number=s.get("to", ""),
                     custom_parameters=s.get("custom_parameters") or {})


def create_router(*, session_factory: SessionFactory, token: str = "", chunk_bytes: int = 3200,
                  close_margin_ms: int = 500, lead_ms: int = 400) -> APIRouter:
    """Outbound audio is paced to real time with a `lead_ms` head start. A live test showed Exotel cancelling the
    stream (`stop`, reason "canceled or call ended") about 80 ms after a 190 KB all-at-once burst."""
    assert chunk_bytes % 320 == 0
    router = APIRouter()

    @router.websocket("/live/exotel")
    @router.websocket("/live/exotel/{secret}")
    async def exotel_stream(ws: WebSocket, secret: str = ""):
        supplied = secret or ws.query_params.get("token", "")
        if token and not hmac.compare_digest(supplied.encode(), token.encode()):
            log.warning("live ws refused: bad or missing secret (received %s, expected %s)", fingerprint(supplied),
                        fingerprint(token))
            await ws.close(code=1008)
            return
        await ws.accept()
        log.info("live ws accepted")
        counts: dict[str, int] = {}
        session: LiveSession | None = None
        stream_sid, rate = "", 8000
        closer: asyncio.Task | None = None
        out_q: asyncio.Queue = asyncio.Queue()
        play_end = 0.0                       # monotonic time at which audio already sent will finish playing
        ts_ms, generation = 0, 0
        sender_task: asyncio.Task | None = None

        async def sender() -> None:
            nonlocal play_end, ts_ms
            while True:
                part, gen = await out_q.get()
                try:
                    now = time.monotonic()
                    play_end = max(play_end, now)
                    wait = play_end - now - lead_ms / 1000
                    if wait > 0:
                        await asyncio.sleep(wait)
                    if gen != generation:            # cleared while waiting (caller interrupted)
                        continue
                    # Minimal message only: a live probe showed Exotel cancels the stream within 100 ms of a media
                    # message that also carries sequence_number / chunk / timestamp (the docs' example format).
                    await ws.send_json({"event": "media", "stream_sid": stream_sid,
                                        "media": {"payload": base64.b64encode(part).decode()}})
                    dur = len(part) / (2 * rate)
                    play_end += dur
                    ts_ms += int(dur * 1000)
                except Exception as exc:             # socket gone; the receive loop will notice too
                    log.info("sender stopped: %s", type(exc).__name__)
                    return
                finally:
                    out_q.task_done()

        def enqueue_audio(pcm: bytes) -> None:
            for i in range(0, len(pcm), chunk_bytes):
                part = pcm[i:i + chunk_bytes]
                part += bytes(-len(part) % 320)      # last chunk must also be a multiple of 320
                out_q.put_nowait((part, generation))

        async def close_later() -> None:
            await out_q.join()
            await asyncio.sleep(max(0.0, play_end - time.monotonic()) + close_margin_ms / 1000)
            await ws.close()                         # closing the socket is how the bot ends the call

        async def run(actions) -> None:
            nonlocal closer, generation, play_end
            for a in actions:
                if isinstance(a, Say):
                    enqueue_audio(a.pcm)
                elif isinstance(a, Clear):
                    generation += 1                  # drop everything not yet sent
                    while not out_q.empty():
                        out_q.get_nowait()
                        out_q.task_done()
                    play_end = time.monotonic()
                    await ws.send_json({"event": "clear", "stream_sid": stream_sid})
                elif isinstance(a, Hangup) and closer is None:
                    closer = asyncio.create_task(close_later())

        try:
            while True:
                msg = await ws.receive_json()
                event = msg.get("event")
                counts[event] = counts.get(event, 0) + 1
                if event == "start":
                    info = _start_info(msg)
                    stream_sid, rate = info.stream_sid, info.sample_rate
                    log.info("start: call_sid=%s rate=%s keys=%s", info.call_sid, info.sample_rate, sorted(msg.get("start") or {}))
                    session = await asyncio.to_thread(session_factory, info)
                    if session is None:
                        log.warning("no session for call_sid=%s; closing", info.call_sid)
                        await ws.close(code=1008)
                        return
                    sender_task = asyncio.create_task(sender())
                    await run(await asyncio.to_thread(session.start))
                    log.info("greeting queued (%d chunks)", out_q.qsize())
                elif session is None:
                    continue
                elif event == "media":
                    pcm = base64.b64decode((msg.get("media") or {}).get("payload", ""))
                    await run(await asyncio.to_thread(session.on_audio, pcm))
                elif event == "dtmf":
                    await run(await asyncio.to_thread(session.on_dtmf, str((msg.get("dtmf") or {}).get("digit", ""))))
                elif event == "stop":
                    log.info("stop: %s", (msg.get("stop") or {}).get("reason"))
                    break
        except (WebSocketDisconnect, RuntimeError) as exc:
            log.info("ws ended: %s", type(exc).__name__)    # caller hung up, or we closed after the goodbye
        except Exception:
            log.exception("live session crashed")           # traceback only; no audio or text is logged
        finally:
            log.info("events received: %s", counts)
            if session is not None:
                session.on_stop()
            for task in (closer, sender_task):
                if task is not None:
                    task.cancel()
            try:
                await ws.close()                            # no-op if already closed; ensures a clean end otherwise
            except Exception:
                pass

    return router
