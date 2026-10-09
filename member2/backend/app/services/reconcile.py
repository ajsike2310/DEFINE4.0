"""Calls whose result never arrived.

A real call can be left "initiating" or "answered" forever if Exotel's callbacks do not reach us (tunnel down, flow
misconfigured). That blocks the participant and the campaign. After STALE_CALL_MINUTES we ask the provider what happened
(Exotel's Call Details API) and apply the answer through the same event path the callback would have used, with the same event
id, so a late callback is recognised as a duplicate.

We never guess: if the provider cannot say, the attempt is left as it is and reported. A call that may never have been placed
(we have no provider call id) is closed as failed WITHOUT a retry, because retrying could dial the person twice.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from member3.integrations.base import ProviderError
from member3.integrations.base import ProviderEvent as PEvent
from member3.integrations.exotel.provider import STATUS_MAP

from ..core.db import utcnow
from ..models import Campaign
from ..repositories import attempts as attempts_repo
from . import campaigns as campaign_svc
from .events import apply_event

TERMINAL = {"completed", "failed", "busy", "no_answer", "voicemail"}


def reconcile(db: Session, settings, provider, campaign: Campaign | None = None, *, minutes: int | None = None,
              now: datetime | None = None) -> dict:
    """Check overdue real calls. `minutes` overrides STALE_CALL_MINUTES (0 = every open real call)."""
    now = now or utcnow()
    minutes = settings.stale_call_minutes if minutes is None else minutes
    attempts = attempts_repo.open_real_before(db, now - timedelta(minutes=minutes), campaign.id if campaign else None)
    out = {"checked": len(attempts), "updated": [], "unchanged": [], "unplaced": [], "errors": []}
    lookup = getattr(provider, "get_call_status", None)
    touched = set()
    for a in attempts:
        touched.add(a.campaign_id)
        if not a.provider_call_id:
            a.status, a.completed_at = "failed", now
            a.failure_reason = "unknown whether the call was placed (no provider call id); not retried"
            db.commit()
            out["unplaced"].append(a.id)
            continue
        if lookup is None:
            out["errors"].append({"attempt_id": a.id, "error": "this provider cannot report call status"})
            continue
        try:
            raw = str((lookup(a.provider_call_id) or {}).get("Status", "")).lower()
        except ProviderError as exc:
            out["errors"].append({"attempt_id": a.id, "error": str(exc)[:160]})
            continue
        mapped = STATUS_MAP.get(raw)
        if mapped not in TERMINAL:
            out["unchanged"].append({"attempt_id": a.id, "provider_status": raw or "unknown"})
            continue
        result = apply_event(db, a.provider, a, PEvent(f"{a.provider_call_id}:{raw}", a.provider_call_id, "status", mapped),
                             settings)
        out["updated"].append({"attempt_id": a.id, "provider_status": raw, "result": result})
    for cid in touched:
        c = campaign if campaign and campaign.id == cid else db.get(Campaign, cid)
        if c is not None:
            campaign_svc.refresh_status(db, c)
    db.commit()
    return out
