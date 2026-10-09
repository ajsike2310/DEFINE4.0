"""Analytics and the Data and AI quality report (computed by member 4's modules)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from member4.analytics.metrics import compute
from member4.analytics.quality import compute as compute_quality

from ..deps import ApiError, get_db

router = APIRouter(tags=["insights"])


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), campaign_id: int | None = None, event_id: int | None = None,
              source: str = Query("all", pattern="^(all|real|simulated)$")):
    return compute(db, campaign_id, source, event_id)


@router.get("/quality")
def quality(db: Session = Depends(get_db), event_id: int | None = None, source: str = "all"):
    if source not in ("all", "real", "simulated"):
        raise ApiError(422, "validation_error", "source must be all|real|simulated")
    return compute_quality(db, event_id=event_id, source=source)
