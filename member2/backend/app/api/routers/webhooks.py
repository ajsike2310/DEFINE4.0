"""Provider callbacks, and the log of what was received."""
import hmac

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from member3.integrations.base import ProviderEvent as PEvent

from ...core.config import get_settings
from ...repositories import attempts as attempts_repo
from ...repositories import webhook_logs as log_repo
from ...schemas.api import WebhookEventIn, WebhookLogOut
from ...services import exotel_webhooks
from ...services.events import apply_event
from ..deps import ApiError, get_db

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/demo")
def webhook_demo(body: WebhookEventIn, db: Session = Depends(get_db)):
    """Inject a SIMULATED provider event (duplicate/ordering tests, manual demos). Demo attempts only."""
    a = attempts_repo.by_provider_call(db, "demo", body.provider_call_id)
    if not a:
        raise ApiError(404, "unknown_call", "no attempt for that provider call id")
    ev = PEvent(body.event_id, body.provider_call_id, body.kind, body.status, body.text, body.dtmf)
    return {"result": apply_event(db, "demo", a, ev, get_settings())}


def _exotel_guard(token: str) -> None:
    """Exotel documents no webhook signature, so a shared secret in the URL is required."""
    s = get_settings()
    if not s.exotel_webhook_token:
        raise ApiError(503, "webhook_disabled", "EXOTEL_WEBHOOK_TOKEN not configured")
    if not hmac.compare_digest(token, s.exotel_webhook_token):
        raise ApiError(401, "unauthorized", "bad webhook token")


async def _payload(request: Request) -> dict:
    """Merge query params with a JSON or form body (Passthru sends GET query params; StatusCallback can be JSON)."""
    data: dict = dict(request.query_params)
    if request.method == "POST":
        ctype = request.headers.get("content-type", "")
        try:
            data.update(await request.json() if "json" in ctype else dict(await request.form()))
        except Exception:
            raise ApiError(422, "unrecognised_payload", "body is not valid JSON/form data")
    return data


@router.post("/webhooks/exotel")
async def webhook_exotel(request: Request, token: str = "", db: Session = Depends(get_db)):
    """Exotel StatusCallback (documented JSON/form fields: CallSid, Status, ...). Only documented `Status`
    values are interpreted. Every authenticated callback is kept, masked, in /webhooks/log."""
    _exotel_guard(token)
    return exotel_webhooks.handle_status(db, get_settings(), await _payload(request), method=request.method,
                                         request_id=getattr(request.state, "request_id", None))


@router.get("/webhooks/exotel/response")
@router.post("/webhooks/exotel/response")
async def webhook_exotel_response(request: Request, token: str = "", db: Session = Depends(get_db)):
    """Target of the flow's Passthru applet (after a Gather). Documented: Passthru sends CallSid, CustomField and
    `digits` (wrapped in double quotes). Reaching this point means the callee answered, so we record
    'answered' first, then the keypad response."""
    _exotel_guard(token)
    return exotel_webhooks.handle_response(db, get_settings(), await _payload(request), method=request.method,
                                           request_id=getattr(request.state, "request_id", None))


@router.get("/webhooks/log", response_model=list[WebhookLogOut])
def webhook_log(db: Session = Depends(get_db), provider: str | None = None, ok: bool | None = None,
                limit: int = Query(50, ge=1, le=200)):
    """The most recent authenticated provider callbacks, newest first, with masked payloads. Use it to see exactly
    what Exotel sent and how we handled it (`result`)."""
    return log_repo.recent(db, provider=provider, ok=ok, limit=limit)
