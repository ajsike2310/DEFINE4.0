"""Events and their CSV exports."""
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ...repositories import events as events_repo
from ...schemas.api import EventIn, EventOut, EventPatch
from ...services import catalog, exports
from ...services.presenters import event_out, events_out
from ..deps import get_db, get_event

router = APIRouter(tags=["events"])


@router.post("/events", response_model=EventOut, status_code=201)
def create_event(body: EventIn, db: Session = Depends(get_db)):
    return event_out(db, catalog.create_event(db, body))


@router.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    return events_out(db, events_repo.list_all(db))


@router.get("/events/{eid}", response_model=EventOut)
def read_event(eid: int, db: Session = Depends(get_db)):
    return event_out(db, get_event(db, eid))


@router.patch("/events/{eid}", response_model=EventOut)
def patch_event(eid: int, body: EventPatch, db: Session = Depends(get_db)):
    return event_out(db, catalog.patch_event(db, get_event(db, eid), body))


def _csv(text: str, filename: str) -> Response:
    return Response(content=text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@router.get("/events/{eid}/export/participants.csv")
def export_participants(eid: int, masked: bool = Query(True, description="mask phone numbers (default)"),
                        db: Session = Depends(get_db)):
    """Every participant of the event's campaigns with consent, outcome and last response. Spreadsheet-safe."""
    get_event(db, eid)
    return _csv(exports.participants_csv(db, eid, masked), f"event-{eid}-participants.csv")


@router.get("/events/{eid}/export/leads.csv")
def export_leads(eid: int, masked: bool = Query(True, description="mask phone numbers (default)"),
                 db: Session = Depends(get_db)):
    get_event(db, eid)
    return _csv(exports.leads_csv(db, eid, masked), f"event-{eid}-leads.csv")
