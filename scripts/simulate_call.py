"""Fake Exotel: drives /live/exotel like a phone call, so the whole pipeline can be tested with no phone.

    python -m scripts.simulate_call "Yes, I will come" [ws_url, default ws://127.0.0.1:8000/live/exotel]

Plays the greeting into the void, then 'speaks' the given sentence (synthesised with ElevenLabs, so it uses a few
characters of quota and exercises real speech-to-text), waits for the goodbye, and reports what came back.
"""
import base64
import json
import os
import sys

from dotenv import load_dotenv
from websockets.sync.client import connect

from member3.integrations.elevenlabs.client import ElevenLabsClient

load_dotenv()
say = sys.argv[1] if len(sys.argv) > 1 else "Yes, I will come"
url = sys.argv[2] if len(sys.argv) > 2 else "ws://127.0.0.1:8000/live/exotel"
if url.rstrip("/").endswith("/live/exotel"):
    url = url.rstrip("/") + "/" + os.getenv("EXOTEL_WEBHOOK_TOKEN", "")      # secret rides in the path
RATE, FRAME = 8000, 640                                  # 40 ms frames
quiet = lambda ms: bytes(int(RATE * ms / 1000) * 2)


def media(pcm):
    return json.dumps({"event": "media", "stream_sid": "SIM", "media": {"payload": base64.b64encode(pcm).decode()}})


def drain(ws, wait):
    got = 0
    try:
        while True:
            m = json.loads(ws.recv(timeout=wait))
            if m["event"] == "media":
                got += len(base64.b64decode(m["media"]["payload"]))
            else:
                print("  server event:", m["event"])
    except TimeoutError:
        pass
    except Exception as exc:                              # server closed the socket = hung up
        print("  connection closed by server:", type(exc).__name__)
        return got, True
    return got, False


speech = ElevenLabsClient(os.environ["ELEVENLABS_API_KEY"], voice_id=os.environ["ELEVENLABS_VOICE_ID"]).speak_pcm(say, RATE)
with connect(url, max_size=None) as ws:
    ws.send(json.dumps({"event": "connected"}))
    ws.send(json.dumps({"event": "start", "stream_sid": "SIM", "start": {"stream_sid": "SIM", "call_sid": "SIM-1",
                        "media_format": {"encoding": "raw", "sample_rate": "8000"}, "custom_parameters": {}}}))
    greeting, _ = drain(ws, 4)
    print(f"greeting received: {greeting} bytes = {greeting / 16000:.1f} s of audio")
    for pcm in (quiet(int(greeting / 16) + 300), speech, quiet(1500)):    # wait out the greeting, speak, pause
        for i in range(0, len(pcm), FRAME):
            ws.send(media(pcm[i:i + FRAME]))
    reply, closed = drain(ws, 25)
    print(f"reply received: {reply} bytes = {reply / 16000:.1f} s of audio; hung up by server: {closed}")
