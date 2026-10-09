"""Browser demo calls (ElevenLabs voice + speech-to-text). Not phone calls; always simulated."""
from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from urllib.parse import quote

from member3.integrations.base import ProviderError

from ...core.config import get_settings
from ...services import browser_calls as calls
from ..deps import ApiError, get_campaign, get_db, get_recipient, voice_client

router = APIRouter(tags=["browser demo call"])
MAX_AUDIO_BYTES = 5 * 1024 * 1024


class BrowserReplyIn(BaseModel):
    dtmf: str | None = Field(default=None, max_length=1)
    text: str | None = Field(default=None, max_length=500)


def _audio(data: bytes, spoken_text: str | None = None) -> Response:
    headers = {"Cache-Control": "no-store"}
    if spoken_text is not None:
        headers["X-Spoken-Text"] = quote(spoken_text, safe="")     # headers are latin-1; the client decodes it
    return Response(content=data, media_type="audio/mpeg", headers=headers)


@router.post("/campaigns/{cid}/recipients/{rid}/browser-call", status_code=201)
def start_browser_call(cid: int, rid: int, mode: str = "main", db: Session = Depends(get_db)):
    c = get_campaign(db, cid)
    r = get_recipient(db, rid)
    if r.campaign_id != cid:
        raise ApiError(404, "not_found", f"participant {rid} not found in campaign {cid}")
    return calls.start(db, get_settings(), c, r, mode)


@router.post("/browser-calls/{aid}/speak")
def browser_call_speak(aid: int, request: Request, db: Session = Depends(get_db)):
    """Speak this call's own script (never arbitrary text) with the configured ElevenLabs voice."""
    a = calls.open_attempt(db, aid)
    voice = voice_client(request)
    try:
        return _audio(voice.speak(calls.attempt_message(db, a)))
    except ProviderError as exc:
        raise ApiError(502, "voice_failed", str(exc))


@router.post("/browser-calls/{aid}/speak-reply")
def browser_call_speak_reply(aid: int, request: Request, db: Session = Depends(get_db)):
    """Voice the agent's closing line for a finished call. Chosen from fixed text by the classified intent (and the
    organiser's approved answer for questions); callers cannot supply text."""
    line = calls.closing_for(db, aid)
    voice = voice_client(request)
    try:
        return _audio(voice.speak(line), line)
    except ProviderError as exc:
        raise ApiError(502, "voice_failed", str(exc))


@router.post("/browser-calls/{aid}/respond")
def browser_call_respond(aid: int, body: BrowserReplyIn, db: Session = Depends(get_db)):
    a = calls.open_attempt(db, aid)
    if not (body.dtmf or (body.text and body.text.strip())):
        raise ApiError(422, "validation_error", "send a keypad digit or some text")
    return calls.finish_reply(db, get_settings(), a, text=(body.text or "").strip() or None, dtmf=body.dtmf)


@router.post("/browser-calls/{aid}/respond-audio")
async def browser_call_respond_audio(aid: int, request: Request, file: UploadFile = File(...),
                                     db: Session = Depends(get_db)):
    """Transcribe the spoken reply with ElevenLabs, then classify the TEXT with the same rules as any reply.
    If transcription fails nothing is recorded (the call stays open): a reply is never guessed."""
    a = calls.open_attempt(db, aid)
    voice = voice_client(request)
    audio = await file.read(MAX_AUDIO_BYTES + 1)
    if not audio:
        raise ApiError(422, "validation_error", "no audio received")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ApiError(413, "too_large", "recording is too long; keep it under a minute")
    try:
        heard = voice.transcribe(audio, file.filename or "reply.webm", file.content_type or "audio/webm")
    except ProviderError as exc:
        raise ApiError(502, "transcription_failed", f"{exc}. Nothing was recorded; try again or press a key.")
    return calls.finish_reply(db, get_settings(), a, text=heard or None, dtmf=None)


@router.post("/browser-calls/{aid}/hangup")
def browser_call_hangup(aid: int, db: Session = Depends(get_db)):
    return calls.hangup(db, get_settings(), calls.open_attempt(db, aid))
