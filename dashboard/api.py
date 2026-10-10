"""HTTP API behind the dashboard UI."""
import csv
import hmac
import io
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .db import Db, loads, now
from .messages import (BUILTIN_VARS, EVENT_TYPES, LANGUAGES, PURPOSES, _OPTIONAL_VARS, compose, default_template)
from .phone import mask_phone, normalize_phone
from .service import OUTCOME_LABELS, CampaignError, Engine, outcome_of, summarize

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^\d{2}:\d{2}$")


class EventIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = "webinar"
    mode: str | None = None
    venue: str = ""
    event_date: str | None = None
    event_time: str | None = None
    organiser: str = Field(default="", max_length=120)
    description: str = ""


class ParticipantIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str
    language: str = ""
    segment: str = Field(default="", max_length=60)
    fields: dict[str, str] = {}
    can_call: bool = True                       # consent: False = never call this person


class CampaignPersonIn(ParticipantIn):
    message: str = Field(default="", max_length=1000)        # this person's own message in this campaign


class ImportIn(BaseModel):
    csv: str


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = "invite"
    language: str = "en"
    template: str = ""
    max_attempts: int = Field(default=3, ge=1, le=5)
    auto_retry: bool = True                     # call non-responders again by itself
    retry_interval_min: int = Field(default=30, ge=0, le=1440)
    add_all: bool = False                       # create the campaign with everyone on the event list already in it


class PreviewIn(BaseModel):
    template: str | None = None
    purpose: str | None = None
    language: str | None = None
    participant_id: int | None = None
    message: str | None = None                  # this person's unsaved personal message


def _check_event(e: EventIn) -> dict:
    if e.type not in EVENT_TYPES:
        raise HTTPException(422, "Unknown event type")
    if e.event_date and not _DATE.match(e.event_date):
        raise HTTPException(422, "Date must be YYYY-MM-DD")
    if e.event_time and not _TIME.match(e.event_time):
        raise HTTPException(422, "Time must be HH:MM")
    d = e.model_dump()
    d["mode"] = d["mode"] if d["mode"] in ("online", "in_person") else EVENT_TYPES[e.type]["mode"]
    d["name"] = d["name"].strip()
    return d


def build_router(db: Db, engine: Engine, settings, require_auth) -> APIRouter:
    r = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

    def get_or_404(table: str, row_id: int) -> dict:
        row = db.one(f"SELECT * FROM {table} WHERE id=?", (row_id,))
        if not row:
            raise HTTPException(404, f"{table[:-1].capitalize()} not found")
        return row

    def person_out(p: dict, reveal: bool = True) -> dict:
        out = {**p, "fields": loads(p["fields"]), "opted_out": bool(p["opted_out"]),
               "can_call": bool(p["can_call"])}
        out.pop("custom_message", None)
        if not reveal:
            out["phone"] = mask_phone(p["phone"])
        return out

    def calls_for(campaign_id: int) -> list[dict]:
        rows = db.q("SELECT c.*, p.name AS participant_name, p.phone, p.segment, p.language AS p_language, "
                    "p.opted_out, p.can_call FROM calls c JOIN participants p ON p.id=c.participant_id "
                    "WHERE c.campaign_id=? ORDER BY c.id", (campaign_id,))
        camp_lang = db.one("SELECT language FROM campaigns WHERE id=?", (campaign_id,))["language"]
        for c in rows:
            c["outcome"] = outcome_of(c)
            c["language"] = c["p_language"] or camp_lang
            c["needs_review"] = bool(c["needs_review"])
            c["blocked"] = "opted out" if c["opted_out"] else ("not OK to call" if not c["can_call"] else "")
            c["opted_out"] = bool(c["opted_out"] or not c["can_call"])
        return rows

    def campaign_out(c: dict, with_calls: bool = False) -> dict:
        calls = calls_for(c["id"])
        s = summarize(calls)
        sched = sorted(x["next_attempt_at"] for x in calls if x.get("next_attempt_at"))
        s["retries_scheduled"] = len(sched)
        out = {**c, "summary": s, "state": engine.state_of(c, calls), "next_retry_at": sched[0] if sched else None,
               "auto_retry": bool(c["auto_retry"])}
        if with_calls:
            out["calls"] = calls
        return out

    # ------------------------------------------------------------------ meta
    @r.get("/meta")
    def meta():
        extra = sorted({k for p in db.q("SELECT fields FROM participants") for k in loads(p["fields"])})
        return {
            "provider": engine.provider.name, "simulated": engine.provider.is_simulated,
            "calling_hours": engine.get_hours(),
            "languages": LANGUAGES, "purposes": PURPOSES, "outcomes": OUTCOME_LABELS,
            "event_types": {k: {"label": v["label"], "mode": v["mode"]} for k, v in EVENT_TYPES.items()},
            "variables": [v for v in BUILTIN_VARS if v not in _OPTIONAL_VARS] + extra,
            "max_attempts": settings.max_attempts}

    @r.get("/templates")
    def template(event_type: str = "webinar", purpose: str = "invite", language: str = "en"):
        return {"template": default_template(event_type, purpose, language)}

    # ------------------------------------------------------------------ events
    @r.get("/events")
    def list_events():
        out = []
        for e in db.q("SELECT * FROM events ORDER BY COALESCE(event_date,'9999') DESC, id DESC"):
            e["participants"] = db.one("SELECT COUNT(*) n FROM participants WHERE event_id=?", (e["id"],))["n"]
            camps = db.q("SELECT id FROM campaigns WHERE event_id=?", (e["id"],))
            e["campaigns"] = len(camps)
            calls = [c for cm in camps for c in db.q("SELECT status, attendance FROM calls WHERE campaign_id=?", (cm["id"],))]
            e["confirmed"] = db.one("SELECT COUNT(*) n FROM participants WHERE event_id=? AND rsvp='attending'", (e["id"],))["n"]
            e["open_tasks"] = db.one("SELECT COUNT(*) n FROM tasks WHERE event_id=? AND status='open'", (e["id"],))["n"]
            out.append(e)
        return out

    @r.post("/events", status_code=201)
    def create_event(body: EventIn):
        d = _check_event(body)
        eid = db.insert("events", created_at=now(), **d)
        return get_or_404("events", eid)

    @r.get("/events/{event_id}")
    def get_event(event_id: int):
        e = get_or_404("events", event_id)
        e["segments"] = [x["segment"] for x in db.q(
            "SELECT DISTINCT segment FROM participants WHERE event_id=? AND segment!='' ORDER BY segment", (event_id,))]
        return e

    @r.patch("/events/{event_id}")
    def update_event(event_id: int, body: EventIn):
        get_or_404("events", event_id)
        db.update("events", event_id, **_check_event(body))
        return get_or_404("events", event_id)

    @r.delete("/events/{event_id}", status_code=204)
    def delete_event(event_id: int):
        get_or_404("events", event_id)
        if any(engine.is_active(c["id"]) for c in db.q("SELECT id FROM campaigns WHERE event_id=?", (event_id,))):
            raise HTTPException(409, "Pause the running campaigns first")
        db.x("DELETE FROM events WHERE id=?", (event_id,))

    # ------------------------------------------------------------------ participants
    @r.get("/events/{event_id}/participants")
    def list_participants(event_id: int):
        get_or_404("events", event_id)
        return [person_out(p) | {"campaigns": [c["name"] for c in db.q(
                    "SELECT cm.name FROM calls c JOIN campaigns cm ON cm.id=c.campaign_id WHERE c.participant_id=?", (p["id"],))]}
                for p in db.q("SELECT * FROM participants WHERE event_id=? ORDER BY id DESC", (event_id,))]

    def _add_person(event_id: int, b: ParticipantIn, reuse: bool = False) -> dict:
        phone = normalize_phone(b.phone)
        if not phone:
            raise HTTPException(422, f"'{b.phone}' is not a valid phone number")
        if reuse and (existing := db.one("SELECT * FROM participants WHERE event_id=? AND phone=?", (event_id, phone))):
            return existing
        if b.language and b.language not in LANGUAGES:
            raise HTTPException(422, "Unsupported language")
        import json
        try:
            pid = db.insert("participants", event_id=event_id, name=b.name.strip(), phone=phone, language=b.language,
                            segment=b.segment.strip(), fields=json.dumps(b.fields), can_call=int(b.can_call),
                            created_at=now())
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(409, f"{phone} is already on this event's list")
            raise
        return get_or_404("participants", pid)

    @r.post("/events/{event_id}/participants", status_code=201)
    def add_participant(event_id: int, body: ParticipantIn):
        get_or_404("events", event_id)
        return person_out(_add_person(event_id, body))

    def _import(event_id: int, text: str, campaign_id: int | None = None) -> dict:
        """CSV with a header row. Columns: name, phone, language, segment, message; any other column becomes a
        variable usable in the message (e.g. an `amount` column -> {amount}). In a campaign, `message` is that
        person's own message in that campaign and people already on the event's list are reused."""
        text = text.lstrip("\ufeff")
        try:
            rows = list(csv.DictReader(io.StringIO(text), dialect=csv.Sniffer().sniff(text.split("\n")[0], ",;\t")))
        except csv.Error:
            rows = list(csv.DictReader(io.StringIO(text)))
        if len(rows) > 5000:
            raise HTTPException(413, "Import at most 5,000 people at a time")
        added, errors = 0, []
        for i, row in enumerate(rows, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k}
            known = {"name", "phone", "mobile", "number", "language", "segment", "group", "message", "custom_message",
                     "consent", "can_call", "ok_to_call"}
            consent = (row.get("consent") or row.get("can_call") or row.get("ok_to_call") or "yes").lower()
            lang = (row.get("language") or "").lower()[:2]
            try:
                p = _add_person(event_id, ParticipantIn(
                    name=row.get("name") or "", phone=row.get("phone") or row.get("mobile") or row.get("number") or "",
                    language=lang if lang in LANGUAGES else "", segment=row.get("segment") or row.get("group") or "",
                    fields={k: v for k, v in row.items() if k not in known and v},
                    can_call=consent not in ("no", "n", "false", "0", "dnd", "do not call")), reuse=campaign_id is not None)
                if campaign_id is not None:
                    engine.add_members(campaign_id, [p["id"]], row.get("message") or row.get("custom_message") or "")
                added += 1
            except HTTPException as exc:
                errors.append({"row": i, "error": exc.detail})
            except ValueError:
                errors.append({"row": i, "error": "name and phone are required"})
        return {"added": added, "errors": errors[:50], "error_count": len(errors)}

    @r.post("/events/{event_id}/participants/import")
    def import_participants(event_id: int, body: ImportIn):
        get_or_404("events", event_id)
        return _import(event_id, body.csv)

    @r.patch("/participants/{pid}")
    def update_participant(pid: int, body: ParticipantIn):
        import json
        get_or_404("participants", pid)
        phone = normalize_phone(body.phone)
        if not phone:
            raise HTTPException(422, f"'{body.phone}' is not a valid phone number")
        db.update("participants", pid, name=body.name.strip(), phone=phone, language=body.language,
                  segment=body.segment.strip(), fields=json.dumps(body.fields), can_call=int(body.can_call))
        return person_out(get_or_404("participants", pid))

    @r.delete("/participants/{pid}", status_code=204)
    def erase_participant(pid: int):
        """Right to erasure: removes the person, their call records and attempts."""
        get_or_404("participants", pid)
        db.x("DELETE FROM participants WHERE id=?", (pid,))

    # ------------------------------------------------------------------ campaigns
    @r.get("/events/{event_id}/campaigns")
    def list_campaigns(event_id: int):
        get_or_404("events", event_id)
        return [campaign_out(c) for c in db.q("SELECT * FROM campaigns WHERE event_id=? ORDER BY id DESC", (event_id,))]

    @r.post("/events/{event_id}/campaigns", status_code=201)
    def create_campaign(event_id: int, body: CampaignIn):
        ev = get_or_404("events", event_id)
        if body.purpose not in PURPOSES or body.language not in LANGUAGES:
            raise HTTPException(422, "Unknown purpose or language")
        tpl = body.template.strip() or default_template(ev["type"], body.purpose, body.language)
        cid = db.insert("campaigns", event_id=event_id, name=body.name.strip(), purpose=body.purpose,
                        language=body.language, template=tpl, max_attempts=body.max_attempts,
                        auto_retry=int(body.auto_retry), retry_interval_min=body.retry_interval_min, created_at=now())
        if body.add_all:
            engine.add_members(cid, [p["id"] for p in db.q("SELECT id FROM participants WHERE event_id=?", (event_id,))])
        return campaign_out(get_or_404("campaigns", cid))

    @r.get("/campaigns/{cid}")
    def get_campaign(cid: int):
        return campaign_out(get_or_404("campaigns", cid), with_calls=True)

    @r.patch("/campaigns/{cid}")
    def update_campaign(cid: int, body: CampaignIn):
        get_or_404("campaigns", cid)
        if not body.template.strip():
            raise HTTPException(422, "The call message cannot be empty")
        db.update("campaigns", cid, name=body.name.strip(), purpose=body.purpose, language=body.language,
                  template=body.template.strip(), max_attempts=body.max_attempts,
                  auto_retry=int(body.auto_retry), retry_interval_min=body.retry_interval_min)
        return campaign_out(get_or_404("campaigns", cid))

    @r.delete("/campaigns/{cid}", status_code=204)
    def delete_campaign(cid: int):
        get_or_404("campaigns", cid)
        if engine.is_active(cid):
            raise HTTPException(409, "Pause the campaign first")
        db.x("DELETE FROM campaigns WHERE id=?", (cid,))

    def _engine_call(fn, *a):
        try:
            return fn(*a)
        except CampaignError as exc:
            raise HTTPException(400, str(exc))

    @r.post("/campaigns/{cid}/launch")
    def launch(cid: int):
        get_or_404("campaigns", cid)
        return _engine_call(engine.launch, cid)

    @r.post("/campaigns/{cid}/pause")
    def pause(cid: int):
        get_or_404("campaigns", cid)
        engine.pause(cid)
        return {"ok": True}

    @r.post("/campaigns/{cid}/retry")
    def retry(cid: int):
        get_or_404("campaigns", cid)
        return _engine_call(engine.retry_non_responders, cid)

    @r.post("/calls/{call_id}/redial")
    def redial(call_id: int):
        get_or_404("calls", call_id)
        _engine_call(engine.redial, call_id)
        return {"ok": True}

    # ---- who is in a campaign, and what each person hears in it
    @r.post("/campaigns/{cid}/members")
    def add_members(cid: int, body: MembersIn):
        camp = get_or_404("campaigns", cid)
        ids = list(body.participant_ids)
        if body.everyone:
            ids += [p["id"] for p in db.q("SELECT id FROM participants WHERE event_id=?", (camp["event_id"],))]
        if body.segment:
            ids += [p["id"] for p in db.q("SELECT id FROM participants WHERE event_id=? AND segment=?", (camp["event_id"], body.segment))]
        if not ids:
            raise HTTPException(422, "Choose at least one person")
        return engine.add_members(cid, ids, body.message)

    @r.post("/campaigns/{cid}/people", status_code=201)
    def add_new_person(cid: int, body: CampaignPersonIn):
        """Create a person on the event's list and put them straight into this campaign."""
        camp = get_or_404("campaigns", cid)
        p = _add_person(camp["event_id"], body, reuse=True)
        res = engine.add_members(cid, [p["id"]], body.message)
        if not res["added"]:
            raise HTTPException(409, "That person is already in this campaign, has opted out, or is marked as not OK to call")
        return person_out(p)

    @r.post("/campaigns/{cid}/import")
    def import_into_campaign(cid: int, body: ImportIn):
        camp = get_or_404("campaigns", cid)
        return _import(camp["event_id"], body.csv, cid)

    @r.patch("/calls/{call_id}")
    def set_call_message(call_id: int, body: CallMessageIn):
        call = get_or_404("calls", call_id)
        if call["status"] in ("dialing", "in_progress"):
            raise HTTPException(409, "A call to this person is in progress")
        db.update("calls", call_id, custom_message=body.message.strip())
        return {"ok": True}

    @r.delete("/calls/{call_id}", status_code=204)
    def remove_member(call_id: int):
        call = get_or_404("calls", call_id)
        if call["status"] != "pending":
            raise HTTPException(409, "Only people who have not been called yet can be removed from a campaign")
        db.x("DELETE FROM calls WHERE id=?", (call_id,))

    @r.post("/campaigns/{cid}/preview")
    def preview(cid: int, body: PreviewIn):
        """What a person will hear. Uses the unsaved template from the editor when supplied."""
        camp = get_or_404("campaigns", cid)
        ev = get_or_404("events", camp["event_id"])
        camp = {**camp, **{k: v for k, v in body.model_dump().items() if k in ("template", "purpose", "language") and v}}
        if body.participant_id:
            p = get_or_404("participants", body.participant_id)
        else:
            p = db.one("SELECT * FROM participants WHERE event_id=? ORDER BY id LIMIT 1", (ev["id"],)) or {
                "name": "Priya Sharma", "fields": "{}"}
        p = {**p, "fields": loads(p["fields"]) if isinstance(p.get("fields"), str) else p.get("fields", {})}
        if body.message is not None:
            p["custom_message"] = body.message
        else:
            link = db.one("SELECT custom_message FROM calls WHERE campaign_id=? AND participant_id=?", (cid, p.get("id", -1)))
            p["custom_message"] = link["custom_message"] if link else ""
        text, lang, missing = compose(camp, ev, p)
        return {"text": text, "language": lang, "missing": missing, "participant": p.get("name", "")}

    @r.get("/campaigns/{cid}/export.csv", response_class=PlainTextResponse)
    def export(cid: int):
        get_or_404("campaigns", cid)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["name", "phone", "segment", "language", "outcome", "rsvp", "attempts", "needs_review", "callback_hint"])
        rsvp = {p["id"]: p["rsvp"] for p in db.q("SELECT id, rsvp FROM participants")}
        for c in calls_for(cid):
            w.writerow([c["participant_name"], c["phone"], c["segment"], c["language"], OUTCOME_LABELS[c["outcome"]], rsvp.get(c["participant_id"], ""),
                        c["attempts"], "yes" if c["needs_review"] else "", c["time_hint"] or c["requested_time"] or ""])
        return PlainTextResponse(buf.getvalue(), headers={
            "Content-Disposition": f'attachment; filename="campaign-{cid}-results.csv"'})

    # ------------------------------------------------------------------ settings
    @r.get("/settings")
    def get_settings():
        h = engine.get_hours()
        return {"calling_hours": h, "now_local": engine.local_now().strftime("%H:%M"), "timezone": "IST (UTC+5:30)",
                "simulated": engine.provider.is_simulated,
                "allowed_to_call_now": (not h["enabled"]) or h["start"] <= engine.local_now().strftime("%H:%M") <= h["end"]}

    @r.put("/settings/calling-hours")
    def put_hours(body: HoursIn):
        try:
            engine.set_hours(body.enabled, body.start, body.end)
        except CampaignError as exc:
            raise HTTPException(422, str(exc))
        return get_settings()

    # ------------------------------------------------------------------ follow-up tasks
    @r.get("/tasks")
    def list_tasks(status: str = "open", event_id: int | None = None):
        sql = ("SELECT t.*, p.name AS participant_name, p.phone, p.rsvp, e.name AS event_name, c.name AS campaign_name "
               "FROM tasks t JOIN participants p ON p.id=t.participant_id JOIN events e ON e.id=t.event_id "
               "LEFT JOIN campaigns c ON c.id=t.campaign_id WHERE t.status=?")
        args: list = [status if status in ("open", "done") else "open"]
        if event_id:
            sql += " AND t.event_id=?"
            args.append(event_id)
        return db.q(sql + " ORDER BY t.id DESC", tuple(args))

    @r.patch("/tasks/{task_id}")
    def update_task(task_id: int, body: TaskIn):
        get_or_404("tasks", task_id)
        if body.status not in ("open", "done"):
            raise HTTPException(422, "Status must be open or done")
        if body.rsvp not in (None, "attending", "not_attending"):
            raise HTTPException(422, "RSVP must be attending or not_attending")
        t = get_or_404("tasks", task_id)
        if body.rsvp:
            db.update("participants", t["participant_id"], rsvp=body.rsvp, rsvp_at=now(), rsvp_campaign_id=t["campaign_id"])
        db.update("tasks", task_id, status=body.status, note=body.note.strip(), done_at=now() if body.status == "done" else None)
        return get_or_404("tasks", task_id)

    # ------------------------------------------------------------------ overview
    @r.get("/overview")
    def overview():
        campaigns = db.q("SELECT c.*, e.name AS event_name FROM campaigns c JOIN events e ON e.id=c.event_id ORDER BY c.id DESC")
        by_campaign, all_calls, by_lang, by_seg = [], [], {}, {}
        for c in campaigns:
            calls = calls_for(c["id"])
            all_calls += calls
            s = summarize(calls)
            by_campaign.append({"id": c["id"], "event_id": c["event_id"], "name": c["name"], "event_name": c["event_name"],
                                "state": engine.campaign_state(c, s), "summary": s})
            for call in calls:
                by_lang.setdefault(call["language"], []).append(call)
                by_seg.setdefault(call["segment"] or "No segment", []).append(call)
        return {
            "events": db.one("SELECT COUNT(*) n FROM events")["n"],
            "campaigns": len(campaigns),
            "participants": db.one("SELECT COUNT(*) n FROM participants")["n"],
            "opted_out": db.one("SELECT COUNT(*) n FROM participants WHERE opted_out=1")["n"],
            "open_tasks": db.one("SELECT COUNT(*) n FROM tasks WHERE status='open'")["n"],
            "rsvp": {k: db.one("SELECT COUNT(*) n FROM participants WHERE rsvp=?", (k,))["n"] for k in ("attending", "not_attending", "undecided")},
            "totals": summarize(all_calls),
            "needs_review": sum(1 for c in all_calls if c["needs_review"]),
            "by_campaign": by_campaign,
            "by_language": [{"key": k, "label": LANGUAGES.get(k, k), "summary": summarize(v)} for k, v in sorted(by_lang.items())],
            "by_segment": [{"key": k, "label": k, "summary": summarize(v)} for k, v in sorted(by_seg.items())]}

    return r


class MembersIn(BaseModel):
    participant_ids: list[int] = []
    segment: str | None = None                  # add everyone in this segment
    everyone: bool = False
    message: str = Field(default="", max_length=1000)


class CallMessageIn(BaseModel):
    message: str = Field(default="", max_length=1000)


class HoursIn(BaseModel):
    enabled: bool
    start: str = "09:00"
    end: str = "21:00"


class TaskIn(BaseModel):
    rsvp: str | None = None                     # what the person told a human: attending | not_attending
    status: str = "done"
    note: str = Field(default="", max_length=500)
