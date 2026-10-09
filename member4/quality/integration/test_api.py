"""API/service integration tests using the SIMULATED demo provider. They prove the
workflow wiring, not real-world telephony or language performance."""
from member4.quality.conftest import add_recipient, new_campaign


def P(d):  # fictional 555-01xx numbers; last digit selects the demo scenario
    return f"+1555010010{d}"


def start(client, cid):
    r = client.post(f"/api/campaigns/{cid}/start")
    assert r.status_code == 200, r.text
    return r.json()


def recipients(client, cid):
    return {r["phone"]: r for r in client.get(f"/api/campaigns/{cid}/recipients").json()}


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_campaign_validation(client):
    r = client.post("/api/campaigns", json={"name": "x", "messages": {}, "languages": ["en"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = client.post("/api/campaigns", json={"name": "Valid", "messages": {"en": "hi"}, "languages": ["en", "ml"]})
    assert r.status_code == 422  # missing ml message
    r = client.post("/api/campaigns", json={"name": "Valid", "messages": {"fr": "x"}, "languages": ["fr"]})
    assert r.status_code == 422


def test_recipient_validation_and_duplicates(client):
    c = new_campaign(client)
    bad = client.post(f"/api/campaigns/{c['id']}/recipients", json={"name": "A", "phone": "12345"})
    assert bad.status_code == 422
    add_recipient(client, c["id"], P(0))
    dup = client.post(f"/api/campaigns/{c['id']}/recipients", json={"name": "B", "phone": P(0)})
    assert dup.status_code == 409


def test_csv_import(client):
    c = new_campaign(client)
    csv_data = "name,phone,language\nAsha,+15550100100,en\nBad,notaphone,en\nDup,+15550100100,en\n"
    r = client.post(f"/api/campaigns/{c['id']}/recipients/import", data={"consent_confirmed": "true"},
                    files={"file": ("r.csv", csv_data, "text/csv")})
    body = r.json()
    assert body["imported"] == 1 and body["rejected"] == 2
    assert recipients(client, c["id"])[P(0)]["consent_status"] == "granted"
    bad = client.post(f"/api/campaigns/{c['id']}/recipients/import", files={"file": ("r.csv", "a,b\n1,2\n", "text/csv")})
    assert bad.status_code == 422


def test_full_flow_outcomes(client):
    c = new_campaign(client, languages=["en", "ml"], messages={"en": "hi", "ml": "ഹായ്"})
    for d in range(10):
        add_recipient(client, c["id"], P(d))
    res = start(client, c["id"])
    assert res["dispatched"] == 10
    rec = recipients(client, c["id"])
    assert rec[P(0)]["outcome"] == "confirmed"
    assert rec[P(1)]["outcome"] == "declined"
    assert rec[P(2)]["outcome"] == "confirmed"          # Malayalam
    assert rec[P(3)]["outcome"] == "callback_requested"
    assert rec[P(4)]["outcome"] == "unclear"            # never silently confirmed
    assert rec[P(5)]["outcome"] == "opted_out" and rec[P(5)]["opted_out"] is True
    assert rec[P(9)]["outcome"] == "information_requested"
    attempts = client.get(f"/api/campaigns/{c['id']}/attempts").json()
    assert all(a["is_simulated"] and a["provider"] == "demo" for a in attempts)
    fus = client.get("/api/followups", params={"campaign_id": c["id"]}).json()
    kinds = {(f["action_type"], f["status"]) for f in fus}
    assert ("callback", "pending") in kinds          # "tomorrow" has no reliable time -> stays pending
    assert ("human_review", "pending") in kinds


def test_retry_policy(client):
    c = new_campaign(client)
    for d in (6, 7, 8):
        add_recipient(client, c["id"], P(d))
    start(client, c["id"])
    rec = recipients(client, c["id"])
    assert all(r["outcome"] == "pending" for r in rec.values())   # retries still available
    # not due yet (backoff) -> nothing dispatched
    assert client.post(f"/api/campaigns/{c['id']}/retry-due").json()["dispatched"] == 0
    for _ in range(3):
        client.post(f"/api/campaigns/{c['id']}/retry-due", params={"force": True})
    rec = recipients(client, c["id"])
    assert rec[P(6)]["outcome"] == "confirmed"        # succeeded on attempt 2 (keypad 1)
    assert rec[P(7)]["outcome"] == "no_response" and rec[P(8)]["outcome"] == "no_response"
    attempts = client.get(f"/api/campaigns/{c['id']}/attempts").json()
    per = {}
    for a in attempts:
        per.setdefault(a["recipient_id"], []).append(a)
    assert max(len(v) for v in per.values()) == 3     # bounded by max_attempts
    assert len(per[rec[P(6)]["id"]]) == 2             # no calls after resolution
    assert client.get(f"/api/campaigns/{c['id']}").json()["status"] == "completed"


def test_no_duplicate_dispatch_on_restart(client):
    c = new_campaign(client)
    add_recipient(client, c["id"], P(0))
    add_recipient(client, c["id"], P(6))      # no-answer -> retry pending, keeps campaign running
    start(client, c["id"])
    again = start(client, c["id"])            # must not re-call anyone or bypass retry backoff
    assert again["dispatched"] == 0
    assert len(client.get(f"/api/campaigns/{c['id']}/attempts").json()) == 2
    # once everything is resolved the campaign is completed and cannot be started again
    client.post(f"/api/campaigns/{c['id']}/retry-due", params={"force": True})
    assert client.post(f"/api/campaigns/{c['id']}/start").status_code == 409


def test_consent_and_opt_out_block_calls(client):
    c = new_campaign(client)
    add_recipient(client, c["id"], P(0), consent="unknown")
    r2 = add_recipient(client, c["id"], P(1))
    client.post(f"/api/recipients/{r2['id']}/opt-out")
    res = start(client, c["id"])
    assert res["dispatched"] == 0 and {s["reason"] for s in res["skipped"]} == {"consent not granted", "opted out"}


def test_duplicate_webhook_events(client):
    c = new_campaign(client)
    add_recipient(client, c["id"], P(3))
    start(client, c["id"])
    att = client.get(f"/api/campaigns/{c['id']}/attempts").json()[0]
    ev = {"event_id": "dup-1", "provider_call_id": att["provider_call_id"], "kind": "response", "text": "yes"}
    # attempt already completed -> response ignored, and a repeated id is a duplicate
    first = client.post("/api/webhooks/demo", json=ev).json()["result"]
    second = client.post("/api/webhooks/demo", json=ev).json()["result"]
    assert second == "duplicate" and first != "duplicate"
    # the already-recorded callback outcome is not flipped by the late event
    assert recipients(client, c["id"])[P(3)]["outcome"] == "callback_requested"
    assert len(client.get(f"/api/campaigns/{c['id']}/intents").json()) == 1


def test_opt_out_cancels_followups_and_survives_later_response(client):
    c = new_campaign(client)
    r = add_recipient(client, c["id"], P(3))
    start(client, c["id"])
    assert client.get("/api/followups", params={"status": "pending"}).json()
    client.post(f"/api/recipients/{r['id']}/opt-out")
    assert not client.get("/api/followups", params={"status": "pending"}).json()
    assert client.patch(f"/api/followups/{client.get('/api/followups').json()[0]['id']}",
                        json={"status": "scheduled", "scheduled_at": "2030-01-01T10:00:00+05:30"}).status_code == 409


def test_state_transition_errors(client):
    c = new_campaign(client)
    assert client.post(f"/api/campaigns/{c['id']}/start").status_code == 422   # no recipients
    add_recipient(client, c["id"], P(0))
    start(client, c["id"])
    assert client.post(f"/api/campaigns/{c['id']}/cancel").status_code in (200, 409)
    assert client.get("/api/campaigns/999").status_code == 404
    assert client.get("/api/campaigns/999").json()["error"]["code"] == "not_found"


def test_demo_campaign_never_uses_real_provider(client):
    seeded = client.post("/api/demo/seed").json()
    assert seeded["is_demo"]
    start(client, seeded["id"])
    assert all(a["is_simulated"] for a in client.get(f"/api/campaigns/{seeded['id']}/attempts").json())
    assert client.delete("/api/demo").json()["deleted_campaigns"] == 1
    assert client.get("/api/campaigns").json() == []


def test_exotel_webhook_requires_token(client):
    assert client.post("/api/webhooks/exotel", json={"CallSid": "x", "Status": "completed"}).status_code == 503
