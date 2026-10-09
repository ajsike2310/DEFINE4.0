"""Labelled sample data."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...repositories import events as events_repo
from ...schemas.api import CampaignOut
from ...services.demo import reset_demo, seed_all, seed_demo, seed_sample_leads
from ...services.presenters import campaign_out, campaigns_out, events_out
from ..deps import get_db

router = APIRouter(tags=["sample data"])


@router.post("/demo/seed", response_model=CampaignOut, status_code=201)
def demo_seed(db: Session = Depends(get_db)):
    return campaign_out(db, seed_demo(db))


@router.post("/demo/seed-leads", status_code=201)
def demo_seed_leads(db: Session = Depends(get_db)):
    """Add clearly-labelled sample leads to sample events that have none."""
    return {"leads_added": seed_sample_leads(db)}


@router.post("/demo/seed-all", status_code=201)
def demo_seed_all(run: bool = False, db: Session = Depends(get_db)):
    """Create the three labelled sample events (each with a draft campaign). run=true also executes the
    simulated calls + retry rounds through the normal code path (clarify-once is left for you to click)."""
    camps = seed_all(db, get_settings(), run=run)
    by_id = {e.id: e for e in events_repo.by_ids(db, {c.event_id for c in camps})}
    events = [by_id[c.event_id] for c in camps]                         # same order as the campaigns
    return {"ran": run, "campaigns": campaigns_out(db, camps), "events": events_out(db, events)}


@router.delete("/demo")
def demo_reset(db: Session = Depends(get_db)):
    return {"deleted_campaigns": reset_demo(db)}
