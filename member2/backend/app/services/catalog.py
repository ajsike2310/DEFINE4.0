"""Setting up events and campaigns (create / edit)."""
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.errors import ApiError
from ..models import Campaign, Event
from ..schemas.api import CampaignIn, CampaignPatch, EventIn, EventPatch


def create_event(db: Session, body: EventIn) -> Event:
    e = Event(**body.model_dump())
    db.add(e)
    db.commit()
    return e


def patch_event(db: Session, e: Event, body: EventPatch) -> Event:
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k == "organizer_contact":
            setattr(e, k, v)
    db.commit()
    return e


def create_campaign(db: Session, event: Event, body: CampaignIn) -> Campaign:
    # A campaign is "simulated" (is_demo) when it belongs to the sample event or was created while the demo provider
    # is configured. Simulated campaigns can never reach a real provider.
    c = Campaign(**body.model_dump(), is_demo=event.is_demo or get_settings().call_provider == "demo")
    db.add(c)
    db.commit()
    return c


def patch_campaign(db: Session, c: Campaign, body: CampaignPatch) -> Campaign:
    if c.status not in ("draft", "scheduled"):
        raise ApiError(409, "invalid_state", "only draft/scheduled campaigns can be edited")
    data = body.model_dump(exclude_unset=True)
    if "messages" in data:
        data["messages"] = {**c.messages, **data["messages"]}
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    return c
