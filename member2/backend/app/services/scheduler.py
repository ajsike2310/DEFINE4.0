"""Scheduled launch and automatic due retries.

Off unless SCHEDULER_ENABLED=true. A tick (also callable on demand through the API) does exactly two things:
  1. starts campaigns that an organiser explicitly scheduled and whose time has come;
  2. runs retries that are already due (technical failures only, bounded by the campaign's max attempts).
Nothing else is ever dialled automatically; opt-out, consent and attempt limits are enforced by the same code
paths as a manual start.
"""
import asyncio
import logging
from datetime import datetime

from member3.integrations.base import ProviderError

from ..core.db import utcnow
from ..core.errors import ApiError
from ..models import Campaign
from ..repositories import campaigns as campaigns_repo
from . import campaigns as svc
from . import reconcile
from .providers import provider_for_campaign
from .states import InvalidTransition

log = logging.getLogger("scheduler")


def schedule(db, c: Campaign, when: datetime) -> Campaign:
    if when.tzinfo is None:
        raise ApiError(422, "validation_error", "scheduled_at must include a timezone offset")
    if when <= utcnow():
        raise ApiError(422, "validation_error", "scheduled_at must be in the future; use Start to run now")
    if not c.recipients:
        raise ApiError(422, "no_recipients", "add recipients before scheduling")
    try:
        svc.set_campaign_status(c, "scheduled")
    except InvalidTransition as exc:
        raise ApiError(409, "invalid_state", str(exc))
    c.scheduled_at = when
    db.commit()
    return c


def unschedule(db, c: Campaign) -> Campaign:
    if c.status != "scheduled":
        raise ApiError(409, "invalid_state", f"only a scheduled campaign can be unscheduled (this one is {c.status})")
    try:
        svc.set_campaign_status(c, "draft")
    except InvalidTransition as exc:
        raise ApiError(409, "invalid_state", str(exc))
    db.commit()
    return c


def tick(factory, settings, *, override=None, now: datetime | None = None) -> dict:
    """Run one scheduler pass. Never raises: a failing campaign is reported and the rest still run."""
    now = now or utcnow()
    result: dict = {"at": now.isoformat(), "started": [], "retried": [], "reconciled": [], "errors": []}
    with factory() as db:
        for c in campaigns_repo.due_scheduled(db, now):
            try:
                out = svc.start_campaign(db, provider_for_campaign(settings, c, override), settings, c)
                result["started"].append({"campaign_id": c.id, "dispatched": out["dispatched"]})
            except (ProviderError, InvalidTransition) as exc:
                result["errors"].append({"campaign_id": c.id, "error": str(exc)[:200]})
                db.rollback()
        for c in campaigns_repo.running(db):
            try:
                provider = provider_for_campaign(settings, c, override)
                out = svc.retry_due(db, provider, settings, c, force=False, now=now)
                if out["dispatched"]:
                    result["retried"].append({"campaign_id": c.id, "dispatched": out["dispatched"]})
                if settings.stale_call_minutes > 0 and not getattr(provider, "is_simulated", True):
                    rec = reconcile.reconcile(db, settings, provider, c, now=now)
                    if rec["updated"] or rec["unplaced"] or rec["errors"]:
                        result["reconciled"].append({"campaign_id": c.id, "updated": len(rec["updated"]),
                                                     "unplaced": len(rec["unplaced"]), "errors": len(rec["errors"])})
            except (ProviderError, InvalidTransition) as exc:
                result["errors"].append({"campaign_id": c.id, "error": str(exc)[:200]})
                db.rollback()
    return result


async def run_forever(app, settings) -> None:
    state = app.state.scheduler
    while True:
        try:
            result = await asyncio.to_thread(tick, app.state.session_factory, settings, override=app.state.provider_override)
            state["last_tick_at"], state["last_result"] = result["at"], result
            state["ticks"] += 1
            if result["started"] or result["retried"] or result["reconciled"] or result["errors"]:
                log.info("scheduler: started=%d retried=%d reconciled=%d errors=%d", len(result["started"]),
                         len(result["retried"]), len(result["reconciled"]), len(result["errors"]))
        except Exception:                                    # keep the loop alive whatever happens
            log.exception("scheduler tick failed")
        await asyncio.sleep(settings.scheduler_interval_seconds)
