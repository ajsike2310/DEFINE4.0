"""Standalone server for testing live calls on your own phone, before the backend is wired in.

    python -m scripts.run_live          (then expose port 8000 with ngrok; EXOTEL_STREAM_URL points at it)

Every call gets the demo campaign below (override with DEV_* in .env) and the result is only printed.
In the real system the backend embeds `LiveService` and calls `register_call(...)` after dialling.
"""
import logging
import os
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI

from . import logging_utils
from .campaign import CallContext, CampaignInfo
from .config import LiveSettings
from .exotel_ws import fingerprint
from .probe import create_probe_router
from .results import LogSink
from .service import LiveService

_shadowed = [k for k in ("EXOTEL_WEBHOOK_TOKEN", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID") if k in os.environ]
load_dotenv(override=True)           # dev server: .env is the source of truth, stale shell variables must not win
logging_utils.install()
settings = LiveSettings.from_env()
if _shadowed:
    logging.getLogger("member3.live").warning("shell environment had %s set; using the .env values instead", _shadowed)
logging.getLogger("member3.live").info("stream secret %s", fingerprint(settings.webhook_token))


class DemoSource:
    """Dev only: every call_sid maps to the same demo campaign."""

    def get(self, call_sid: str, wait_s: float = 0.0) -> CallContext:
        campaign = CampaignInfo(
            name=os.getenv("DEV_EVENT_NAME", "TechFest"), venue=os.getenv("DEV_VENUE", "the main auditorium"),
            event_date=os.getenv("DEV_EVENT_DATE") or date(date.today().year, 11, 15),
            event_time=os.getenv("DEV_EVENT_TIME", "10 AM"), organiser=os.getenv("DEV_ORGANISER", "your college"),
            language=os.getenv("DEV_LANGUAGE", "en"), greeting_override=os.getenv("DEV_GREETING") or None)
        return CallContext(provider_call_id=call_sid, attempt_id=0, participant_id="dev-participant",
                           campaign_id="dev-campaign", campaign=campaign)


app = FastAPI()
if os.getenv("DEV_EXPERIMENT") == "probe":       # diagnostic: no TTS/STT, logs a timeline (see probe.py)
    app.include_router(create_probe_router(settings.webhook_token))
else:
    app.include_router(LiveService(settings, LogSink(), source=DemoSource()).router)


@app.get("/health")
def health():
    return {"ok": True}
