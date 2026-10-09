"""What can go wrong on the first live day: placement failures, calls whose result never arrives, refused numbers."""
from datetime import datetime, timedelta, timezone

import pytest

from member2.backend.app.core.config import get_settings
from member2.backend.app.services import scheduler
from member3.integrations.base import InitiateResult, ProviderError

from .conftest import add_recipient, new_campaign

TOKEN = "t0ken-" + "x" * 20


class Provider:
    """A scriptable stand-in for Exotel: placement can fail, and Call Details answers what we tell it to."""
    name, is_simulated, supports_clarify = "exotel", False, True

    def __init__(self):
        self.fail_for: set[str] = set()
        self.details: dict[str, object] = {}                 # sid -> status string, or an exception to raise
        self.placed: list[str] = []

    def initiate_call(self, *, attempt_id, attempt_number, to, language, message, mode="main"):
        if to in self.fail_for:
            raise ProviderError("Exotel returned HTTP 503")
        self.placed.append(to)
        return InitiateResult(f"CA{attempt_id:06d}")

    def get_call_status(self, sid):
        got = self.details.get(sid, "in-progress")
        if isinstance(got, Exception):
            raise got
        return {"Sid": sid, "Status": got}

    def cancel_call(self, provider_call_id):
        return None


@pytest.fixture
def live(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "call_provider", "exotel")
    monkeypatch.setattr(s, "exotel_webhook_token", TOKEN)
    monkeypatch.setattr(s, "exotel_max_calls_per_minute", 600)
    p = Provider()
    client.app_.state.provider_override = p
    return p


def attempts(client, cid):
    return client.get(f"/api/campaigns/{cid}/attempts").json()


def recipient(client, cid, phone):
    return next(r for r in client.get(f"/api/campaigns/{cid}/recipients").json() if r["phone"] == phone)


# ---- a failed placement is retried (bounded), not stranded --------------------------------------------------------------
def test_a_placement_failure_schedules_a_bounded_retry(client, live):
    cid = new_campaign(client, max_attempts=2)["id"]
    add_recipient(client, cid, "+919876543210")
    live.fail_for = {"+919876543210"}
    client.post(f"/api/campaigns/{cid}/start")
    first = attempts(client, cid)[0]
    assert first["status"] == "failed" and "503" in first["failure_reason"] and first["next_retry_at"] is not None
    assert recipient(client, cid, "+919876543210")["outcome"] == "pending"
    client.post(f"/api/campaigns/{cid}/retry-due", params={"force": True})            # backoff skipped for the test
    assert len(attempts(client, cid)) == 2
    assert recipient(client, cid, "+919876543210")["outcome"] == "no_response"       # limit reached: honestly "never reached"
    assert client.get(f"/api/campaigns/{cid}").json()["status"] == "completed"       # nothing left to try
    assert client.post(f"/api/campaigns/{cid}/retry-due", params={"force": True}).status_code == 409
    assert len(attempts(client, cid)) == 2


def test_a_retry_after_a_placement_failure_can_succeed(client, live):
    cid = new_campaign(client)["id"]
    add_recipient(client, cid, "+919876543210")
    live.fail_for = {"+919876543210"}
    client.post(f"/api/campaigns/{cid}/start")
    live.fail_for = set()                                                             # Exotel recovered
    client.post(f"/api/campaigns/{cid}/retry-due", params={"force": True})
    last = attempts(client, cid)[-1]
    assert last["attempt_number"] == 2 and last["status"] == "initiating" and last["provider_call_id"]


# ---- refused numbers are skipped, not failed -----------------------------------------------------------------------------
def test_numbers_outside_the_allow_list_are_skipped_with_a_reason_and_never_attempted(client, live, monkeypatch):
    monkeypatch.setattr(get_settings(), "exotel_allowed_numbers", "+919876543210")
    cid = new_campaign(client)["id"]
    add_recipient(client, cid, "+919876543210")
    add_recipient(client, cid, "+919876543211")
    out = client.post(f"/api/campaigns/{cid}/start").json()
    assert out["dispatched"] == 1 and len(attempts(client, cid)) == 1 and live.placed == ["+919876543210"]
    assert [s["reason"] for s in out["skipped"]] == ["phone not in EXOTEL_ALLOWED_NUMBERS (real calls are limited to approved numbers)"]


def test_the_allow_list_never_applies_to_simulated_calls(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "exotel_allowed_numbers", "+919876543210")
    cid = new_campaign(client)["id"]                       # demo provider: simulated
    add_recipient(client, cid, "+919876543211")
    assert client.post(f"/api/campaigns/{cid}/start").json()["dispatched"] == 1


# ---- calls whose result never arrived --------------------------------------------------------------------------------------
@pytest.fixture
def stuck(client, live):
    """Three real calls placed, no callback ever received."""
    cid = new_campaign(client, max_attempts=3)["id"]
    for i in range(3):
        add_recipient(client, cid, f"+91987654321{i}")
    client.post(f"/api/campaigns/{cid}/start")
    return cid, {a["recipient_id"]: a["provider_call_id"] for a in attempts(client, cid)}


def test_fresh_calls_are_left_alone(client, live, stuck):
    cid, _ = stuck
    out = client.post(f"/api/campaigns/{cid}/reconcile").json()          # default threshold: 20 minutes
    assert out["checked"] == 0


def test_a_call_the_provider_says_is_finished_is_closed_like_a_callback_would(client, live, stuck):
    cid, sids = stuck
    first, second, third = sids.values()
    live.details = {first: "completed", second: "no-answer", third: "in-progress"}
    out = client.post(f"/api/campaigns/{cid}/reconcile", params={"minutes": 0}).json()
    assert out["checked"] == 3 and len(out["updated"]) == 2 and out["unchanged"] == [{"attempt_id": 3, "provider_status": "in-progress"}]
    by_sid = {a["provider_call_id"]: a for a in attempts(client, cid)}
    assert by_sid[first]["status"] == "completed" and by_sid[first]["answered_at"]
    assert by_sid[second]["status"] == "no_answer" and by_sid[second]["next_retry_at"] is not None     # bounded retry queued
    assert by_sid[third]["status"] == "initiating"
    late = client.post("/api/webhooks/exotel", params={"token": TOKEN}, data={"CallSid": first, "Status": "completed"})
    assert late.json()["result"] == "duplicate"                         # the callback that finally arrives changes nothing


def test_provider_errors_are_reported_and_nothing_is_guessed(client, live, stuck):
    cid, sids = stuck
    live.details = {sid: ProviderError("Exotel returned HTTP 500") for sid in sids.values()}
    out = client.post(f"/api/campaigns/{cid}/reconcile", params={"minutes": 0}).json()
    assert out["updated"] == [] and len(out["errors"]) == 3 and "500" in out["errors"][0]["error"]
    assert {a["status"] for a in attempts(client, cid)} == {"initiating"}


def test_a_call_that_may_never_have_been_placed_is_closed_without_a_retry(client, live):
    cid = new_campaign(client)["id"]
    r = add_recipient(client, cid, "+919876543210")
    with client.app_.state.engine.begin() as c:                     # a crash between creating the attempt and saving the SID
        c.exec_driver_sql("INSERT INTO call_attempts (campaign_id, recipient_id, provider, is_simulated, attempt_number, "
                          "mode, call_language, status) VALUES (?, ?, 'exotel', 0, 1, 'main', 'en', 'initiating')", (cid, r["id"]))
    out = client.post(f"/api/campaigns/{cid}/reconcile", params={"minutes": 0}).json()
    a = attempts(client, cid)[0]
    assert out["unplaced"] == [a["id"]] and a["status"] == "failed" and a["next_retry_at"] is None
    assert "not retried" in a["failure_reason"]


def test_simulated_campaigns_have_nothing_to_reconcile(client):
    cid = new_campaign(client)["id"]
    r = client.post(f"/api/campaigns/{cid}/reconcile")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_real"


def test_reconcile_validates_its_input(client, live):
    cid = new_campaign(client)["id"]
    assert client.post(f"/api/campaigns/{cid}/reconcile", params={"minutes": -1}).status_code == 422
    assert client.post("/api/campaigns/999/reconcile").status_code == 404


def test_the_scheduler_reconciles_overdue_real_calls(client, live, stuck):
    cid, sids = stuck
    live.details = {sid: "completed" for sid in sids.values()}
    result = scheduler.tick(client.app_.state.session_factory, get_settings(), override=live,
                            now=datetime.now(timezone.utc) + timedelta(minutes=45))
    assert result["reconciled"] == [{"campaign_id": cid, "updated": 3, "unplaced": 0, "errors": 0}]
    assert {a["status"] for a in attempts(client, cid)} == {"completed"}


def test_the_scheduler_does_not_reconcile_when_switched_off(client, live, stuck, monkeypatch):
    cid, _ = stuck
    monkeypatch.setattr(get_settings(), "stale_call_minutes", 0)
    result = scheduler.tick(client.app_.state.session_factory, get_settings(), override=live,
                            now=datetime.now(timezone.utc) + timedelta(minutes=45))
    assert result["reconciled"] == []


def test_a_finished_reconcile_can_complete_the_campaign(client, live):
    cid = new_campaign(client)["id"]
    add_recipient(client, cid, "+919876543210")
    client.post(f"/api/campaigns/{cid}/start")
    sid = attempts(client, cid)[0]["provider_call_id"]
    live.details = {sid: "failed"}
    client.post(f"/api/campaigns/{cid}/reconcile", params={"minutes": 0})
    client.post(f"/api/campaigns/{cid}/retry-due", params={"force": True})
    client.post(f"/api/campaigns/{cid}/retry-due", params={"force": True})
    assert client.get(f"/api/campaigns/{cid}").json()["status"] in ("running", "completed")
