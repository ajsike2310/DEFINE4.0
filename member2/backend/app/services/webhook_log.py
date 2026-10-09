"""Keep every authenticated provider callback (masked) so a live integration can be diagnosed from what really arrived.

Never stored: the shared-secret `token`, or whole phone numbers (they are masked like everywhere else). Rows older than
WEBHOOK_LOG_DAYS are pruned; WEBHOOK_LOG_DAYS=0 turns logging off. A logging failure never affects the callback itself.
"""
import logging
import re
from datetime import timedelta

from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import WebhookLog
from ..repositories import webhook_logs as repo
from .events import mask

log = logging.getLogger("webhooks")

PHONE_LIKE = re.compile(r"^\+?\d[\d \-]{7,18}\d$")
VERBATIM_KEYS = {"callsid", "sid", "customfield", "digits", "status", "event", "direction", "duration",
                 "starttime", "endtime", "currenttime", "calltype"}
MAX_KEYS, MAX_VALUE = 40, 200
PRUNE_EVERY = 50


def mask_payload(payload: dict) -> dict:
    out: dict[str, str] = {}
    for key, value in list(payload.items())[:MAX_KEYS]:
        name = str(key)
        if name.lower() == "token":
            continue
        text = ("" if value is None else str(value))[:MAX_VALUE]
        if name.lower() not in VERBATIM_KEYS and PHONE_LIKE.match(text.strip()):
            text = mask(text.strip())
        out[name[:60]] = text
    return out


def record(db: Session, settings, *, provider: str, endpoint: str, method: str, payload: dict, ok: bool, result: str,
           attempt_id: int | None = None, request_id: str | None = None) -> None:
    if settings.webhook_log_days <= 0:
        return
    try:
        row = WebhookLog(provider=provider, endpoint=endpoint, method=method[:8], request_id=request_id, ok=ok,
                         result=result[:100], call_attempt_id=attempt_id, payload=mask_payload(payload))
        db.add(row)
        db.commit()
        if row.id % PRUNE_EVERY == 0:
            repo.delete_older_than(db, utcnow() - timedelta(days=settings.webhook_log_days))
            db.commit()
    except Exception:                      # diagnostics must never break the callback
        db.rollback()
        log.exception("could not record webhook")
