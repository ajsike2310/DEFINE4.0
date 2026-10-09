"""API assembly. Endpoints live in api/routers/*, rules in services/*.

`provider_for` stays defined here on purpose: it is the documented place to substitute the call provider
(the routers look it up through this module at call time).
"""
from fastapi import APIRouter

from ..core.errors import ApiError  # noqa: F401  (re-exported for callers that imported it from here)
from .deps import default_provider_for as provider_for  # noqa: F401
from .routers import (browser_calls, campaigns, demo, events, followups, insights, leads, participants, system,
                      webhooks)

router = APIRouter(prefix="/api")
for _r in (system, events, campaigns, participants, followups, leads, insights, demo, webhooks, browser_calls):
    router.include_router(_r.router)
