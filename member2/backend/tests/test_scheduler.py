"""Scheduled launch and automatic due retries."""
from datetime import datetime, timedelta, timezone

from member2.backend.app.core.config import get_settings
from member2.backend.app.services import scheduler

from .conftest import add_recipient, new_campaign


def future(minutes=30):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def test_schedule_and_unschedule_rules(client):
    camp = new_campaign(client)
    cid = camp["id"]
    assert client.post(f"/api/campaigns/{cid}/schedule", json={"scheduled_at": future()}).status_code == 422   # nobody to call
    add_recipient(client, cid, "+919876543210")
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert client.post(f"/api/campaigns/{cid}/schedule", json={"scheduled_at": past}).status_code == 422
    assert client.post(f"/api/campaigns/{cid}/schedule", json={"scheduled_at": "2030-01-01T10:00:00"}).status_code == 422
    ok = client.post(f"/api/campaigns/{cid}/schedule", json={"scheduled_at": future()})
    assert ok.status_code == 200 and ok.json()["status"] == "scheduled"
    back = client.post(f"/api/campaigns/{cid}/unschedule")
    assert back.status_code == 200 and back.json()["status"] == "draft"
    assert client.post(f"/api/campaigns/{cid}/unschedule").status_code == 409                                   # already a draft


def test_a_running_campaign_cannot_be_scheduled(client):
    cid = new_campaign(client)["id"]
    add_recipient(client, cid, "+919876543210")
    client.post(f"/api/campaigns/{cid}/start")
    assert client.post(f"/api/campaigns/{cid}/schedule", json={"scheduled_at": future()}).status_code == 409


def test_tick_starts_only_due_scheduled_campaigns(client):
    due, later, draft = (new_campaign(client, name=n) for n in ("Due soon", "Later one", "Plain draft"))
    for c in (due, later, draft):
        add_recipient(client, c["id"], "+919876543210")
    client.post(f"/api/campaigns/{due['id']}/schedule", json={"scheduled_at": future(10)})
    client.post(f"/api/campaigns/{later['id']}/schedule", json={"scheduled_at": future(600)})
    now = datetime.now(timezone.utc) + timedelta(minutes=20)
    result = scheduler.tick(client.app_.state.session_factory, get_settings(), now=now)
    assert [s["campaign_id"] for s in result["started"]] == [due["id"]] and result["errors"] == []
    status = {c["id"]: c["status"] for c in client.get("/api/campaigns").json()}
    assert status[due["id"]] in ("running", "completed")
    assert status[later["id"]] == "scheduled" and status[draft["id"]] == "draft"
    again = scheduler.tick(client.app_.state.session_factory, get_settings(), now=now)
    assert again["started"] == []                                                                                # not twice


def test_tick_retries_only_when_due_and_within_the_limit(client):
    cid = new_campaign(client, max_attempts=2)["id"]
    add_recipient(client, cid, "+919876543218")            # simulated: busy on every attempt
    client.post(f"/api/campaigns/{cid}/start")
    factory, s = client.app_.state.session_factory, get_settings()
    assert scheduler.tick(factory, s)["retried"] == []                                  # backoff has not elapsed
    later = datetime.now(timezone.utc) + timedelta(minutes=s.retry_backoff_minutes + 1)
    assert scheduler.tick(factory, s, now=later)["retried"][0]["dispatched"] == 1
    attempts = client.get(f"/api/campaigns/{cid}/attempts").json()
    assert len(attempts) == 2
    much_later = later + timedelta(hours=5)
    assert scheduler.tick(factory, s, now=much_later)["retried"] == []                  # attempt limit reached
    assert len(client.get(f"/api/campaigns/{cid}/attempts").json()) == 2


def test_tick_reports_a_provider_problem_and_keeps_going(client, real_data):
    cid = new_campaign(client)["id"]                          # real campaign, but Exotel is not configured
    add_recipient(client, cid, "+919876543210")
    client.post(f"/api/campaigns/{cid}/schedule", json={"scheduled_at": future(5)})
    result = scheduler.tick(client.app_.state.session_factory, get_settings(),
                            now=datetime.now(timezone.utc) + timedelta(minutes=10))
    assert result["started"] == [] and result["errors"][0]["campaign_id"] == cid
    assert client.get(f"/api/campaigns/{cid}").json()["status"] == "scheduled"     # still waiting, nothing lost


def test_scheduler_api_and_default_off(client):
    status = client.get("/api/scheduler").json()
    assert status["enabled"] is False and status["ticks"] == 0
    tick = client.post("/api/scheduler/tick").json()
    assert set(tick) >= {"at", "started", "retried", "errors"}
    assert client.get("/api/scheduler").json()["ticks"] == 1
