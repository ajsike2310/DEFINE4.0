"""Campaign engine: turns a campaign + audience into calls, records what happened, and summarises outcomes."""
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from member3.integrations.base import ProviderError
from member3.intelligence.pipeline import ResponseInput, process_response
from member3.live.campaign import CallContext, CampaignInfo
from member3.live.results import CallResult, build_result

from .config import Settings
from .db import Db, loads, now
from .messages import _parse_date, _parse_time, compose

log = logging.getLogger("dashboard")

# Provider statuses that mean "the call did not connect"; they can be retried.
UNREACHED = ("no_answer", "busy", "failed", "voicemail")
OUTCOME_LABELS = {
    "confirmed": "Confirmed", "declined": "Declined", "callback_requested": "Wants callback",
    "information_requested": "Asked a question", "acknowledged": "Acknowledged", "opted_out": "Opted out",
    "unclear": "Unclear", "needs_review": "Needs review", "no_response": "Picked up, no answer",
    "no_answer": "No answer", "busy": "Busy", "voicemail": "Voicemail", "failed": "Failed",
    "in_progress": "In progress", "pending": "Not called yet"}
ACTIVE = ("dialing", "in_progress")


def outcome_of(call: dict) -> str:
    st = call["status"]
    if st == "pending":
        return "pending"
    if st in ACTIVE:
        return "in_progress"
    if st == "completed":
        return call.get("attendance") or "no_response"
    return st if st in OUTCOME_LABELS else "failed"


def is_non_responder(call: dict) -> bool:
    return call["status"] in UNREACHED or (call["status"] == "completed"
                                           and (call.get("attendance") or "no_response") in ("no_response", "unclear", "needs_review"))


def summarize(calls: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for c in calls:
        o = outcome_of(c)
        counts[o] = counts.get(o, 0) + 1
    total = len(calls)
    reached = sum(1 for c in calls if c["status"] == "completed")
    answered = sum(v for k, v in counts.items() if k in ("confirmed", "declined", "callback_requested",
                                                        "information_requested", "acknowledged", "opted_out"))
    return {"total": total, "counts": counts, "reached": reached, "responded": answered,
            "confirmed": counts.get("confirmed", 0), "pending": counts.get("pending", 0),
            "in_progress": counts.get("in_progress", 0),
            "reach_rate": round(100 * reached / total) if total else 0,
            "response_rate": round(100 * answered / total) if total else 0}


class CampaignError(Exception):
    """A problem the user can fix (shown verbatim in the UI)."""


class Engine:
    def __init__(self, db: Db, provider, settings: Settings, live=None):
        self.db, self.provider, self.settings, self.live = db, provider, settings, live
        self._threads: dict[int, threading.Thread] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- audience / launching
    def add_members(self, campaign_id: int, participant_ids: list[int], message: str = "") -> dict:
        """Put people from the campaign's event into the campaign. Opted-out people and people already in it are skipped."""
        camp = self.db.one("SELECT * FROM campaigns WHERE id=?", (campaign_id,))
        added = skipped = 0
        for pid in dict.fromkeys(participant_ids):
            p = self.db.one("SELECT * FROM participants WHERE id=? AND event_id=?", (pid, camp["event_id"]))
            if not p or p["opted_out"] or not p["can_call"] or self.db.one(
                    "SELECT 1 FROM calls WHERE campaign_id=? AND participant_id=?", (campaign_id, pid)):
                skipped += 1
                continue
            self.db.insert("calls", campaign_id=campaign_id, participant_id=pid, custom_message=message.strip(),
                           updated_at=now())
            added += 1
        return {"added": added, "skipped": skipped}

    # ---------------------------------------------------------------- calling hours (editable in the dashboard)
    def get_hours(self) -> dict:
        """{enabled, start, end}. The dashboard's saved choice wins; CALL_WINDOW in .env is only the first default."""
        row = self.db.one("SELECT value FROM settings WHERE key='calling_hours'")
        if row:
            try:
                h = json.loads(row["value"])
                return {"enabled": bool(h.get("enabled")), "start": h.get("start", "09:00"), "end": h.get("end", "21:00")}
            except ValueError:
                pass
        m = re.fullmatch(r"\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*", self.settings.call_window or "")
        return {"enabled": bool(m), "start": m.group(1).zfill(5) if m else "09:00", "end": m.group(2).zfill(5) if m else "21:00"}

    def set_hours(self, enabled: bool, start: str, end: str) -> dict:
        for v in (start, end):
            if not re.fullmatch(r"\d{2}:\d{2}", v or ""):
                raise CampaignError("Times must look like 09:00")
        if enabled and start >= end:
            raise CampaignError("The end time must be after the start time")
        self.db.x("INSERT INTO settings(key, value) VALUES('calling_hours', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (json.dumps({"enabled": enabled, "start": start, "end": end}),))
        return self.get_hours()

    def local_now(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(minutes=self.settings.call_timezone_offset_min)

    def _check_window(self) -> None:
        h = self.get_hours()
        if not h["enabled"] or self.provider.is_simulated:
            return
        start, end = (datetime.strptime(x, "%H:%M").time() for x in (h["start"], h["end"]))
        if not (start <= self.local_now().time() <= end):
            raise CampaignError(f"Outside calling hours ({h['start']}-{h['end']} IST). Change or switch off calling hours in Settings.")

    def is_active(self, campaign_id: int) -> bool:
        t = self._threads.get(campaign_id)
        return bool(t and t.is_alive())

    def launch(self, campaign_id: int) -> dict:
        c = self.db.one("SELECT * FROM campaigns WHERE id=?", (campaign_id,))
        if not c:
            raise CampaignError("Campaign not found")
        if not (c["template"] or "").strip():
            raise CampaignError("Write the call message first")
        self._check_window()
        pending = self.db.one("SELECT COUNT(*) n FROM calls c JOIN participants p ON p.id=c.participant_id "
                              "WHERE c.campaign_id=? AND c.status='pending' AND p.opted_out=0 AND p.can_call=1", (campaign_id,))["n"]
        if pending == 0:
            raise CampaignError("Nobody left to call. Add people to this campaign first (opted-out people are never called).")
        self.db.update("campaigns", campaign_id, status="active", launched_at=c["launched_at"] or now())
        with self._lock:
            if not self.is_active(campaign_id):
                t = threading.Thread(target=self._run, args=(campaign_id,), name=f"campaign-{campaign_id}", daemon=True)
                self._threads[campaign_id] = t
                t.start()
        return {"queued": pending}

    def pause(self, campaign_id: int) -> None:
        self.db.update("campaigns", campaign_id, status="paused")

    def retry_non_responders(self, campaign_id: int) -> dict:
        c = self.db.one("SELECT * FROM campaigns WHERE id=?", (campaign_id,))
        if not c:
            raise CampaignError("Campaign not found")
        n = 0
        for call in self.db.q("SELECT c.*, (p.opted_out OR NOT p.can_call) AS opted_out FROM calls c JOIN participants p ON p.id=c.participant_id "
                              "WHERE c.campaign_id=?", (campaign_id,)):
            if call["opted_out"] or not is_non_responder(call) or call["attempts"] >= c["max_attempts"]:
                continue
            self.db.update("calls", call["id"], status="pending", error="", next_attempt_at=None, updated_at=now())
            n += 1
        if n == 0:
            raise CampaignError("No non-responders to retry (everyone either answered or reached the attempt limit).")
        self.launch(campaign_id)
        return {"queued": n}

    def redial(self, call_id: int) -> None:
        self.db.update("calls", call_id, next_attempt_at=None)
        call = self.db.one("SELECT * FROM calls WHERE id=?", (call_id,))
        if not call:
            raise CampaignError("Call not found")
        p = self.db.one("SELECT opted_out, can_call FROM participants WHERE id=?", (call["participant_id"],))
        if p and p["opted_out"]:
            raise CampaignError("This person opted out and will not be called.")
        if p and not p["can_call"]:
            raise CampaignError("This person is marked as not OK to call.")
        if call["status"] in ACTIVE:
            raise CampaignError("A call to this person is already in progress.")
        self.db.update("calls", call_id, status="pending", error="", updated_at=now())
        self.launch(call["campaign_id"])

    # ---------------------------------------------------------------- the dialer thread
    def _run(self, campaign_id: int) -> None:
        try:
            while True:
                c = self.db.one("SELECT status FROM campaigns WHERE id=?", (campaign_id,))
                if not c or c["status"] != "active":
                    return
                call = self.db.one("SELECT c.id FROM calls c JOIN participants p ON p.id=c.participant_id "
                                   "WHERE c.campaign_id=? AND c.status='pending' AND p.opted_out=0 AND p.can_call=1 "
                                   "ORDER BY c.id LIMIT 1", (campaign_id,))
                if not call:
                    return
                try:
                    self._dial(call["id"])
                except Exception:                                   # one bad call must not stop the campaign
                    log.exception("dial failed for call %s", call["id"])
                    self.db.update("calls", call["id"], status="failed", error="internal error", updated_at=now())
                time.sleep(self.settings.dial_interval_s)
        finally:
            self._threads.pop(campaign_id, None)

    def _dial(self, call_id: int) -> None:
        call = self.db.one("SELECT * FROM calls WHERE id=?", (call_id,))
        camp = self.db.one("SELECT * FROM campaigns WHERE id=?", (call["campaign_id"],))
        event = self.db.one("SELECT * FROM events WHERE id=?", (camp["event_id"],))
        person = self.db.one("SELECT * FROM participants WHERE id=?", (call["participant_id"],))
        person["fields"] = loads(person["fields"])
        person["custom_message"] = call["custom_message"]          # this campaign's personal message, not a global one
        message, lang, _ = compose(camp, event, person)
        number = call["attempts"] + 1
        attempt_id = self.db.insert("attempts", call_id=call_id, number=number, started_at=now())
        self.db.update("calls", call_id, status="dialing", attempts=number, message=message, error="", updated_at=now())
        self.provider.last_error_detail = ""
        try:
            res = self.provider.initiate_call(attempt_id=attempt_id, attempt_number=number, to=person["phone"],
                                              language=lang, message=message)
        except ProviderError as exc:
            self._finish_attempt(attempt_id, "failed")
            detail = getattr(self.provider, "last_error_detail", "")
            self.db.update("calls", call_id, status="failed", error=(f"{exc}: {detail}" if detail else str(exc))[:400], updated_at=now())
            self._followup(call_id)
            return
        self.db.update("attempts", attempt_id, provider_call_id=res.provider_call_id)
        self.db.update("calls", call_id, provider_call_id=res.provider_call_id, status="in_progress", updated_at=now())
        if self.provider.is_simulated:
            self._apply_simulated(call_id, attempt_id, camp, person, res)
        elif self.live is not None:
            from member3.live.campaign import CallContext as Ctx
            self.live.register_call(Ctx(
                provider_call_id=res.provider_call_id, attempt_id=attempt_id, participant_id=str(person["id"]),
                campaign_id=str(camp["id"]), participant_name=person["name"],
                campaign=CampaignInfo(
                    name=event["name"], venue=event["venue"] or ("online" if event["mode"] == "online" else ""),
                    event_date=_parse_date(event["event_date"]), event_time=_parse_time(event["event_time"]),
                    organiser=event["organiser"], description=event["description"] or "",
                    language=lang, greeting_override=message)))

    def _apply_simulated(self, call_id, attempt_id, camp, person, res) -> None:
        """Demo provider: its scripted events are applied right away, through the real classifier."""
        ctx = CallContext(provider_call_id=res.provider_call_id, attempt_id=attempt_id, participant_id=str(person["id"]),
                          campaign_id=str(camp["id"]), campaign=CampaignInfo(name=""))
        for ev in res.events:
            if ev.kind == "status" and ev.status in UNREACHED:
                self._finish_attempt(attempt_id, ev.status)
                self.db.update("calls", call_id, status=ev.status, updated_at=now())
                self._followup(call_id)
            elif ev.kind == "response":
                decision = process_response(ResponseInput(text=ev.text, dtmf=ev.dtmf))
                self.on_result(build_result(ctx, decision, call_outcome="completed"))

    # ---------------------------------------------------------------- results coming back
    def _finish_attempt(self, attempt_id: int, status: str) -> None:
        self.db.update("attempts", attempt_id, status=status, ended_at=now())

    def on_result(self, r: CallResult) -> None:
        """Sink for the live-call layer: one result per call, de-duplicated on event_id."""
        att = self.db.one("SELECT * FROM attempts WHERE id=?", (r.attempt_id,))
        if not att:
            log.warning("result for unknown attempt %s ignored", r.attempt_id)
            return
        call = self.db.one("SELECT * FROM calls WHERE id=?", (att["call_id"],))
        if call["last_event_id"] == r.event_id:
            return
        self._finish_attempt(att["id"], "completed")
        self.db.update(
            "calls", call["id"], status="completed", attendance=r.attendance, needs_review=int(r.needs_review),
            language_detected=r.language, method=r.method, requested_time=r.requested_time, time_hint=r.time_hint,
            info_topic=r.info_topic, last_event_id=r.event_id, updated_at=now())
        if r.attendance == "opted_out":
            self.db.update("participants", call["participant_id"], opted_out=1)
        self._record_rsvp(call, r.attendance)
        self._followup(call["id"])

    # ---------------------------------------------------------------- automatic retries
    def _schedule_retry(self, call: dict) -> None:
        """After a call that did not reach the person (no answer, busy, picked up but silent), plan the next attempt."""
        camp = self.db.one("SELECT * FROM campaigns WHERE id=?", (call["campaign_id"],))
        retryable = call["status"] in ("no_answer", "busy", "voicemail") or (
            call["status"] == "failed" and not call.get("error")) or (
            call["status"] == "completed" and (call.get("attendance") or "no_response") == "no_response")
        due = None
        if camp["auto_retry"] and retryable and call["attempts"] < camp["max_attempts"]:
            due = (datetime.now(timezone.utc) + timedelta(minutes=camp["retry_interval_min"])).isoformat(timespec="seconds")
        self.db.update("calls", call["id"], next_attempt_at=due)

    def run_due_retries(self) -> int:
        """Put every call whose retry time has come back in the queue and restart its campaign. Returns how many."""
        due = self.db.q(
            "SELECT c.id, c.campaign_id FROM calls c JOIN campaigns k ON k.id=c.campaign_id JOIN participants p ON p.id=c.participant_id "
            "WHERE k.status='active' AND k.auto_retry=1 AND c.next_attempt_at IS NOT NULL AND c.next_attempt_at<=? "
            "AND c.status IN ('no_answer','busy','voicemail','failed','completed') AND c.attempts<k.max_attempts "
            "AND p.opted_out=0 AND p.can_call=1", (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
        if not due:
            return 0
        try:
            self._check_window()                    # outside calling hours: leave them scheduled, try again on the next scan
        except CampaignError:
            return 0
        campaigns = set()
        for d in due:
            self.db.update("calls", d["id"], status="pending", error="", next_attempt_at=None, updated_at=now())
            campaigns.add(d["campaign_id"])
        for cid in campaigns:
            try:
                self.launch(cid)
            except CampaignError:
                log.warning("could not restart campaign %s for retries", cid)
        return len(due)

    def start_scheduler(self) -> None:
        def loop():
            while True:
                time.sleep(self.settings.scheduler_interval_s)
                try:
                    self.run_due_retries()
                except Exception:
                    log.exception("retry scheduler failed")
        threading.Thread(target=loop, name="retry-scheduler", daemon=True).start()

    # ---------------------------------------------------------------- RSVP and follow-up tasks
    def _record_rsvp(self, call: dict, attendance: str) -> None:
        """Keep the person's RSVP for the event current. A clear yes/no always wins; an unclear call never erases one."""
        clear = {"confirmed": "attending", "declined": "not_attending", "opted_out": "not_attending"}
        p = self.db.one("SELECT rsvp FROM participants WHERE id=?", (call["participant_id"],))
        if attendance in clear:
            new = clear[attendance]
        elif attendance in ("unclear", "needs_review", "callback_requested", "information_requested") and (p["rsvp"] or "") in ("", "undecided"):
            new = "undecided"
        else:
            return
        self.db.update("participants", call["participant_id"], rsvp=new, rsvp_at=now(), rsvp_campaign_id=call["campaign_id"])

    def _open_task(self, call: dict, event_id: int, kind: str, reason: str) -> None:
        existing = self.db.one("SELECT id FROM tasks WHERE campaign_id=? AND participant_id=? AND kind=? AND status='open'",
                               (call["campaign_id"], call["participant_id"], kind))
        if existing:
            self.db.update("tasks", existing["id"], reason=reason, call_id=call["id"])
        else:
            self.db.insert("tasks", event_id=event_id, campaign_id=call["campaign_id"], participant_id=call["participant_id"],
                           call_id=call["id"], kind=kind, reason=reason, created_at=now())

    def _followup(self, call_id: int) -> None:
        """Turn a call outcome that a machine could not settle into a task for a person."""
        call = self.db.one("SELECT * FROM calls WHERE id=?", (call_id,))
        if not call:
            return
        camp = self.db.one("SELECT event_id, max_attempts FROM campaigns WHERE id=?", (call["campaign_id"],))
        self._schedule_retry(call)
        att, st, n = call.get("attendance") or "", call["status"], call["attempts"]
        if st == "completed" and att in ("confirmed", "declined", "opted_out", "acknowledged"):
            self.db.x("UPDATE tasks SET status='done', done_at=?, note=CASE WHEN note='' THEN ? ELSE note END "
                      "WHERE campaign_id=? AND participant_id=? AND status='open'",
                      (now(), f"Resolved automatically: later call answered '{OUTCOME_LABELS.get(att, att)}'",
                       call["campaign_id"], call["participant_id"]))
        elif st == "completed" and att in ("unclear", "needs_review"):
            self._open_task(call, camp["event_id"], "in_person_call", "The answer was unclear. Call or meet the person to confirm whether they will attend.")
        elif st == "completed" and att == "callback_requested":
            hint = call.get("time_hint") or call.get("requested_time") or ""
            self._open_task(call, camp["event_id"], "callback", "Asked to be called back" + (f" ({hint})." if hint else "."))
        elif st == "completed" and att == "information_requested":
            topic = {"venue": "the venue", "schedule": "the schedule"}.get(call.get("info_topic") or "", "the event")
            self._open_task(call, camp["event_id"], "answer_question", f"Asked about {topic}. Reply with the details.")
        elif n >= camp["max_attempts"] and (st in UNREACHED or (st == "completed" and att == "no_response")):
            why = "picked up but gave no answer" if st == "completed" else OUTCOME_LABELS.get(st, st).lower()
            self._open_task(call, camp["event_id"], "in_person_call", f"Not reached after {n} {'attempt' if n == 1 else 'attempts'} ({why}). Contact the person another way.")

    def on_status(self, provider_call_id: str, status: str) -> None:
        """Provider status callback (Exotel StatusCallback). Only unreached outcomes matter here: a connected call
        reports its result through the live session."""
        status = {"no-answer": "no_answer", "busy": "busy", "failed": "failed", "canceled": "failed"}.get(status, status)
        att = self.db.one("SELECT * FROM attempts WHERE provider_call_id=?", (provider_call_id,))
        if not att:
            return
        call = self.db.one("SELECT * FROM calls WHERE id=?", (att["call_id"],))
        if status in UNREACHED and call["status"] in ACTIVE:
            self._finish_attempt(att["id"], status)
            self.db.update("calls", call["id"], status=status, updated_at=now())
            self._followup(call["id"])
        elif status == "completed" and call["status"] in ACTIVE:
            # connected but the live session never reported (stream failed): do not leave it spinning
            self._finish_attempt(att["id"], "completed")
            self.db.update("calls", call["id"], status="completed", attendance="no_response", needs_review=1,
                           updated_at=now())
            self._followup(call["id"])

    def reconcile(self, older_than_s: int = 150) -> int:
        """Ask the provider about calls stuck in progress (e.g. a lost callback). Returns how many were updated."""
        get = getattr(self.provider, "get_call_status", None)
        if not get:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_s)).isoformat(timespec="seconds")
        n = 0
        for call in self.db.q("SELECT * FROM calls WHERE status IN ('dialing','in_progress') AND updated_at<? "
                              "AND provider_call_id IS NOT NULL", (cutoff,)):
            try:
                st = (get(call["provider_call_id"]).get("Status") or "").lower()
            except ProviderError:
                continue
            if st in ("completed", "failed", "busy", "no-answer"):
                self.on_status(call["provider_call_id"], st)
                n += 1
        return n

    # ---------------------------------------------------------------- reporting
    def campaign_state(self, campaign: dict, summary: dict) -> str:
        if campaign["status"] == "paused":
            return "paused"
        if summary["total"] == 0 or campaign["status"] == "draft":
            return "draft"
        if self.is_active(campaign["id"]) or summary["in_progress"]:
            return "running"
        if summary["pending"]:
            return "ready"
        return "waiting" if summary.get("retries_scheduled") else "completed"
