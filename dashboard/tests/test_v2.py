"""The API served for the React frontend (/api/v2): shapes must match the frontend's own fixtures, and the flows must work."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.config import Settings
from dashboard.main import create_app

FIX = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures"
V = "/api/v2"


@pytest.fixture
def client():
    s = Settings(call_provider="demo", db_path=":memory:", dial_interval_s=0, call_window="", scheduler_interval_s=0.2)
    with TestClient(create_app(s, start_reconciler=True)) as c:
        yield c


def wait_campaign(client, cid, until=("completed", "cancelled"), timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        c = client.get(f"{V}/campaigns/{cid}").json()
        if c["status"] in until:
            return c
        time.sleep(0.1)
    raise AssertionError(f"campaign never reached {until}: {c['status']}")


def fixture(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def assert_superset(actual, expected, path="$"):
    """Every key the frontend fixture has must be present, recursively for objects (and the first item of lists)."""
    if isinstance(expected, dict) and expected and isinstance(actual, dict):
        for k, v in expected.items():
            assert k in actual, f"{path}.{k} missing from the API response"
            if k not in ("outcomes", "unknown_breakdown", "by_status", "approved_info", "messages", "by_source"):
                assert_superset(actual[k], v, f"{path}.{k}")
    elif isinstance(expected, list) and expected and isinstance(actual, list) and actual:
        assert_superset(actual[0], expected[0], path + "[0]")


def test_react_app_contract_matches_the_frontend_fixtures(client):
    seeded = client.post(f"{V}/demo/seed-all?run=true").json()
    assert seeded["ran"] and len(seeded["events"]) == 3
    for c in seeded["campaigns"]:
        wait_campaign(client, c["id"])
    client.post(f"{V}/demo/seed-leads")
    eid = seeded["events"][0]["id"]
    cid = seeded["campaigns"][0]["id"]
    q = client.get(f"{V}/followups/queue").json()
    rid = client.get(f"{V}/campaigns/{cid}/recipients").json()[0]["id"]
    checks = {
        "events": f"{V}/events", "campaigns": f"{V}/campaigns", "campaign": f"{V}/campaigns/{cid}",
        "recipients": f"{V}/campaigns/{cid}/recipients", "attempts": f"{V}/campaigns/{cid}/attempts",
        "intents": f"{V}/campaigns/{cid}/intents", "followups": f"{V}/followups", "queue": f"{V}/followups/queue",
        "analytics": f"{V}/analytics?event_id={eid}", "overview": f"{V}/campaigns/overview", "settings": f"{V}/settings",
        "exotel": f"{V}/settings/exotel-readiness", "voice": f"{V}/voice/status", "history": f"{V}/recipients/{rid}/history",
        "leads": f"{V}/events/{eid}/leads", "lead_summary": f"{V}/events/{eid}/leads/summary", "participants": f"{V}/recipients",
    }
    for name, url in checks.items():
        r = client.get(url)
        assert r.status_code == 200, (name, r.text)
        exp = fixture(name)
        if name == "history":
            exp = {k: exp[k] for k in ("recipient", "attempts", "intents", "followups")}
        assert_superset(r.json(), exp, name)
    assert q, "the sample simulation should leave people for a human"


def test_sample_data_never_uses_the_real_provider(client):
    eng = client.app.state.engine
    eng.provider.is_simulated = False                      # pretend the configured provider is a real one
    eng.provider.initiate_call = lambda **kw: (_ for _ in ()).throw(AssertionError("sample call reached the real provider"))
    try:
        seeded = client.post(f"{V}/demo/seed-all?run=true").json()
        for c in seeded["campaigns"]:
            wait_campaign(client, c["id"])
    finally:
        eng.provider.is_simulated = True


def test_event_campaign_and_recipient_lifecycle(client):
    ev = client.post(f"{V}/events", json={"name": "Hack Night", "approved_info": {"venue": "Lab 3", "schedule": "Sat 10:00"}}).json()
    assert ev["approved_info"] == {"venue": "Lab 3", "schedule": "Sat 10:00"} and ev["campaign_count"] == 0
    assert client.patch(f"{V}/events/{ev['id']}", json={"description": "A hackathon"}).json()["description"] == "A hackathon"
    body = {"event_id": ev["id"], "name": "Confirm", "purpose": "attendance_confirmation", "languages": ["en", "hi"],
            "messages": {"en": "Hello {first_name}, will you attend {event}?", "hi": "नमस्ते {first_name}, क्या आप आएँगे?"}, "max_attempts": 2}
    camp = client.post(f"{V}/campaigns", json=body).json()
    assert camp["status"] == "draft" and camp["languages"] == ["en", "hi"] and camp["recipient_count"] == 0
    # validation errors use the envelope the frontend reads
    bad = client.post(f"{V}/campaigns", json={**body, "name": "x"})
    assert bad.status_code == 422 and bad.json()["error"]["details"][0]["field"] == "name"
    assert client.post(f"{V}/campaigns", json={**body, "languages": ["ml"], "messages": {"ml": "x"}}).json()["error"]["message"].startswith("Language not supported")
    # recipients: one with consent (and a personal message), one without
    ok = client.post(f"{V}/campaigns/{camp['id']}/recipients", json={"name": "Asha Rao", "phone": "9876543210", "preferred_language": "hi",
                                                                      "consent_status": "granted", "message": "Hi {first_name}, saved you a seat. Coming?"})
    assert ok.status_code == 201 and ok.json()["consent_status"] == "granted" and ok.json()["message"].startswith("Hi {first_name}")
    nc = client.post(f"{V}/campaigns/{camp['id']}/recipients", json={"name": "No Consent", "phone": "9876543211", "consent_status": "unknown"}).json()
    assert nc["consent_status"] == "unknown"
    assert client.post(f"{V}/campaigns/{camp['id']}/recipients", json={"name": "A", "phone": "9876543210"}).status_code == 409
    assert client.post(f"{V}/campaigns/{camp['id']}/recipients", json={"name": "A", "phone": "12"}).status_code == 422
    start = client.post(f"{V}/campaigns/{camp['id']}/start").json()
    assert start["dispatched"] == 1 and start["skipped"][0]["reason"] == "consent not confirmed"
    done = wait_campaign(client, camp["id"])
    recs = {r["name"]: r for r in client.get(f"{V}/campaigns/{camp['id']}/recipients").json()}
    assert recs["Asha Rao"]["outcome"] == "confirmed" and recs["No Consent"]["outcome"] == "pending" and done["status"] == "completed"
    assert client.get(f"{V}/analytics?campaign_id={camp['id']}").json()["headcount"]["confirmed"] == 1
    # the personal message and per-language script were actually used
    att = client.get(f"{V}/campaigns/{camp['id']}/attempts").json()
    assert len(att) == 1 and att[0]["status"] == "completed" and att[0]["is_simulated"] is True
    call = client.app.state.db.one("SELECT message FROM calls WHERE id=?", (recs["Asha Rao"]["id"],))
    assert call["message"].startswith("Hi Asha, saved you a seat")


def test_per_language_scripts_follow_the_person(client):
    ev = client.post(f"{V}/events", json={"name": "Lang test"}).json()
    camp = client.post(f"{V}/campaigns", json={"event_id": ev["id"], "name": "Lang", "languages": ["en", "ta"],
                                               "messages": {"en": "Hello {first_name}, will you come?", "ta": "வணக்கம் {first_name}, வருவீர்களா?"}}).json()
    for n, ph, lang in (("Eve", "9000000000", None), ("Tam", "9000000010", "ta")):
        client.post(f"{V}/campaigns/{camp['id']}/recipients", json={"name": n, "phone": ph, "preferred_language": lang, "consent_status": "granted"})
    client.post(f"{V}/campaigns/{camp['id']}/start"); wait_campaign(client, camp["id"])
    msgs = {r["name"]: r["message"] for r in client.app.state.db.q("SELECT p.name, c.message FROM calls c JOIN participants p ON p.id=c.participant_id")}
    assert msgs["Eve"] == "Hello Eve, will you come?" and msgs["Tam"].startswith("வணக்கம் Tam")


def test_csv_import_without_the_multipart_package(client):
    ev = client.post(f"{V}/events", json={"name": "CSV"}).json()
    camp = client.post(f"{V}/campaigns", json={"event_id": ev["id"], "name": "C1", "languages": ["en"], "messages": {"en": "Hi?"}}).json()
    csv = "name,phone,language,segment,participant_id,opted_out\nA One,9100000000,en,Students,P-1,\nB Two,9100000001,hi,Staff,P-2,yes\nBad,12,en,,,\n"
    r = client.post(f"{V}/campaigns/{camp['id']}/recipients/import", files={"file": ("p.csv", csv, "text/csv")}, data={"consent_confirmed": "true"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["imported"] == 2 and out["rejected"] == 1 and out["errors"][0]["line"] == 4
    recs = {x["name"]: x for x in client.get(f"{V}/campaigns/{camp['id']}/recipients").json()}
    assert recs["A One"]["consent_status"] == "granted" and recs["A One"]["external_ref"] == "P-1" and recs["B Two"]["opted_out"] is True
    # without the consent tick, people are stored as unknown and skipped at launch
    camp2 = client.post(f"{V}/campaigns", json={"event_id": ev["id"], "name": "C2", "languages": ["en"], "messages": {"en": "Hi?"}}).json()
    client.post(f"{V}/campaigns/{camp2['id']}/recipients/import", files={"file": ("p.csv", "name,phone\nZed,9100000009\n", "text/csv")}, data={"consent_confirmed": "false"})
    assert client.post(f"{V}/campaigns/{camp2['id']}/start").json()["dispatched"] == 0
    # reuse participants from the first campaign: opted out and no-consent people are not copied
    cp = client.post(f"{V}/campaigns/{camp2['id']}/recipients/copy-from/{camp['id']}").json()
    assert cp["copied"] == 1 and cp["skipped"] == 1


def test_cancel_schedule_duplicate_delete(client):
    ev = client.post(f"{V}/events", json={"name": "Life"}).json()
    camp = client.post(f"{V}/campaigns", json={"event_id": ev["id"], "name": "Camp L", "languages": ["en"], "messages": {"en": "Hi?"}}).json()
    client.post(f"{V}/campaigns/{camp['id']}/recipients", json={"name": "A", "phone": "9000000000", "consent_status": "granted"})
    soon = (time.time() + 1.2)
    from datetime import datetime, timezone
    at = datetime.fromtimestamp(soon, timezone.utc).isoformat()
    assert client.post(f"{V}/campaigns/{camp['id']}/schedule", json={"scheduled_at": at}).json()["status"] == "scheduled"
    done = wait_campaign(client, camp["id"], until=("completed",), timeout=10)          # the scheduler starts it by itself
    assert done["scheduled_at"] is None
    dup = client.post(f"{V}/campaigns/{camp['id']}/duplicate", json={"name": "L2", "copy_participants": True}).json()
    assert dup["campaign"]["name"] == "L2" and dup["copied"] == 1 and dup["campaign"]["status"] == "draft"
    assert client.post(f"{V}/campaigns/{dup['campaign']['id']}/cancel").json()["status"] == "cancelled"
    assert client.post(f"{V}/campaigns/{dup['campaign']['id']}/start").status_code == 409
    assert client.delete(f"{V}/campaigns/{dup['campaign']['id']}").json() == {"deleted": dup["campaign"]["id"]}
    assert client.post(f"{V}/campaigns/{camp['id']}/schedule", json={"scheduled_at": "2000-01-01T00:00:00Z"}).status_code in (409, 422)


def test_followups_opt_out_and_calling_hours(client):
    ev = client.post(f"{V}/events", json={"name": "FU"}).json()
    camp = client.post(f"{V}/campaigns", json={"event_id": ev["id"], "name": "Camp F", "languages": ["en"], "messages": {"en": "Hi?"}, "max_attempts": 1}).json()
    for n, ph in (("Unsure", "9100000004"), ("Callback", "9100000003"), ("Quits", "9100000005")):
        client.post(f"{V}/campaigns/{camp['id']}/recipients", json={"name": n, "phone": ph, "consent_status": "granted"})
    client.post(f"{V}/campaigns/{camp['id']}/start"); wait_campaign(client, camp["id"])
    queue = {i["participant_name"]: i for i in client.get(f"{V}/followups/queue?event_id={ev['id']}").json()}
    assert set(queue) == {"Unsure", "Callback"} and queue["Unsure"]["action_type"] == "human_review" and queue["Callback"]["action_type"] == "callback"
    assert queue["Unsure"]["priority"] <= queue["Callback"]["priority"]
    fid = queue["Callback"]["followup_id"]
    assert client.patch(f"{V}/followups/{fid}", json={"status": "completed"}).json()["status"] == "completed"
    recs = {r["name"]: r for r in client.get(f"{V}/campaigns/{camp['id']}/recipients").json()}
    assert recs["Quits"]["outcome"] == "opted_out" and recs["Quits"]["opted_out"]
    # recording an opt-out cancels that person's open follow-ups
    assert client.post(f"{V}/recipients/{recs['Unsure']['id']}/opt-out").json()["opted_out"] is True
    assert client.get(f"{V}/followups/queue?event_id={ev['id']}").json() == []
    assert client.get(f"{V}/recipients?opted_out=true").json().__len__() == 2
    # calling hours are editable from the React app too
    h = client.put(f"{V}/settings/calling-hours", json={"enabled": True, "start": "09:00", "end": "21:00"}).json()
    assert h["calling_hours"] == {"enabled": True, "start": "09:00", "end": "21:00"}
    assert client.put(f"{V}/settings/calling-hours", json={"enabled": True, "start": "21:00", "end": "09:00"}).status_code == 409


def test_leads_flow(client):
    ev = client.post(f"{V}/events", json={"name": "Leads"}).json()
    camp = client.post(f"{V}/campaigns", json={"event_id": ev["id"], "name": "Camp C", "languages": ["en"], "messages": {"en": "Hi?"}}).json()
    a = client.post(f"{V}/events/{ev['id']}/leads", json={"name": "Lena", "phone": "9300000000", "source": "registration_form", "consent_status": "granted", "interest": "AI"})
    assert a.status_code == 201 and a.json()["score"] >= 80
    b = client.post(f"{V}/events/{ev['id']}/leads", json={"name": "Ned", "phone": "9300000001", "consent_status": "unknown"}).json()
    assert client.post(f"{V}/events/{ev['id']}/leads", json={"name": "Dup", "phone": "9300000000"}).status_code == 409
    s = client.get(f"{V}/events/{ev['id']}/leads/summary").json()
    assert s["total"] == 2 and s["ready_to_convert"] == 1
    conv = client.post(f"{V}/leads/convert", json={"campaign_id": camp["id"], "lead_ids": [a.json()["id"], b["id"]]}).json()
    assert conv["converted"] == 1 and conv["skipped"][0]["reason"] == "consent not granted"
    assert client.get(f"{V}/campaigns/{camp['id']}/recipients").json()[0]["name"] == "Lena"
    assert client.patch(f"{V}/leads/{b['id']}", json={"status": "lost"}).json()["status"] == "lost"


def test_existing_dashboard_api_is_untouched_and_token_protects_v2():
    s = Settings(call_provider="demo", db_path=":memory:", dashboard_token="tok", call_window="")
    with TestClient(create_app(s, start_reconciler=False)) as c:
        assert c.get("/api/events").status_code == 401 and c.get(f"{V}/events").status_code == 401
        h = {"Authorization": "Bearer tok"}
        assert c.get("/api/events", headers=h).json() == [] and c.get(f"{V}/events", headers=h).json() == []
        assert c.get("/app").status_code in (200, 404)             # served (404 only until the frontend is built)


def test_exotel_status_webhook_works_without_the_multipart_package():
    s = Settings(call_provider="demo", db_path=":memory:", exotel_webhook_token="hook", call_window="")
    with TestClient(create_app(s, start_reconciler=False)) as c:
        assert c.post("/api/webhooks/exotel?token=wrong", data={"CallSid": "x", "Status": "busy"}).status_code == 401
        assert c.post("/api/webhooks/exotel?token=hook", data={"CallSid": "x", "Status": "busy"}).json() == {"ok": True}
