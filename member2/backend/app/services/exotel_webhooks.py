"""Exotel callbacks -> provider events. Built to Exotel's documented shapes; see docs/EXOTEL_INTEGRATION.md for what is
still to verify on a live account (the webhook log shows the real payloads).

Two entry points, both called by the router after the shared-secret check:
  * handle_status    the StatusCallback  (CallSid, Status ...)
  * handle_response  the Passthru applet after a Gather (CallSid, CustomField, digits ...)
"""
from sqlalchemy.orm import Session

from member3.integrations.base import ProviderEvent as PEvent
from member3.integrations.exotel.provider import STATUS_MAP

from ..core.errors import ApiError
from ..models import CallAttempt
from ..repositories import attempts as attempts_repo
from . import webhook_log
from .events import apply_event

PROVIDER = "exotel"


def find_attempt(db: Session, payload: dict) -> tuple[str, CallAttempt]:
    """Our attempt by CallSid, else by CustomField (= our attempt id, set when the call was placed)."""
    sid = str(payload.get("CallSid") or "")
    a = attempts_repo.by_provider_call(db, PROVIDER, sid) if sid else None
    if not a and str(payload.get("CustomField", "")).isdigit():
        a = attempts_repo.get(db, int(payload["CustomField"]))
        if a and a.provider != PROVIDER:
            a = None
    if not a:
        raise ApiError(404, "unknown_call", "no attempt matches CallSid/CustomField")
    return sid or a.provider_call_id or str(a.id), a


def _status(db: Session, settings, payload: dict) -> tuple[dict, int | None]:
    status = str(payload.get("Status", "")).lower()
    if not payload.get("CallSid") or status not in STATUS_MAP:
        raise ApiError(422, "unrecognised_payload", "missing CallSid or unrecognised Status")
    sid, a = find_attempt(db, payload)
    mapped = STATUS_MAP[status]
    if mapped == "initiating":
        return {"result": "ignored"}, a.id
    return {"result": apply_event(db, PROVIDER, a, PEvent(f"{sid}:{status}", sid, "status", mapped), settings)}, a.id


def _response(db: Session, settings, payload: dict) -> tuple[dict, int | None]:
    digits = str(payload.get("digits", "")).strip().strip('"').strip("'").strip()
    sid, a = find_attempt(db, payload)
    apply_event(db, PROVIDER, a, PEvent(f"{sid}:passthru-answered", sid, "status", "answered"), settings)
    db.refresh(a)
    if not digits:
        return {"result": "no digits received"}, a.id
    return {"result": apply_event(db, PROVIDER, a, PEvent(f"{sid}:digits:{digits}", sid, "response", dtmf=digits),
                                  settings)}, a.id


def _logged(endpoint: str, handler):
    def run(db: Session, settings, payload: dict, *, method: str = "POST", request_id: str | None = None) -> dict:
        try:
            out, attempt_id = handler(db, settings, payload)
        except ApiError as exc:
            db.rollback()
            webhook_log.record(db, settings, provider=PROVIDER, endpoint=endpoint, method=method, payload=payload,
                               ok=False, result=exc.detail["code"], request_id=request_id)
            raise
        webhook_log.record(db, settings, provider=PROVIDER, endpoint=endpoint, method=method, payload=payload, ok=True,
                           result=out["result"], attempt_id=attempt_id, request_id=request_id)
        return out
    run.__doc__ = handler.__doc__
    return run


handle_status = _logged("status", _status)
handle_response = _logged("response", _response)
