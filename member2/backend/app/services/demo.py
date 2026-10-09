"""Clearly labelled SAMPLE data. Everything here is fictional or a demonstration scenario:
- DEFINE 4.0 @ MBCET is used only as a scenario; no organiser adoption/data access is claimed and only the venue
  string (supplied by the team) is configured - no schedule, deadline or contact is invented.
- The other two events are fictional. Their "approved info" is sample text, labelled as such.
Participants use fictional NANP 555-01xx numbers; every call is simulated by the demo provider."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from member3.integrations.demo_provider.provider import DemoProvider

from ..models import (CallAttempt, Campaign, Event, FollowUp, ImportRun, IntentResult, Lead, ProviderEvent,
                      Recipient)
from . import campaigns as svc

DEMO_PREFIX = "[SAMPLE] "
EVENT_NAME = DEMO_PREFIX + "DEFINE 4.0 - MBCET, Thiruvananthapuram"   # kept for compatibility

_OPT = "Press 9 to stop receiving calls."
PRESETS: dict[str, dict] = {
    "define": {
        "event": {"name": EVENT_NAME, "approved_info": {"venue": "MBCET, Thiruvananthapuram"},
                  "description": "Demonstration scenario only. Not affiliated with or requested by the organisers."},
        "campaign": {"name": "Attendance confirmation", "purpose": "attendance_confirmation", "languages": ["en", "ml"],
                     "messages": {
                         "en": "Hello, this is Cadence calling on behalf of the DEFINE 4.0 organisers to confirm your attendance. "
                               f"Press 1 to confirm, 2 if you cannot attend, 3 to request a callback, 4 for more information. {_OPT}",
                         "ml": "നമസ്കാരം, DEFINE 4.0 സംഘാടകർക്ക് വേണ്ടി നിങ്ങളുടെ പങ്കാളിത്തം സ്ഥിരീകരിക്കാൻ വിളിക്കുന്നതാണ്. "
                               "സ്ഥിരീകരിക്കാൻ 1 അമർത്തുക."}},
        # (phone, language, ref) - last digit(s) pick the simulated scenario; 114 stays unclear after clarification
        "participants": [(f"+1555010010{i}", "ml" if i % 3 == 2 else "en") for i in range(10)] + [("+15550100114", "en")],
    },
    "sprint": {
        "event": {"name": DEMO_PREFIX + "Campus Code Sprint (fictional)",
                  "approved_info": {"venue": "Seminar Hall A (sample text)", "schedule": "Saturday 10:00-18:00 (sample text)"},
                  "description": "Fictional sample event with venue AND schedule approved, so both questions get answers."},
        "campaign": {"name": "Schedule announcement", "purpose": "schedule_venue_update", "languages": ["en", "ml"],
                     "messages": {
                         "en": f"Hello, this is Cadence calling on behalf of the Campus Code Sprint organisers with a schedule update. Press 1 to acknowledge, 3 for a callback, 4 for more information. {_OPT}",
                         "ml": "നമസ്കാരം, ക്യാമ്പസ് കോഡ് സ്പ്രിന്റ് സംഘാടകരുടെ ഷെഡ്യൂൾ അറിയിപ്പാണിത്. അറിഞ്ഞു എന്ന് അറിയിക്കാൻ 1 അമർത്തുക."}},
        "participants": [(f"+1555010020{i}", "ml" if i % 3 == 2 else "en") for i in range(10)] + [("+15550100219", "en")],
    },
    "hacknight": {
        "event": {"name": DEMO_PREFIX + "Hack Night Workshop (fictional)", "approved_info": {},
                  "description": "Fictional sample event with NO approved facts, so every question goes to a person."},
        "campaign": {"name": "Deadline reminder", "purpose": "submission_deadline_reminder", "languages": ["en"],
                     "messages": {"en": f"Hello, this is Cadence calling on behalf of the Hack Night organisers with a reminder about the submission deadline shared earlier. Press 1 to acknowledge, 4 for more information. {_OPT}"}},
        "participants": [(f"+1555010030{i}", "en") for i in (0, 1, 2, 3, 4, 5, 9)],
    },
}


REF_PREFIX = {"define": "SAMPLE", "sprint": "SPRINT", "hacknight": "HACKN"}


def _event(db: Session, key: str) -> Event:
    spec = PRESETS[key]["event"]
    ev = db.scalar(select(Event).where(Event.name == spec["name"]))
    if not ev:
        ev = Event(name=spec["name"], description=spec["description"], approved_info=spec["approved_info"], is_demo=True)
        db.add(ev)
        db.flush()
    return ev


def get_or_create_demo_event(db: Session) -> Event:
    return _event(db, "define")


LEAD_SOURCES_CYCLE = ["registration_form", "registration_form", "referral", "walk_in", "csv_import", "manual",
                      "registration_form", "referral", "csv_import", "registration_form"]
LEAD_INTERESTS = ["AI / ML", "Web", "Hardware", None, "Open source", "Design", "AI / ML", None, "Web", "Security"]


def seed_leads(db: Session, key: str, ev: Event) -> int:
    """Ten fictional sample leads per sample event (once). Fictional 555-01xx numbers; clearly labelled sample."""
    if db.scalar(select(Lead.id).where(Lead.event_id == ev.id)):
        return 0
    k = list(PRESETS).index(key)
    for i in range(10):
        consent = "revoked" if i == 9 else ("unknown" if i % 5 == 4 else "granted")
        src = LEAD_SOURCES_CYCLE[i]
        db.add(Lead(event_id=ev.id, name=f"Sample Lead {k}{i}", phone=f"+1555010{1}{k}{i}",
                    email=f"sample.lead{k}{i}@example.invalid" if src in ("registration_form", "referral") else None,
                    source=src, interest=LEAD_INTERESTS[i], preferred_language="ml" if i % 3 == 2 else "en",
                    consent_status=consent, status="lost" if consent == "revoked" else ("contacted" if i == 3 else "new"),
                    notes="Sample lead (fictional).", is_demo=True))
    db.add(ImportRun(kind="leads", event_id=ev.id, filename="[SAMPLE] registration-export.csv", rows_total=12,
                     imported=10, rejected=2, is_demo=True,
                     reasons={"duplicate phone": 1, "phone must be E.164, e.g. +919876543210": 1}))
    return 10


def seed_sample_leads(db: Session) -> int:
    """Add sample leads to sample events that do not have any yet (e.g. events created before leads existed)."""
    n = 0
    for key in PRESETS:
        name = PRESETS[key]["event"]["name"]
        # sample events created by an earlier build have no "[SAMPLE] " prefix; they are still demo events
        ev = db.scalar(select(Event).where(Event.is_demo.is_(True), Event.name.in_([name, name.removeprefix(DEMO_PREFIX)])))
        if ev:
            n += seed_leads(db, key, ev)
    db.commit()
    return n


def seed_demo(db: Session, key: str = "define") -> Campaign:
    preset = PRESETS[key]
    ev = _event(db, key)
    seed_leads(db, key, ev)
    n = db.query(Campaign).filter(Campaign.event_id == ev.id).count() + 1
    spec = preset["campaign"]
    camp = Campaign(event_id=ev.id, name=f"{DEMO_PREFIX}{spec['name']} #{n}", purpose=spec["purpose"],
                    messages=spec["messages"], languages=spec["languages"], status="draft", is_demo=True)
    db.add(camp)
    db.flush()
    for i, (phone, lang) in enumerate(preset["participants"]):
        db.add(Recipient(campaign_id=camp.id, external_ref=f"{REF_PREFIX[key]}-{i:03d}",
                         name=f"Sample Participant {i}", phone=phone,
                         preferred_language=lang if lang in spec["languages"] else None, segment="sample",
                         consent_status="granted", is_demo=True))
    db.commit()
    return camp


def run_simulation(db: Session, settings, camp: Campaign) -> None:
    """Start the campaign and run the retry rounds, all through the normal (simulated) code path."""
    provider = DemoProvider()
    svc.start_campaign(db, provider, settings, camp)
    for _ in range(4):
        db.refresh(camp)
        if camp.status != "running":
            break
        svc.retry_due(db, provider, settings, camp, force=True)


def seed_all(db: Session, settings, run: bool = False) -> list[Campaign]:
    out = []
    for key in PRESETS:
        c = seed_demo(db, key)
        if run:
            run_simulation(db, settings, c)
        out.append(c)
    return out


def reset_demo(db: Session) -> int:
    n = 0
    for c in db.scalars(select(Campaign).where(Campaign.is_demo.is_(True))):
        _purge(db, c)
        n += 1
    db.flush()
    for model in (Lead, ImportRun):
        for row in db.scalars(select(model).where(model.is_demo.is_(True))):
            db.delete(row)
    db.flush()
    for ev in db.scalars(select(Event).where(Event.is_demo.is_(True))):
        db.delete(ev)
    db.commit()
    return n


def _purge(db: Session, c: Campaign) -> None:
    att_ids = [a.id for a in db.scalars(select(CallAttempt).where(CallAttempt.campaign_id == c.id))]
    if att_ids:
        for row in db.scalars(select(ProviderEvent).where(ProviderEvent.call_attempt_id.in_(att_ids))):
            db.delete(row)
    for model in (FollowUp, IntentResult, CallAttempt):
        for row in db.scalars(select(model).where(model.campaign_id == c.id)):
            db.delete(row)
    db.flush()
    db.delete(c)
