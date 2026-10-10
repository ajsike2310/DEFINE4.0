"""API for the React frontend (frontend/), served under /api/v2 as its own sub-application.

It speaks the shapes `frontend/src/services/api.ts` expects (events with approved facts, campaigns with per-language
messages, campaign-scoped recipients, attempts, intents, follow-ups, analytics, leads) and is a thin layer over the same
database and `Engine` as the original dashboard API in `api.py`, which it does not touch. A "recipient" is a person's place
in one campaign, so recipient ids are the ids of the `calls` rows.
"""
import csv
import hmac
import io
import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email.policy import default as email_default

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .db import Db, loads, now
from .messages import LANGUAGES
from .phone import normalize_phone
from .service import UNREACHED, CampaignError, Engine, outcome_of

SUPPORTED = ("en", "hi", "ta")
FINAL = ("confirmed", "declined", "opted_out", "acknowledged")


class ApiErr(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


# ------------------------------------------------------------------ request bodies
class EventIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    approved_info: dict[str, str] = {}
    organizer_contact: str | None = None


class EventPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    approved_info: dict[str, str] | None = None
    organizer_contact: str | None = None


class CampaignIn(BaseModel):
    event_id: int
    name: str = Field(min_length=2, max_length=120)
    purpose: str = "attendance_confirmation"
    messages: dict[str, str]
    languages: list[str] = Field(min_length=1)
    max_attempts: int = Field(default=3, ge=1, le=5)
    require_consent: bool = True
    scheduled_at: str | None = None
    auto_retry: bool | None = None
    retry_interval_min: int | None = Field(default=None, ge=0, le=1440)


class CampaignPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    max_attempts: int | None = Field(default=None, ge=1, le=5)
    messages: dict[str, str] | None = None
    auto_retry: bool | None = None
    retry_interval_min: int | None = Field(default=None, ge=0, le=1440)


class RecipientIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str
    external_ref: str | None = None
    preferred_language: str | None = None
    consent_status: str = "unknown"
    segment: str | None = None
    message: str = Field(default="", max_length=1000)         # this person's own message in this campaign


class RecipientPatch(BaseModel):
    message: str | None = Field(default=None, max_length=1000)
    preferred_language: str | None = None


class ScheduleIn(BaseModel):
    scheduled_at: str


class FollowupPatch(BaseModel):
    status: str | None = None
    scheduled_at: str | None = None


class DuplicateIn(BaseModel):
    name: str | None = None
    copy_participants: bool = False


class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str
    email: str | None = None
    source: str = "manual"
    interest: str | None = None
    preferred_language: str | None = None
    consent_status: str = "unknown"
    notes: str = ""


class LeadPatch(BaseModel):
    status: str | None = None
    notes: str | None = None
    consent_status: str | None = None


class ConvertIn(BaseModel):
    campaign_id: int
    lead_ids: list[int]


class VoicemailIn(BaseModel):
    leave_message: bool


class HoursIn(BaseModel):
    enabled: bool
    start: str = "09:00"
    end: str = "21:00"


# ------------------------------------------------------------------ multipart without python-multipart
async def read_multipart(request: Request) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    """Fields and files of a multipart/form-data body, using only the standard library."""
    ctype = request.headers.get("content-type", "")
    if "multipart/form-data" not in ctype:
        raise ApiErr(400, "bad_request", "Expected a file upload")
    body = await request.body()
    msg = BytesParser(policy=email_default).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body)
    fields, files = {}, {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename is not None:
            files[name] = (filename, payload)
        else:
            fields[name] = payload.decode("utf-8", "replace")
    return fields, files


def parse_csv(raw: bytes) -> list[dict[str, str]]:
    text = raw.decode("utf-8-sig", "replace")
    head = text.split("\n", 1)[0]
    try:
        dialect = csv.Sniffer().sniff(head, ",;\t")
    except csv.Error:
        dialect = csv.excel
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k}
            for row in csv.DictReader(io.StringIO(text), dialect=dialect)]


def yes(v: str | None) -> bool:
    return (v or "").strip().lower() in ("yes", "y", "true", "1")


def sample_numbers(i: int) -> str:
    return f"+1555010{i:04d}"


def build_v2(db: Db, engine: Engine, settings, require_auth) -> FastAPI:
    app = FastAPI(title="Cadence API v2", docs_url=None, redoc_url=None, openapi_url=None,
                  dependencies=[Depends(require_auth)])

    @app.exception_handler(ApiErr)
    async def _api_err(_: Request, exc: ApiErr):
        body = {"error": {"code": exc.code, "message": exc.message}}
        if exc.details:
            body["error"]["details"] = exc.details
        return JSONResponse(body, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(x) for x in e["loc"][1:]) or "body", "message": e["msg"].removeprefix("Value error, ")}
                   for e in exc.errors()]
        return JSONResponse({"error": {"code": "validation_error", "message": "; ".join(f"{d['field']}: {d['message']}" for d in details),
                                       "details": details}}, status_code=422)

    from fastapi import HTTPException as _HTTP

    @app.exception_handler(_HTTP)
    async def _http(_: Request, exc: _HTTP):
        return JSONResponse({"error": {"code": "http_error", "message": str(exc.detail)}}, status_code=exc.status_code)

    def row(table: str, rid: int, what: str) -> dict:
        r = db.one(f"SELECT * FROM {table} WHERE id=?", (rid,))
        if not r:
            raise ApiErr(404, "not_found", f"{what} not found")
        return r

    def engine_do(fn, *a):
        try:
            return fn(*a)
        except CampaignError as exc:
            raise ApiErr(409, "conflict", str(exc))

    def iso_future(s: str) -> str:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            raise ApiErr(422, "validation_error", "scheduled_at must be an ISO date-time")
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat(timespec="seconds")

    # ================================================================== mappers
    def event_out(e: dict) -> dict:
        info = loads(e.get("approved_info"))
        if e.get("venue") and "venue" not in info:
            info["venue"] = e["venue"]
        return {"id": e["id"], "name": e["name"], "description": e["description"] or "", "approved_info": info,
                "organizer_contact": e.get("organizer_contact"), "is_demo": bool(e.get("is_demo")),
                "campaign_count": db.one("SELECT COUNT(*) n FROM campaigns WHERE event_id=?", (e["id"],))["n"],
                "created_at": e["created_at"], "updated_at": e["created_at"]}

    def ui_status(c: dict, state: str) -> str:
        if c["status"] == "cancelled":
            return "cancelled"
        if c["scheduled_at"] and c["status"] in ("draft", "paused"):
            return "scheduled"
        if c["status"] in ("draft", "paused") or state in ("draft",):
            return "draft"
        return "completed" if state == "completed" else "running"

    def camp_calls(cid: int) -> list[dict]:
        return db.q("SELECT c.*, p.opted_out, p.can_call FROM calls c JOIN participants p ON p.id=c.participant_id WHERE c.campaign_id=?", (cid,))

    def campaign_out(c: dict) -> dict:
        calls = camp_calls(c["id"])
        msgs = loads(c.get("messages")) or {c["language"]: c["template"]}
        return {"id": c["id"], "event_id": c["event_id"], "name": c["name"], "purpose": c["purpose"], "messages": msgs,
                "languages": list(msgs), "status": ui_status(c, engine.state_of(c, calls)), "scheduled_at": c["scheduled_at"],
                "max_attempts": c["max_attempts"], "require_consent": bool(c["require_consent"]), "is_demo": bool(c["is_demo"]),
                "created_at": c["created_at"], "updated_at": c["created_at"], "recipient_count": len(calls),
                "auto_retry": bool(c["auto_retry"]), "retry_interval_min": c["retry_interval_min"]}

    def consent_of(p: dict) -> str:
        if p["opted_out"]:
            return "revoked"
        return "granted" if p["can_call"] else (p.get("consent_status") or "unknown")

    def ui_outcome(call: dict) -> str:
        o = outcome_of(call)
        return {"unclear": "unclear", "needs_review": "unclear", "no_answer": "no_response", "busy": "no_response",
                "voicemail": "no_response", "failed": "no_response", "in_progress": "pending"}.get(o, o)

    def recipient_out(call: dict, p: dict | None = None, camp: dict | None = None) -> dict:
        p = p or row("participants", call["participant_id"], "Participant")
        camp = camp or row("campaigns", call["campaign_id"], "Campaign")
        return {"id": call["id"], "campaign_id": call["campaign_id"], "external_ref": p.get("external_ref"), "name": p["name"],
                "phone": p["phone"], "preferred_language": p["language"] or None, "segment": p["segment"] or None,
                "consent_status": consent_of(p), "opted_out": bool(p["opted_out"]), "outcome": ui_outcome(call),
                "is_demo": bool(camp["is_demo"]), "created_at": p["created_at"], "message": call.get("custom_message") or "",
                "attempts": call["attempts"], "next_attempt_at": call.get("next_attempt_at"),
                "rsvp": p.get("rsvp") or "", "can_call": bool(p["can_call"]), "error": call.get("error") or ""}

    def recipients_for(where: str, args: tuple) -> list[dict]:
        rows = db.q("SELECT c.*, p.name AS _n FROM calls c JOIN participants p ON p.id=c.participant_id "
                    f"JOIN campaigns k ON k.id=c.campaign_id WHERE {where} ORDER BY c.id DESC", args)
        people = {p["id"]: p for p in db.q("SELECT * FROM participants")}
        camps = {c["id"]: c for c in db.q("SELECT * FROM campaigns")}
        return [recipient_out(c, people[c["participant_id"]], camps[c["campaign_id"]]) for c in rows]

    ATTEMPT_STATUS = {"dialing": "ringing"}

    def attempts_for(cid: int | None = None, call_id: int | None = None) -> list[dict]:
        where, args = ("a.call_id=?", (call_id,)) if call_id else ("c.campaign_id=?", (cid,))
        out = []
        for a in db.q("SELECT a.*, c.campaign_id, c.participant_id, c.next_attempt_at, c.error, c.language_detected, c.attempts AS total "
                      f"FROM attempts a JOIN calls c ON c.id=a.call_id WHERE {where} ORDER BY a.id", args):
            camp = db.one("SELECT * FROM campaigns WHERE id=?", (a["campaign_id"],))
            p = db.one("SELECT language FROM participants WHERE id=?", (a["participant_id"],))
            sim = engine.provider_for(camp).is_simulated
            out.append({"id": a["id"], "campaign_id": a["campaign_id"], "recipient_id": a["call_id"], "provider": engine.provider_for(camp).name,
                        "is_simulated": sim, "provider_call_id": a["provider_call_id"], "attempt_number": a["number"], "mode": "main",
                        "call_language": (p and p["language"]) or camp["language"],
                        "status": ATTEMPT_STATUS.get(a["status"], a["status"]), "started_at": a["started_at"],
                        "answered_at": a["ended_at"] if a["status"] == "completed" else None, "completed_at": a["ended_at"],
                        "failure_reason": (a["error"] or None) if a["status"] == "failed" else None,
                        "next_retry_at": a["next_attempt_at"] if a["number"] == a["total"] else None})
        return out

    def intents_for(where: str, args: tuple) -> list[dict]:
        return [{"id": i["id"], "call_attempt_id": i["call_attempt_id"], "recipient_id": i["call_id"], "campaign_id": i["campaign_id"],
                 "intent": i["intent"], "score": i["score"], "method": i["method"] or "none", "detected_language": i["detected_language"] or "unknown",
                 "evidence": "", "notes": json.loads(i["notes"] or "[]"), "needs_review": bool(i["needs_review"]),
                 "next_action": i["next_action"] or "", "processing_status": "processed", "created_at": i["created_at"]}
                for i in db.q(f"SELECT * FROM intents WHERE {where} ORDER BY id", args)]

    ACTION = {"in_person_call": "human_review", "callback": "callback", "answer_question": "send_information"}

    def ui_task_status(t: dict) -> str:
        if t["status"] == "done":
            return "completed"
        if t["status"] == "cancelled":
            return "cancelled"
        return "scheduled" if t.get("scheduled_at") else "pending"

    def call_of(t: dict) -> dict | None:
        return db.one("SELECT * FROM calls WHERE campaign_id=? AND participant_id=?", (t["campaign_id"], t["participant_id"]))

    def followup_out(t: dict) -> dict:
        call = call_of(t)
        note = (t["reason"] or "") + (f" {t['note']}" if t.get("note") else "")
        return {"id": t["id"], "campaign_id": t["campaign_id"], "recipient_id": call["id"] if call else 0,
                "action_type": ACTION.get(t["kind"], "human_review"), "status": ui_task_status(t), "scheduled_at": t.get("scheduled_at"),
                "note": note.strip(), "created_at": t["created_at"], "completed_at": t["done_at"]}

    def queue_item(t: dict) -> dict:
        call = call_of(t) or {}
        p = row("participants", t["participant_id"], "Participant")
        camp = row("campaigns", t["campaign_id"], "Campaign")
        prio, why, rec = {
            "callback": (2, "callback requested; time not confirmed", "Call the participant back at their requested time, then mark complete."),
            "answer_question": (3, "asked a question you can answer", "Send them the answer, then mark complete."),
            "in_person_call": (1, "answer unclear or not reached; only a person can settle it", "Call or meet the participant to confirm, then mark complete."),
        }[t["kind"]] if t["kind"] in ACTION else (2, "needs a person", "Contact the participant, then mark complete.")
        return {"followup_id": t["id"], "campaign_id": t["campaign_id"], "campaign_name": camp["name"], "event_id": t["event_id"],
                "recipient_id": call.get("id", 0), "participant_name": p["name"], "participant_ref": p.get("external_ref"),
                "participant_phone": p["phone"], "reason": (t["reason"] or "").split(".")[0].lower() or ACTION.get(t["kind"], "follow-up"),
                "action_type": ACTION.get(t["kind"], "human_review"), "status": ui_task_status(t), "priority": prio, "priority_reason": why,
                "latest_outcome": ui_outcome(call) if call else "pending", "recommended_action": rec, "can_clarify": False,
                "clarification_attempted": False, "scheduled_at": t.get("scheduled_at"), "note": t["reason"] or "",
                "is_simulated": bool(camp["is_demo"]) or engine.provider.is_simulated, "created_at": t["created_at"]}

    # ================================================================== settings / status
    @app.get("/settings")
    def get_settings():
        return {"provider": engine.provider.name, "purposes": ["attendance_confirmation", "event_announcement", "participant_followup",
                                                                 "schedule_venue_update", "submission_deadline_reminder"],
                "exotel_configured": bool(settings.exotel_account_sid and settings.exotel_api_key and settings.exotel_api_token),
                "languages": [{"code": c, "name": LANGUAGES[c], "support": "rule-based phrase matching; not native-reviewed; experimental"}
                              for c in SUPPORTED],
                "retry_policy": {"max_attempts_default": settings.max_attempts, "backoff_minutes": 30,
                                 "retry_on": ["failed", "busy", "no_answer", "voicemail", "no response"]},
                "data_location": "Local SQLite file on the machine running this server. Call audio is processed live and never stored.",
                "transcription": "ElevenLabs Scribe, live during the call only; transcripts are not saved",
                "calling_hours": engine.get_hours(), "voicemail": engine.get_voicemail(),
                "now_local": engine.local_now().strftime("%H:%M"), "timezone": "IST (UTC+5:30)"}

    @app.put("/settings/calling-hours")
    def put_hours(body: HoursIn):
        engine_do(engine.set_hours, body.enabled, body.start, body.end)
        return get_settings()

    @app.put("/settings/voicemail")
    def put_voicemail(body: VoicemailIn):
        engine.set_voicemail(body.leave_message)
        return get_settings()

    @app.get("/settings/exotel-readiness")
    def exotel_readiness():
        checks = [{"name": n, "ok": bool(getattr(settings, a)), "required": req}
                  for n, a, req in (("EXOTEL_ACCOUNT_SID", "exotel_account_sid", True), ("EXOTEL_API_KEY", "exotel_api_key", True),
                                    ("EXOTEL_API_TOKEN", "exotel_api_token", True), ("EXOTEL_CALLER_ID", "exotel_caller_id", True),
                                    ("EXOTEL_STREAM_URL", "exotel_stream_url", True), ("EXOTEL_WEBHOOK_TOKEN", "exotel_webhook_token", True),
                                    ("PUBLIC_BASE_URL", "public_base_url", False))]
        cb = f"{settings.public_base_url.rstrip('/')}/api/webhooks/exotel" if settings.public_base_url else None
        return {"ready": all(c["ok"] for c in checks if c["required"]) and not engine.provider.is_simulated, "checks": checks,
                "urls": {"status_callback": cb, "passthru_response": None},
                "note": "Live calls use Exotel's streaming API with the audio server on STREAM_PORT. Status callbacks are optional: "
                        "without PUBLIC_BASE_URL the dashboard polls Exotel instead."}

    @app.get("/voice/status")
    def voice_status():
        return {"configured": False, "voice_id": os.getenv("ELEVENLABS_VOICE_ID", ""),
                "tts_model": os.getenv("ELEVENLABS_TTS_MODEL", ""), "stt_model": os.getenv("ELEVENLABS_STT_MODEL", ""),
                "note": "The in-browser practice call is not part of this build. Real phone calls use the live voice agent."}

    def no_browser():
        raise ApiErr(501, "not_available", "In-browser practice calls are not available in this build.")

    for path in ("/campaigns/{cid}/recipients/{rid}/browser-call", "/browser-calls/{aid}/speak", "/browser-calls/{aid}/speak-reply",
                 "/browser-calls/{aid}/respond", "/browser-calls/{aid}/respond-audio", "/browser-calls/{aid}/hangup"):
        app.post(path)(no_browser)

    # ================================================================== events
    def event_values(approved: dict[str, str] | None, contact: str | None) -> dict:
        info = {k: v.strip() for k, v in (approved or {}).items() if v and v.strip()}
        return {"approved_info": json.dumps(info), "venue": info.get("venue", ""), "organizer_contact": contact or None,
                "organiser": contact or ""}

    @app.get("/events")
    def list_events():
        return [event_out(e) for e in db.q("SELECT * FROM events ORDER BY id")]

    @app.get("/events/{eid}")
    def get_event(eid: int):
        return event_out(row("events", eid, "Event"))

    @app.post("/events", status_code=201)
    def create_event(body: EventIn):
        eid = db.insert("events", name=body.name.strip(), type="custom", mode="in_person", description=body.description,
                        created_at=now(), **event_values(body.approved_info, body.organizer_contact))
        return event_out(row("events", eid, "Event"))

    @app.patch("/events/{eid}")
    def patch_event(eid: int, body: EventPatch):
        e = row("events", eid, "Event")
        vals = {}
        if body.name is not None:
            vals["name"] = body.name.strip()
        if body.description is not None:
            vals["description"] = body.description
        if body.approved_info is not None or body.organizer_contact is not None:
            vals.update(event_values(body.approved_info if body.approved_info is not None else loads(e["approved_info"]),
                                     body.organizer_contact if body.organizer_contact is not None else e["organizer_contact"]))
        db.update("events", eid, **vals)
        return event_out(row("events", eid, "Event"))

    # ================================================================== campaigns
    def check_campaign(b: CampaignIn | CampaignPatch, languages: list[str] | None = None) -> None:
        msgs = b.messages or {}
        langs = languages if languages is not None else list(msgs)
        bad = [l for l in langs if l not in SUPPORTED]
        if bad:
            raise ApiErr(422, "validation_error", f"Language not supported yet: {', '.join(bad)}. Supported: English, Hindi, Tamil.",
                         [{"field": "languages", "message": f"unsupported: {', '.join(bad)}"}])
        for l in langs:
            if l in msgs and not msgs[l].strip():
                raise ApiErr(422, "validation_error", f"The message for {LANGUAGES.get(l, l)} cannot be empty.",
                             [{"field": f"messages.{l}", "message": "required"}])
        if isinstance(b, CampaignIn):
            for l in b.languages:
                if not (msgs.get(l) or "").strip():
                    raise ApiErr(422, "validation_error", f"Write a message for {LANGUAGES.get(l, l)}.",
                                 [{"field": f"messages.{l}", "message": "required"}])

    @app.get("/campaigns/overview")
    def campaign_overview(event_id: int | None = None):
        camps = db.q("SELECT * FROM campaigns" + (" WHERE event_id=?" if event_id else "") + " ORDER BY id DESC", (event_id,) if event_id else ())
        rows, by_status = [], {}
        for c in camps:
            co = campaign_out(c)
            calls = camp_calls(c["id"])
            outs = [ui_outcome(x) for x in calls]
            n = len(calls)
            resolved = sum(1 for o in outs if o in FINAL)
            attention = sum(1 for x, o in zip(calls, outs) if o in ("unclear", "human_required", "callback_requested", "information_requested", "no_response")
                            and not x["opted_out"])
            retry = sum(1 for x in calls if x["status"] in UNREACHED and x["attempts"] < c["max_attempts"] and not x["opted_out"] and x["can_call"])
            missing = sum(1 for x in calls if not x["can_call"] and not x["opted_out"])
            if n == 0:
                nxt = "Add participants"
            elif co["status"] in ("draft", "scheduled"):
                nxt = "Ready to launch" if not missing else f"{missing} without consent will be skipped"
            elif attention:
                nxt = f"{attention} need follow-up"
            elif retry:
                nxt = f"{retry} retry eligible"
            else:
                nxt = "All resolved" if resolved == n else "In progress"
            by_status[co["status"]] = by_status.get(co["status"], 0) + 1
            rows.append({"campaign_id": c["id"], "event_id": c["event_id"], "name": c["name"], "purpose": c["purpose"], "status": co["status"],
                         "is_demo": bool(c["is_demo"]), "participants": n,
                         "contacted": sum(1 for x in calls if x["attempts"] > 0), "resolved": resolved, "needs_attention": attention,
                         "retry_eligible": retry, "missing_consent": missing, "progress": (resolved / n) if n else None,
                         "next_step": nxt, "created_at": c["created_at"]})
        return {"by_status": by_status, "campaigns": rows,
                "totals": {"participants": sum(r["participants"] for r in rows), "needs_attention": sum(r["needs_attention"] for r in rows),
                           "retry_eligible": sum(r["retry_eligible"] for r in rows)}}

    @app.get("/campaigns")
    def list_campaigns(event_id: int | None = None):
        sql, args = ("SELECT * FROM campaigns WHERE event_id=? ORDER BY id DESC", (event_id,)) if event_id else ("SELECT * FROM campaigns ORDER BY id DESC", ())
        return [campaign_out(c) for c in db.q(sql, args)]

    @app.get("/campaigns/{cid}")
    def get_campaign(cid: int):
        return campaign_out(row("campaigns", cid, "Campaign"))

    def insert_campaign(b: CampaignIn, *, is_demo: bool = False) -> int:
        row("events", b.event_id, "Event")
        check_campaign(b, b.languages)
        msgs = {l: b.messages[l].strip() for l in b.languages}
        first = b.languages[0]
        retry_min = b.retry_interval_min if b.retry_interval_min is not None else 30
        return db.insert("campaigns", event_id=b.event_id, name=b.name.strip(), purpose=b.purpose, language=first, template=msgs[first],
                         messages=json.dumps(msgs, ensure_ascii=False), max_attempts=b.max_attempts, require_consent=int(b.require_consent),
                         scheduled_at=iso_future(b.scheduled_at) if b.scheduled_at else None, is_demo=int(is_demo),
                         auto_retry=int(b.auto_retry if b.auto_retry is not None else True), retry_interval_min=retry_min, created_at=now())

    @app.post("/campaigns", status_code=201)
    def create_campaign(body: CampaignIn):
        return campaign_out(row("campaigns", insert_campaign(body), "Campaign"))

    @app.patch("/campaigns/{cid}")
    def patch_campaign(cid: int, body: CampaignPatch):
        c = row("campaigns", cid, "Campaign")
        vals = {}
        if body.name is not None:
            vals["name"] = body.name.strip()
        if body.max_attempts is not None:
            vals["max_attempts"] = body.max_attempts
        if body.auto_retry is not None:
            vals["auto_retry"] = int(body.auto_retry)
        if body.retry_interval_min is not None:
            vals["retry_interval_min"] = body.retry_interval_min
        if body.messages is not None:
            msgs = loads(c["messages"]) or {c["language"]: c["template"]}
            check_campaign(body, list(body.messages))
            msgs.update({k: v.strip() for k, v in body.messages.items()})
            first = next(iter(msgs))
            vals.update(messages=json.dumps(msgs, ensure_ascii=False), language=first, template=msgs[first])
        db.update("campaigns", cid, **vals)
        return campaign_out(row("campaigns", cid, "Campaign"))

    @app.delete("/campaigns/{cid}")
    def delete_campaign(cid: int):
        row("campaigns", cid, "Campaign")
        if engine.is_active(cid):
            raise ApiErr(409, "conflict", "This campaign is running. Cancel it first.")
        db.x("DELETE FROM campaigns WHERE id=?", (cid,))
        return {"deleted": cid}

    @app.post("/campaigns/{cid}/cancel")
    def cancel_campaign(cid: int):
        row("campaigns", cid, "Campaign")
        engine.cancel(cid)
        return campaign_out(row("campaigns", cid, "Campaign"))

    @app.post("/campaigns/{cid}/schedule")
    def schedule_campaign(cid: int, body: ScheduleIn):
        c = row("campaigns", cid, "Campaign")
        if c["status"] not in ("draft", "paused"):
            raise ApiErr(409, "conflict", "Only a campaign that has not started can be scheduled.")
        at = iso_future(body.scheduled_at)
        if at <= now():
            raise ApiErr(422, "validation_error", "Choose a start time in the future.")
        db.update("campaigns", cid, scheduled_at=at)
        return campaign_out(row("campaigns", cid, "Campaign"))

    @app.post("/campaigns/{cid}/unschedule")
    def unschedule_campaign(cid: int):
        row("campaigns", cid, "Campaign")
        db.update("campaigns", cid, scheduled_at=None)
        return campaign_out(row("campaigns", cid, "Campaign"))

    @app.post("/campaigns/{cid}/start")
    def start_campaign(cid: int):
        c = row("campaigns", cid, "Campaign")
        if c["status"] == "cancelled":
            raise ApiErr(409, "conflict", "This campaign was cancelled.")
        calls = camp_calls(cid)
        skipped = [{"recipient_id": x["id"], "reason": "opted out" if x["opted_out"] else "consent not confirmed"}
                   for x in calls if x["opted_out"] or not x["can_call"]]
        ready = sum(1 for x in calls if x["status"] == "pending" and not x["opted_out"] and x["can_call"])
        if ready == 0:
            return {"dispatched": 0, "skipped": skipped}
        engine_do(engine.launch, cid)
        db.update("campaigns", cid, scheduled_at=None)
        return {"dispatched": ready, "skipped": skipped}

    @app.post("/campaigns/{cid}/retry-due")
    def retry_due(cid: int, force: bool = False):
        row("campaigns", cid, "Campaign")
        return {"dispatched": engine_do(engine.retry_due, cid, force)}

    @app.post("/campaigns/{cid}/clarify")
    def clarify_campaign(cid: int):
        row("campaigns", cid, "Campaign")
        return {"dispatched": 0, "skipped": [{"reason": "The voice agent already asks once on the call when an answer is unclear; "
                                                       "anything still unclear becomes a follow-up task."}]}

    @app.post("/recipients/{rid}/clarify")
    def clarify_recipient(rid: int):
        row("calls", rid, "Recipient")
        return {"dispatched": 0, "skipped": [{"reason": "The voice agent already asks once on the call; see Follow-ups."}]}

    @app.post("/campaigns/{cid}/duplicate")
    def duplicate_campaign(cid: int, body: DuplicateIn):
        c = row("campaigns", cid, "Campaign")
        msgs = loads(c["messages"]) or {c["language"]: c["template"]}
        new_id = insert_campaign(CampaignIn(event_id=c["event_id"], name=body.name or f"{c['name']} (copy)", purpose=c["purpose"], messages=msgs,
                                            languages=list(msgs), max_attempts=c["max_attempts"], require_consent=bool(c["require_consent"]),
                                            auto_retry=bool(c["auto_retry"]), retry_interval_min=c["retry_interval_min"]), is_demo=bool(c["is_demo"]))
        copied = skipped = 0
        if body.copy_participants:
            copied, skipped = copy_people(cid, new_id)
        return {"campaign": campaign_out(row("campaigns", new_id, "Campaign")), "copied": copied, "skipped": skipped}

    def copy_people(src: int, dst: int) -> tuple[int, int]:
        ids = [x["participant_id"] for x in db.q("SELECT participant_id FROM calls WHERE campaign_id=?", (src,))]
        res = engine.add_members(dst, ids)
        return res["added"], res["skipped"]

    @app.post("/campaigns/{cid}/recipients/copy-from/{src}")
    def copy_from(cid: int, src: int):
        a, b = row("campaigns", cid, "Campaign"), row("campaigns", src, "Source campaign")
        if a["event_id"] != b["event_id"]:
            raise ApiErr(422, "validation_error", "Participants can only be reused within the same event.")
        copied, skipped = copy_people(src, cid)
        return {"copied": copied, "skipped": skipped}

    # ---- recipients of a campaign
    def person_values(b: RecipientIn) -> dict:
        phone = normalize_phone(b.phone)
        if not phone:
            raise ApiErr(422, "validation_error", f"'{b.phone}' is not a valid phone number.", [{"field": "phone", "message": "invalid phone number"}])
        lang = b.preferred_language or ""
        if lang and lang not in SUPPORTED:
            raise ApiErr(422, "validation_error", f"Language not supported: {lang}", [{"field": "preferred_language", "message": "unsupported"}])
        granted = b.consent_status == "granted"
        return {"name": b.name.strip(), "phone": phone, "language": lang, "segment": b.segment or "", "external_ref": b.external_ref,
                "can_call": int(granted), "consent_status": b.consent_status if not granted else "granted", "fields": "{}"}

    def upsert_person(event_id: int, vals: dict) -> dict:
        p = db.one("SELECT * FROM participants WHERE event_id=? AND phone=?", (event_id, vals["phone"]))
        if p:
            if vals["can_call"] and not p["can_call"]:
                db.update("participants", p["id"], can_call=1, consent_status="granted")
            return db.one("SELECT * FROM participants WHERE id=?", (p["id"],))
        pid = db.insert("participants", event_id=event_id, created_at=now(), **vals)
        return db.one("SELECT * FROM participants WHERE id=?", (pid,))

    def add_to_campaign(c: dict, p: dict, message: str = "") -> dict:
        existing = db.one("SELECT * FROM calls WHERE campaign_id=? AND participant_id=?", (c["id"], p["id"]))
        if existing:
            raise ApiErr(409, "conflict", f"{p['phone']} is already in this campaign.")
        cid = db.insert("calls", campaign_id=c["id"], participant_id=p["id"], custom_message=message.strip(), updated_at=now())
        return db.one("SELECT * FROM calls WHERE id=?", (cid,))

    @app.get("/campaigns/{cid}/recipients")
    def campaign_recipients(cid: int):
        row("campaigns", cid, "Campaign")
        return list(reversed(recipients_for("c.campaign_id=?", (cid,))))

    @app.post("/campaigns/{cid}/recipients", status_code=201)
    def add_recipient(cid: int, body: RecipientIn):
        c = row("campaigns", cid, "Campaign")
        p = upsert_person(c["event_id"], person_values(body))
        call = add_to_campaign(c, p, body.message)
        return recipient_out(call, p, c)

    @app.post("/campaigns/{cid}/recipients/import")
    async def import_recipients(cid: int, request: Request):
        c = row("campaigns", cid, "Campaign")
        fields, files = await read_multipart(request)
        if "file" not in files:
            raise ApiErr(422, "validation_error", "Choose a CSV file.")
        consent = yes(fields.get("consent_confirmed"))
        rows = parse_csv(files["file"][1])
        if len(rows) > 5000:
            raise ApiErr(413, "too_large", "Import at most 5,000 people at a time.")
        imported, errors = 0, []
        for line, r in enumerate(rows, start=2):
            try:
                lang = (r.get("language") or r.get("preferred_language") or "").lower()[:2]
                b = RecipientIn(name=r.get("name") or "", phone=r.get("phone") or r.get("mobile") or "", external_ref=r.get("participant_id") or r.get("external_ref") or None,
                                preferred_language=lang if lang in SUPPORTED else None, segment=r.get("segment") or None,
                                consent_status="granted" if consent and not yes(r.get("opted_out")) else "unknown", message=r.get("message") or "")
                p = upsert_person(c["event_id"], person_values(b))
                if yes(r.get("opted_out")):
                    db.update("participants", p["id"], opted_out=1, can_call=0)
                    p["opted_out"] = 1
                add_to_campaign(c, p, b.message)
                imported += 1
            except ApiErr as exc:
                errors.append({"line": line, "error": exc.message})
            except ValueError:
                errors.append({"line": line, "error": "name and phone are required"})
        return {"imported": imported, "rejected": len(errors), "errors": errors[:50]}

    @app.patch("/recipients/{rid}")
    def patch_recipient(rid: int, body: RecipientPatch):
        call = row("calls", rid, "Recipient")
        if call["status"] in ("dialing", "in_progress"):
            raise ApiErr(409, "conflict", "A call to this person is in progress.")
        if body.message is not None:
            db.update("calls", rid, custom_message=body.message.strip())
        if body.preferred_language is not None:
            if body.preferred_language and body.preferred_language not in SUPPORTED:
                raise ApiErr(422, "validation_error", "Language not supported.")
            db.update("participants", call["participant_id"], language=body.preferred_language)
        return recipient_out(row("calls", rid, "Recipient"))

    @app.post("/recipients/{rid}/opt-out")
    def opt_out(rid: int):
        row("calls", rid, "Recipient")
        engine.record_opt_out(rid)
        return recipient_out(row("calls", rid, "Recipient"))

    @app.get("/recipients")
    def all_recipients(event_id: int | None = None, attention: bool = False, retry_eligible: bool = False, opted_out: bool = False,
                       outcome: str | None = None, language: str | None = None):
        where, args = ["1=1"], []
        if event_id:
            where.append("k.event_id=?")
            args.append(event_id)
        out = recipients_for(" AND ".join(where), tuple(args))
        camps = {c["id"]: c for c in db.q("SELECT * FROM campaigns")}
        if attention:
            out = [r for r in out if r["outcome"] in ("unclear", "human_required", "callback_requested", "information_requested", "no_response") and not r["opted_out"]]
        if retry_eligible:
            out = [r for r in out if r["outcome"] == "no_response" and r["attempts"] < camps[r["campaign_id"]]["max_attempts"] and r["can_call"] and not r["opted_out"]]
        if opted_out:
            out = [r for r in out if r["opted_out"]]
        if outcome:
            out = [r for r in out if r["outcome"] == outcome]
        if language:
            out = [r for r in out if r["preferred_language"] == language]
        return out

    @app.get("/recipients/{rid}/history")
    def history(rid: int):
        call = row("calls", rid, "Recipient")
        t = db.q("SELECT * FROM tasks WHERE campaign_id=? AND participant_id=? ORDER BY id", (call["campaign_id"], call["participant_id"]))
        return {"recipient": recipient_out(call), "attempts": attempts_for(call_id=rid),
                "intents": intents_for("call_id=?", (rid,)), "followups": [followup_out(x) for x in t]}

    @app.get("/campaigns/{cid}/attempts")
    def campaign_attempts(cid: int):
        row("campaigns", cid, "Campaign")
        return attempts_for(cid=cid)

    @app.get("/campaigns/{cid}/intents")
    def campaign_intents(cid: int):
        row("campaigns", cid, "Campaign")
        return intents_for("campaign_id=?", (cid,))

    # ================================================================== follow-ups
    @app.get("/followups")
    def followups(campaign_id: int | None = None, status: str | None = None):
        where, args = ["1=1"], []
        if campaign_id:
            where.append("campaign_id=?")
            args.append(campaign_id)
        out = [followup_out(t) for t in db.q(f"SELECT * FROM tasks WHERE {' AND '.join(where)} ORDER BY id DESC", tuple(args))]
        return [f for f in out if not status or f["status"] == status]

    @app.get("/followups/queue")
    def followup_queue(event_id: int | None = None, campaign_id: int | None = None):
        where, args = ["status='open'"], []
        if event_id:
            where.append("event_id=?")
            args.append(event_id)
        if campaign_id:
            where.append("campaign_id=?")
            args.append(campaign_id)
        items = [queue_item(t) for t in db.q(f"SELECT * FROM tasks WHERE {' AND '.join(where)}", tuple(args))]
        return sorted(items, key=lambda i: (i["priority"], i["created_at"]))

    @app.patch("/followups/{fid}")
    def patch_followup(fid: int, body: FollowupPatch):
        row("tasks", fid, "Follow-up")
        vals = {}
        if body.status in ("completed", "done"):
            vals.update(status="done", done_at=now())
        elif body.status == "cancelled":
            vals.update(status="cancelled", done_at=now())
        elif body.status in ("pending", "scheduled"):
            vals.update(status="open", done_at=None)
        elif body.status is not None:
            raise ApiErr(422, "validation_error", "Unknown status.")
        if body.scheduled_at:
            vals["scheduled_at"] = iso_future(body.scheduled_at)
        db.update("tasks", fid, **vals)
        return followup_out(row("tasks", fid, "Follow-up"))

    # ================================================================== analytics
    RATE = lambda a, b: round(a / b, 4) if b else None      # noqa: E731
    OUTCOMES = ["confirmed", "acknowledged", "declined", "callback_requested", "information_requested", "unclear", "human_required",
                "opted_out", "no_response", "pending"]

    @app.get("/analytics")
    def analytics(campaign_id: int | None = None, event_id: int | None = None, source: str = "all"):
        camps = db.q("SELECT * FROM campaigns")
        if campaign_id:
            camps = [c for c in camps if c["id"] == campaign_id]
        if event_id:
            camps = [c for c in camps if c["event_id"] == event_id]
        if source in ("simulated", "real"):
            camps = [c for c in camps if (engine.provider_for(c).is_simulated or bool(c["is_demo"])) == (source == "simulated")]
        ids = [c["id"] for c in camps]
        marks = ",".join("?" * len(ids)) or "NULL"
        calls = db.q(f"SELECT c.*, p.language AS plang, p.opted_out, p.can_call FROM calls c JOIN participants p ON p.id=c.participant_id "
                     f"WHERE c.campaign_id IN ({marks})", tuple(ids))
        atts = db.q(f"SELECT a.*, c.campaign_id FROM attempts a JOIN calls c ON c.id=a.call_id WHERE c.campaign_id IN ({marks})", tuple(ids))
        by_camp = {c["id"]: c for c in camps}
        outcomes = {k: 0 for k in OUTCOMES}
        for x in calls:
            outcomes[ui_outcome(x)] += 1
        n = len(calls)
        finished = [a for a in atts if a["status"] != "dialing"]
        answered = [a for a in finished if a["status"] == "completed"]
        sim = sum(1 for a in atts if engine.provider_for(by_camp[a["campaign_id"]]).is_simulated)
        responded = sum(outcomes[k] for k in ("confirmed", "acknowledged", "declined", "callback_requested", "information_requested", "unclear", "human_required", "opted_out"))
        tasks = db.q(f"SELECT status FROM tasks WHERE campaign_id IN ({marks})", tuple(ids))
        langs: dict[str, dict] = {}
        for x in calls:
            lang = x["plang"] or by_camp[x["campaign_id"]]["language"]
            d = langs.setdefault(lang, {"language": lang, "recipients": 0, "attempts": 0, "answered": 0, **{k: 0 for k in OUTCOMES}})
            d["recipients"] += 1
            d[ui_outcome(x)] += 1
        for a in atts:
            call = next((x for x in calls if x["id"] == a["call_id"]), None)
            if call:
                d = langs[call["plang"] or by_camp[call["campaign_id"]]["language"]]
                d["attempts"] += 1
                d["answered"] += a["status"] == "completed"
        confirmed, declined = outcomes["confirmed"], outcomes["declined"]
        unknown_break = {k: v for k, v in outcomes.items() if v and k not in ("confirmed", "declined", "acknowledged")}
        review = db.one(f"SELECT COUNT(*) n FROM calls WHERE needs_review=1 AND campaign_id IN ({marks})", tuple(ids))["n"]
        attention = sum(1 for x in calls if ui_outcome(x) in ("unclear", "human_required", "callback_requested", "information_requested", "no_response") and not x["opted_out"])
        return {"source": source,
                "totals": {"campaigns": len(camps), "recipients": n, "calls_attempted": len(atts), "calls_finished": len(finished),
                           "calls_answered": len(answered), "recipients_contacted": sum(1 for x in calls if x["attempts"] > 0),
                           "recipients_responded": responded, "retries": sum(max(x["attempts"] - 1, 0) for x in calls),
                           "failed_or_unanswered": len(finished) - len(answered), "simulated_calls": sim, "real_calls": len(atts) - sim},
                "outcomes": outcomes,
                "followups": {"pending": sum(t["status"] == "open" for t in tasks), "completed": sum(t["status"] == "done" for t in tasks),
                              "cancelled": sum(t["status"] == "cancelled" for t in tasks)},
                "rates": {"completion_rate": RATE(n - outcomes["pending"], n), "answer_rate": RATE(len(answered), len(finished)),
                          "failure_rate": RATE(len(finished) - len(answered), len(finished)), "confirmation_rate": RATE(confirmed, responded),
                          "decline_rate": RATE(declined, responded), "unclear_rate": RATE(outcomes["unclear"] + outcomes["human_required"], responded)},
                "by_language": sorted(langs.values(), key=lambda d: d["language"]),
                "needs_review": review, "needs_attention": attention,
                "headcount": {"participants": n, "confirmed": confirmed, "declined": declined, "unknown": n - confirmed - declined,
                              "unknown_breakdown": unknown_break, "floor": confirmed, "ceiling": n - declined,
                              "certainty": RATE(confirmed + declined, n) or 0} if n else None,
                "clarification": {"attempted": 0, "resolved": 0}}

    # ================================================================== leads
    def lead_score(l: dict) -> tuple[int, list[str]]:
        pts = [(40, "consent granted", l["consent_status"] == "granted"), (25, "came from registration form", l["source"] == "registration_form"),
               (15, "stated an interest", bool(l.get("interest"))), (10, "gave an email", bool(l.get("email"))), (10, "preferred language known", bool(l.get("preferred_language")))]
        got = [(p, why) for p, why, ok in pts if ok]
        return min(100, sum(p for p, _ in got)), [f"{why} (+{p})" for p, why in got]

    def lead_out(l: dict) -> dict:
        score, reasons = lead_score(l)
        call = db.one("SELECT * FROM calls WHERE id=?", (l["recipient_id"],)) if l["recipient_id"] else None
        return {"id": l["id"], "event_id": l["event_id"], "name": l["name"], "phone": l["phone"], "email": l["email"], "source": l["source"],
                "interest": l["interest"], "preferred_language": l["preferred_language"], "consent_status": l["consent_status"], "status": l["status"],
                "notes": l["notes"] or "", "recipient_id": l["recipient_id"], "is_demo": bool(l["is_demo"]), "created_at": l["created_at"],
                "score": score, "score_reasons": reasons, "campaign_id": l["campaign_id"], "recipient_outcome": ui_outcome(call) if call else None}

    def insert_lead(eid: int, b: LeadIn, is_demo: bool = False) -> dict:
        phone = normalize_phone(b.phone)
        if not phone:
            raise ApiErr(422, "validation_error", f"'{b.phone}' is not a valid phone number.", [{"field": "phone", "message": "invalid phone number"}])
        if db.one("SELECT 1 FROM leads WHERE event_id=? AND phone=?", (eid, phone)):
            raise ApiErr(409, "conflict", f"{phone} is already a lead for this event.")
        lid = db.insert("leads", event_id=eid, name=b.name.strip(), phone=phone, email=b.email, source=b.source, interest=b.interest,
                        preferred_language=b.preferred_language if b.preferred_language in SUPPORTED else None, consent_status=b.consent_status,
                        notes=b.notes, is_demo=int(is_demo), created_at=now())
        return db.one("SELECT * FROM leads WHERE id=?", (lid,))

    @app.get("/events/{eid}/leads")
    def list_leads(eid: int, status: str | None = None, source: str | None = None, q: str | None = None):
        row("events", eid, "Event")
        out = [lead_out(l) for l in db.q("SELECT * FROM leads WHERE event_id=? ORDER BY id DESC", (eid,))]
        ql = (q or "").lower()
        out = [l for l in out if (not status or l["status"] == status) and (not source or l["source"] == source)
               and (not ql or ql in l["name"].lower() or ql in l["phone"] or ql in (l["email"] or "").lower())]
        return sorted(out, key=lambda l: -l["score"])

    @app.get("/events/{eid}/leads/summary")
    def lead_summary(eid: int):
        row("events", eid, "Event")
        ls = db.q("SELECT * FROM leads WHERE event_id=?", (eid,))
        by_status = {k: sum(1 for l in ls if l["status"] == k) for k in ("new", "contacted", "qualified", "converted", "lost")}
        consented = sum(1 for l in ls if l["consent_status"] == "granted")
        sources = {}
        for l in ls:
            s = sources.setdefault(l["source"], {"source": l["source"], "leads": 0, "converted": 0, "consented": 0})
            s["leads"] += 1
            s["converted"] += l["status"] == "converted"
            s["consented"] += l["consent_status"] == "granted"
        for s in sources.values():
            s["conversion_rate"] = RATE(s["converted"], s["leads"]) or 0
        return {"total": len(ls), "by_status": by_status, "consented": consented, "consent_rate": RATE(consented, len(ls)),
                "conversion_rate": RATE(by_status["converted"], len(ls)),
                "ready_to_convert": sum(1 for l in ls if l["consent_status"] == "granted" and l["status"] in ("new", "contacted", "qualified")),
                "by_source": sorted(sources.values(), key=lambda s: -s["leads"])}

    @app.post("/events/{eid}/leads", status_code=201)
    def capture_lead(eid: int, body: LeadIn):
        row("events", eid, "Event")
        return lead_out(insert_lead(eid, body))

    @app.post("/events/{eid}/leads/import")
    async def import_leads(eid: int, request: Request):
        row("events", eid, "Event")
        fields, files = await read_multipart(request)
        if "file" not in files:
            raise ApiErr(422, "validation_error", "Choose a CSV file.")
        consent = yes(fields.get("consent_confirmed"))
        imported, errors = 0, []
        for line, r in enumerate(parse_csv(files["file"][1]), start=2):
            try:
                insert_lead(eid, LeadIn(name=r.get("name") or "", phone=r.get("phone") or "", email=r.get("email") or None, source="csv_import",
                                        interest=r.get("interest") or None, preferred_language=(r.get("language") or "")[:2].lower() or None,
                                        consent_status="granted" if consent else "unknown"))
                imported += 1
            except ApiErr as exc:
                errors.append({"line": line, "error": exc.message})
            except ValueError:
                errors.append({"line": line, "error": "name and phone are required"})
        return {"imported": imported, "rejected": len(errors), "errors": errors[:50]}

    @app.patch("/leads/{lid}")
    def patch_lead(lid: int, body: LeadPatch):
        row("leads", lid, "Lead")
        vals = {k: v for k, v in body.model_dump().items() if v is not None}
        if vals.get("status") and vals["status"] not in ("new", "contacted", "qualified", "converted", "lost"):
            raise ApiErr(422, "validation_error", "Unknown lead status.")
        db.update("leads", lid, **vals)
        return lead_out(row("leads", lid, "Lead"))

    @app.post("/leads/convert")
    def convert_leads(body: ConvertIn):
        c = row("campaigns", body.campaign_id, "Campaign")
        converted, skipped = 0, []
        for lid in body.lead_ids:
            l = db.one("SELECT * FROM leads WHERE id=? AND event_id=?", (lid, c["event_id"]))
            if not l:
                skipped.append({"lead_id": lid, "reason": "not a lead of this campaign's event"})
            elif l["consent_status"] != "granted":
                skipped.append({"lead_id": lid, "reason": "consent not granted"})
            elif l["status"] == "converted":
                skipped.append({"lead_id": lid, "reason": "already converted"})
            else:
                p = upsert_person(c["event_id"], {"name": l["name"], "phone": l["phone"], "language": l["preferred_language"] or "", "segment": "lead",
                                                  "external_ref": None, "can_call": 1, "consent_status": "granted", "fields": "{}"})
                try:
                    call = add_to_campaign(c, p)
                except ApiErr:
                    call = db.one("SELECT * FROM calls WHERE campaign_id=? AND participant_id=?", (c["id"], p["id"]))
                db.update("leads", lid, status="converted", recipient_id=call["id"], campaign_id=c["id"])
                converted += 1
        return {"converted": converted, "skipped": skipped}

    # ================================================================== sample data (always simulated, never dialled)
    SAMPLE_EVENTS = [
        ("[SAMPLE] DEFINE 4.0 - MBCET, Thiruvananthapuram", "Demonstration scenario only. Not affiliated with or requested by the organisers.",
         {"venue": "MBCET, Thiruvananthapuram"}),
        ("[SAMPLE] Campus Code Sprint (fictional)", "Fictional sample event with venue AND schedule approved, so both questions get answers.",
         {"venue": "Seminar Hall A (sample text)", "schedule": "Saturday 10:00-18:00 (sample text)"}),
        ("[SAMPLE] Cloud Basics Webinar (fictional)", "Fictional online webinar used to try the dashboard.", {"venue": "Online", "schedule": "Friday 17:30"}),
    ]
    SAMPLE_DIGITS = "0000011234569"      # last digits drive the simulated scenarios (yes, yes, no, callback, unclear, no answer, ...)

    def seed_events(run: bool) -> tuple[list[dict], list[dict]]:
        evs, camps = [], []
        for name, desc, info in SAMPLE_EVENTS:
            if db.one("SELECT 1 FROM events WHERE name=?", (name,)):
                continue
            eid = db.insert("events", name=name, type="custom", mode="in_person", description=desc, created_at=now(), is_demo=1,
                            **event_values(info, None))
            msg = f"Hello, this is the sample assistant calling about {name}. Will you be able to attend?"
            cid = insert_campaign(CampaignIn(event_id=eid, name=f"{name.split(' - ')[0]} attendance confirmation", purpose="attendance_confirmation",
                                             messages={"en": msg}, languages=["en"], max_attempts=3, retry_interval_min=0), is_demo=True)
            for i, d in enumerate(SAMPLE_DIGITS):
                p = upsert_person(eid, {"name": f"Sample Participant {i}", "phone": sample_numbers(i * 10 + int(d)), "language": "en", "segment": "sample",
                                        "external_ref": f"SAMPLE-{i:03d}", "can_call": 1, "consent_status": "granted", "fields": "{}"})
                db.update("participants", p["id"], is_demo=1)
                add_to_campaign(row("campaigns", cid, "Campaign"), p)
            if run:
                engine_do(engine.launch, cid)
            evs.append(event_out(row("events", eid, "Event")))
            camps.append(campaign_out(row("campaigns", cid, "Campaign")))
        return evs, camps

    @app.post("/demo/seed")
    def demo_seed():
        _, camps = seed_events(False)
        return camps[0] if camps else campaign_out(db.one("SELECT * FROM campaigns WHERE is_demo=1 ORDER BY id LIMIT 1"))

    @app.post("/demo/seed-all")
    def demo_seed_all(run: bool = False):
        evs, camps = seed_events(run)
        if not evs:
            evs = [event_out(e) for e in db.q("SELECT * FROM events WHERE is_demo=1")]
            camps = [campaign_out(c) for c in db.q("SELECT * FROM campaigns WHERE is_demo=1")]
        return {"ran": run, "campaigns": camps, "events": evs}

    @app.post("/demo/seed-leads")
    def demo_seed_leads():
        ev = db.one("SELECT * FROM events WHERE is_demo=1 ORDER BY id LIMIT 1") or db.one("SELECT * FROM events ORDER BY id LIMIT 1")
        if not ev:
            raise ApiErr(409, "conflict", "Create or load an event first.")
        added = 0
        for i, (src, consent, interest) in enumerate([("registration_form", "granted", "AI / ML"), ("registration_form", "granted", "Web"),
                                                      ("csv_import", "granted", "Cloud"), ("registration_form", "unknown", None),
                                                      ("csv_import", "unknown", None), ("walk_in", "granted", "Design")]):
            try:
                insert_lead(ev["id"], LeadIn(name=f"Sample Lead {i:02d}", phone=f"+1555010{100 + i}", email=f"sample.lead{i:02d}@example.invalid",
                                             source=src, interest=interest, preferred_language="en", consent_status=consent, notes="Sample lead (fictional)."),
                            is_demo=True)
                added += 1
            except ApiErr:
                pass
        return {"leads_added": added}

    @app.delete("/demo")
    def reset_demo():
        n = db.one("SELECT COUNT(*) n FROM campaigns WHERE is_demo=1")["n"]
        for c in db.q("SELECT id FROM campaigns WHERE is_demo=1"):
            if engine.is_active(c["id"]):
                raise ApiErr(409, "conflict", "Wait for the sample simulation to finish.")
        db.x("DELETE FROM events WHERE is_demo=1")
        db.x("DELETE FROM leads WHERE is_demo=1")
        return {"deleted_campaigns": n}

    return app
