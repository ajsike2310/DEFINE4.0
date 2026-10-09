"""Health, request ids, logging hygiene, rate limit, config validation, pagination."""
import logging

import pytest
from pydantic import ValidationError

from member2.backend.app.core.config import Settings, get_settings
from member2.backend.app.core.ratelimit import SlidingWindowLimiter

from .conftest import add_recipient, new_campaign, new_event


# ---- limiter -----------------------------------------------------------------------------------
def test_limiter_allows_up_to_the_limit_then_reports_wait_and_recovers():
    t = [0.0]
    lim = SlidingWindowLimiter(2, 10, clock=lambda: t[0])
    assert lim.hit("a") is None and lim.hit("a") is None
    wait = lim.hit("a")
    assert wait is not None and 1 <= wait <= 11
    assert lim.hit("b") is None                       # other clients are independent
    t[0] = 10.5
    assert lim.hit("a") is None                       # window slid


def test_public_signup_is_throttled_but_organiser_entries_are_not(client):
    client.app_.state.signup_limiter = SlidingWindowLimiter(2, 600)
    ev = new_event(client)["id"]

    def signup(i, source="registration_form"):
        return client.post(f"/api/events/{ev}/leads", json={"name": "Sign Up", "phone": f"+91987654321{i}",
                                                            "source": source, "consent_status": "granted"})
    assert signup(0).status_code == 201 and signup(1).status_code == 201
    blocked = signup(2)
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) >= 1
    assert signup(3, source="manual").status_code == 201          # organiser typing leads in is not throttled


# ---- health / request id / logs ------------------------------------------------------------------
def test_health_reports_state_without_secrets(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["database"] == "ok" and h["provider"] == "demo" and h["uptime_seconds"] >= 0
    assert set(h["scheduler"]) == {"enabled", "ticks", "last_tick_at"} and isinstance(h["voice_configured"], bool)
    assert "key" not in str(h).lower().replace("voice_configured", "")


def test_request_id_is_echoed_or_generated_and_bad_ids_are_replaced(client):
    assert client.get("/api/health", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"
    generated = client.get("/api/health").headers["x-request-id"]
    assert len(generated) == 12
    evil = client.get("/api/health", headers={"X-Request-ID": "bad id\twith spaces"}).headers["x-request-id"]
    assert evil != "bad id\twith spaces" and len(evil) == 12


def test_access_log_never_contains_query_strings(client, caplog, monkeypatch):
    monkeypatch.setattr(get_settings(), "exotel_webhook_token", "TOPSECRET")
    with caplog.at_level(logging.INFO, logger="access"):
        client.post("/api/webhooks/exotel?token=TOPSECRET", json={"CallSid": "x", "Status": "completed"})
        client.get("/api/events?x=+919876543210")
    text = " ".join(r.getMessage() for r in caplog.records if r.name == "access")
    assert "/api/webhooks/exotel" in text and "TOPSECRET" not in text and "9876543210" not in text


def test_unknown_route_and_validation_use_the_error_envelope(client):
    nf = client.get("/api/nope")
    assert nf.status_code == 404 and nf.json()["error"]["code"] == "http_error"
    bad = client.post("/api/events", json={"name": "x"})
    assert bad.status_code == 422 and bad.json()["error"]["details"][0]["field"] == "name"


# ---- config ------------------------------------------------------------------------------------
@pytest.mark.parametrize("field,value", [("call_provider", "twilio"), ("max_call_attempts", 0), ("max_call_attempts", 9),
                                         ("retry_backoff_minutes", -1), ("scheduler_interval_seconds", 1)])
def test_bad_settings_fail_fast(field, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_cors_list_is_trimmed():
    assert Settings(cors_origins=" http://a.test , http://b.test ,").cors_list == ["http://a.test", "http://b.test"]


# ---- pagination ---------------------------------------------------------------------------------
def test_recipients_are_paged_in_order_and_limits_are_validated(client):
    cid = new_campaign(client)["id"]
    for i in range(5):
        add_recipient(client, cid, f"+91987654320{i}")
    page = client.get("/api/recipients", params={"campaign_id": cid, "limit": 2, "offset": 1}).json()
    everything = client.get("/api/recipients", params={"campaign_id": cid}).json()
    assert [r["id"] for r in page] == [r["id"] for r in everything][1:3] and len(everything) == 5
    assert client.get("/api/recipients", params={"limit": 0}).status_code == 422
    assert client.get("/api/recipients", params={"limit": 501}).status_code == 422
    assert client.get("/api/recipients", params={"offset": -1}).status_code == 422


def test_retry_eligible_filter_matches_the_rule(client):
    cid = new_campaign(client)["id"]
    add_recipient(client, cid, "+919876543218")        # busy -> technical failure -> retry eligible
    add_recipient(client, cid, "+919876543210")        # confirms -> not eligible
    client.post(f"/api/campaigns/{cid}/start")
    rows = client.get("/api/recipients", params={"campaign_id": cid, "retry_eligible": True}).json()
    assert [r["phone"] for r in rows] == ["+919876543218"]
