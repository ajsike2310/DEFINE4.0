"""Health, configuration view, scheduler control."""
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...core import dbtools, migrate
from ...core.config import get_settings
from ...repositories import health as health_repo
from ...schemas.api import PURPOSES, SUPPORTED_LANGUAGES
from ...services import readiness, scheduler
from ..deps import get_db

router = APIRouter(tags=["system"])


@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)):
    """Liveness plus a few facts an operator needs at a glance. Never returns secrets."""
    health_repo.ping(db)
    s = get_settings()
    sched = request.app.state.scheduler
    return {"status": "ok", "provider": s.call_provider, "version": request.app.version,
            "database": "ok", "schema": migrate.status(request.app.state.engine), "uptime_seconds": int(time.time() - request.app.state.started_at),
            "voice_configured": bool(s.elevenlabs_api_key),
            "scheduler": {"enabled": sched["enabled"], "ticks": sched["ticks"], "last_tick_at": sched["last_tick_at"]}}


@router.get("/health/database")
def database_health(request: Request):
    """Read-only diagnostics: schema revision, row counts and size, integrity and consistency rules."""
    engine = request.app.state.engine
    return {"schema": migrate.status(engine), "stats": dbtools.stats(engine), "check": dbtools.integrity_report(engine)}


@router.get("/settings")
def settings_info():
    s = get_settings()
    return {
        "provider": s.call_provider,
        "purposes": sorted(PURPOSES),
        "exotel_configured": all([s.exotel_account_sid, s.exotel_api_key, s.exotel_api_token,
                                  s.exotel_caller_id, s.exotel_flow_url]),
        "languages": [{"code": k, "name": v,
                       "support": "rule-based phrase matching; small synthetic test set; experimental"
                       } for k, v in SUPPORTED_LANGUAGES.items()],
        "retry_policy": {"max_attempts_default": s.max_call_attempts, "backoff_minutes": s.retry_backoff_minutes,
                         "retry_on": ["failed", "busy", "no_answer", "voicemail"]},
        "data_location": s.data_location_note,
        "transcription": ("ElevenLabs speech-to-text for the browser demo call only; phone-call audio without text is routed to human review"
                          if s.elevenlabs_api_key else "none configured; speech audio without text is routed to human review"),
    }


@router.get("/settings/exotel-readiness")
def exotel_readiness(probe: bool = False, db: Session = Depends(get_db)):
    """What is still missing before real calls can be placed. Names only, never values. `probe=true` also checks that
    PUBLIC_BASE_URL really reaches this backend (needs the tunnel to be up)."""
    return readiness.exotel_readiness(db, get_settings(), probe=probe)


@router.get("/voice/status")
def voice_status():
    """Whether the ElevenLabs key is configured. Never returns the key."""
    s = get_settings()
    return {"configured": bool(s.elevenlabs_api_key), "voice_id": s.elevenlabs_voice_id,
            "tts_model": s.elevenlabs_tts_model, "stt_model": s.elevenlabs_stt_model,
            "note": "Browser demo call: a person plays the participant. It is not a phone call and is recorded as simulated."}


@router.get("/scheduler")
def scheduler_status(request: Request):
    s = get_settings()
    return {**request.app.state.scheduler, "interval_seconds": s.scheduler_interval_seconds,
            "does": ["start campaigns that were explicitly scheduled and are due",
                     "run retries that are due (technical failures only, within the attempt limit)"]}


@router.post("/scheduler/tick")
def scheduler_tick(request: Request):
    """Run one scheduler pass right now (works even when the background loop is off)."""
    st = request.app.state
    result = scheduler.tick(st.session_factory, get_settings(), override=st.provider_override)
    st.scheduler["last_tick_at"], st.scheduler["last_result"] = result["at"], result
    st.scheduler["ticks"] += 1
    return result
