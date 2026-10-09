"""Shared FastAPI dependencies and lookups for the routers."""
from fastapi import Request
from sqlalchemy.orm import Session

from member3.integrations.base import ProviderError
from member3.integrations.elevenlabs.client import ElevenLabsClient

from ..core.config import get_settings
from ..core.errors import ApiError
from ..models import Campaign, Event, Lead, Recipient
from ..services.providers import provider_for_campaign

__all__ = ["ApiError", "get_db", "default_provider_for", "provider_for", "voice_client",
           "get_campaign", "get_event", "get_lead", "get_recipient"]


def get_db(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def default_provider_for(request: Request, campaign: Campaign):
    """Demo-seeded campaigns can NEVER reach a real provider."""
    try:
        return provider_for_campaign(get_settings(), campaign, getattr(request.app.state, "provider_override", None))
    except ProviderError as exc:
        raise ApiError(503, "provider_unavailable", str(exc))


def provider_for(request: Request, campaign: Campaign):
    # Resolved through the routes module at call time, so operators and tests can replace
    # `routes.provider_for` (the long-standing extension point) without touching the routers.
    from . import routes
    return routes.provider_for(request, campaign)


def voice_client(request: Request) -> ElevenLabsClient:
    override = getattr(request.app.state, "elevenlabs_override", None)
    if override:
        return override
    s = get_settings()
    if not s.elevenlabs_api_key:
        raise ApiError(503, "voice_unavailable", "ELEVENLABS_API_KEY is not set in .env; voice and speech are off")
    return ElevenLabsClient(s.elevenlabs_api_key, voice_id=s.elevenlabs_voice_id,
                            tts_model=s.elevenlabs_tts_model, stt_model=s.elevenlabs_stt_model)


def _get(db: Session, model, ident: int, label: str):
    row = db.get(model, ident)
    if not row:
        raise ApiError(404, "not_found", f"{label} {ident} not found")
    return row


def get_campaign(db: Session, cid: int) -> Campaign:
    return _get(db, Campaign, cid, "campaign")


def get_event(db: Session, eid: int) -> Event:
    return _get(db, Event, eid, "event")


def get_lead(db: Session, lid: int) -> Lead:
    return _get(db, Lead, lid, "lead")


def get_recipient(db: Session, rid: int) -> Recipient:
    row = db.get(Recipient, rid)
    if not row:
        raise ApiError(404, "not_found", "recipient not found")
    return row
