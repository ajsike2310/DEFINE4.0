"""Clarify-once loop, headcount range and Exotel webhook path (fake REAL provider; no network)."""
import httpx

from member3.integrations.base import InitiateResult
from member3.integrations.exotel.provider import ExotelProvider
from member4.quality.conftest import add_recipient, new_campaign, new_event


def num(last2):
    return f"+155501001{last2}"        # last two digits pick the simulated scenario


def seed_run(client):
    c = client.post("/api/demo/seed").json()
    client.post(f"/api/campaigns/{c['id']}/start")
    for _ in range(3):
        if "error" in client.post(f"/api/campaigns/{c['id']}/retry-due", params={"force": True}).json():
            break
    return c


def outcomes(client, cid):
    return {r["external_ref"]: r for r in client.get(f"/api/campaigns/{cid}/recipients").json()}


def test_clarify_once_resolves_or_escalates(client):
    c = seed_run(client)
    o = outcomes(client, c["id"])
    assert o["SAMPLE-004"]["outcome"] == "unclear" and o["SAMPLE-010"]["outcome"] == "unclear"
    q = client.get("/api/followups/queue").json()
    assert {i["participant_ref"] for i in q if i["can_clarify"]} == {"SAMPLE-004", "SAMPLE-010"}

    res = client.post(f"/api/campaigns/{c['id']}/clarify").json()
    assert res["dispatched"] == 2
    o = outcomes(client, c["id"])
    assert o["SAMPLE-004"]["outcome"] == "confirmed"          # pressed 1 on the clarification call
    assert o["SAMPLE-010"]["outcome"] == "unclear"            # "hmm not sure" never becomes a confirmation
    q = {i["participant_ref"]: i for i in client.get("/api/followups/queue").json()}
    assert "SAMPLE-004" not in q                              # its review task was closed automatically
    assert q["SAMPLE-010"]["clarification_attempted"] and not q["SAMPLE-010"]["can_clarify"]
    assert "still unclear" in q["SAMPLE-010"]["note"]
    # exactly once: a second round does nothing and a direct request is refused
    again = client.post(f"/api/campaigns/{c['id']}/clarify").json()
    assert again["dispatched"] == 0
    rid = o["SAMPLE-010"]["id"]
    r = client.post(f"/api/recipients/{rid}/clarify")
    assert r.status_code == 409 and "already attempted" in r.json()["error"]["message"]
    atts = [a for a in client.get(f"/api/campaigns/{c['id']}/attempts").json() if a["mode"] == "clarify"]
    assert len(atts) == 2 and all(a["is_simulated"] for a in atts)
    an = client.get("/api/analytics", params={"campaign_id": c["id"]}).json()
    assert an["clarification"] == {"attempted": 2, "resolved": 1}


def test_clarify_call_not_answered_leaves_person_with_human(client):
    ev = new_event(client)
    c = new_campaign(client, event_id=ev["id"])
    r = add_recipient(client, c["id"], num("24"))           # main call: last digit 4 -> unclear; clarify: no answer
    client.post(f"/api/campaigns/{c['id']}/start")
    assert client.post(f"/api/recipients/{r['id']}/clarify").json()["dispatched"] == 1
    rec = client.get(f"/api/campaigns/{c['id']}/recipients").json()[0]
    assert rec["outcome"] == "unclear"                       # not "no_response", not confirmed
    f = client.get("/api/followups", params={"campaign_id": c["id"]}).json()
    assert len(f) == 1 and f[0]["status"] == "pending" and "no_answer" in f[0]["note"]
    assert client.post(f"/api/recipients/{r['id']}/clarify").status_code == 409     # chance used


def test_clarify_rules(client):
    ann = new_campaign(client, purpose="event_announcement")
    add_recipient(client, ann["id"], num("04"))
    client.post(f"/api/campaigns/{ann['id']}/start")
    rid = client.get(f"/api/campaigns/{ann['id']}/recipients").json()[0]["id"]
    r = client.post(f"/api/recipients/{rid}/clarify")
    assert r.status_code == 409 and "attendance campaigns only" in r.json()["error"]["message"]

    att = new_campaign(client)
    p = add_recipient(client, att["id"], num("04"))
    assert client.post(f"/api/recipients/{p['id']}/clarify").status_code == 409        # not unclear yet
    client.post(f"/api/campaigns/{att['id']}/start")
    client.post(f"/api/recipients/{p['id']}/opt-out")
    r = client.post(f"/api/recipients/{p['id']}/clarify")
    assert r.status_code == 409 and "opted out" in r.json()["error"]["message"]
    assert client.post("/api/recipients/9999/clarify").status_code == 404


def test_headcount_range_is_a_bound_not_a_prediction(client):
    c = seed_run(client)
    h = client.get("/api/analytics", params={"event_id": c["event_id"]}).json()["headcount"]
    assert h["participants"] == 11
    assert h["confirmed"] == 3 and h["declined"] == 1 and h["unknown"] == 7
    assert (h["floor"], h["ceiling"]) == (3, 10) and h["certainty"] == round(4 / 11, 4)
    assert h["unknown_breakdown"]["unclear"] == 2 and h["unknown_breakdown"]["opted_out"] == 1
    client.post(f"/api/campaigns/{c['id']}/clarify")
    h2 = client.get("/api/analytics", params={"event_id": c["event_id"]}).json()["headcount"]
    assert h2["floor"] == 4 and h2["certainty"] > h["certainty"]          # clarification narrowed the range
    # announcement campaigns never feed the attendance range
    e = new_event(client)
    ann = new_campaign(client, event_id=e["id"], purpose="event_announcement")
    add_recipient(client, ann["id"], num("00"))
    assert client.get("/api/analytics", params={"event_id": e["id"]}).json()["headcount"] is None


def test_headcount_prior_definite_answer_survives_a_later_pending_row(client):
    e = new_event(client)
    a, b = new_campaign(client, event_id=e["id"]), new_campaign(client, event_id=e["id"])
    add_recipient(client, a["id"], num("00"))                # confirmed in round 1
    add_recipient(client, b["id"], num("00"))                # round 2 not started: pending
    client.post(f"/api/campaigns/{a['id']}/start")
    h = client.get("/api/analytics", params={"event_id": e["id"]}).json()["headcount"]
    assert h["participants"] == 1 and h["confirmed"] == 1 and h["unknown"] == 0


def test_headcount_uses_latest_attendance_campaign_per_person(client):
    e = new_event(client)
    a, b = new_campaign(client, event_id=e["id"]), new_campaign(client, event_id=e["id"])
    add_recipient(client, a["id"], num("01"))                # declined in round 1
    add_recipient(client, b["id"], num("01"))
    client.post(f"/api/campaigns/{a['id']}/start")
    h = client.get("/api/analytics", params={"event_id": e["id"]}).json()["headcount"]
    assert h["participants"] == 1 and h["declined"] == 1 and h["ceiling"] == 0
    client.post(f"/api/campaigns/{b['id']}/start")           # same person, later campaign: declined again
    assert client.get("/api/analytics", params={"event_id": e["id"]}).json()["headcount"]["participants"] == 1


# ---- Exotel path with a fake REAL provider ---------------------------------------------------------
class FakeReal:
    name, is_simulated, supports_clarify = "exotel", False, True

    def __init__(self):
        self.modes = []

    def initiate_call(self, *, attempt_id, mode="main", **kw):
        self.modes.append(mode)
        return InitiateResult(f"CA{attempt_id}")

    def cancel_call(self, _):
        pass


def real_setup(client, monkeypatch):
    from member2.backend.app.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "call_provider", "exotel")
    monkeypatch.setattr(s, "exotel_webhook_token", "tok")
    fake = FakeReal()
    client.app_.state.provider_override = fake
    return fake


def test_passthru_digits_flow_and_quote_stripping(client, monkeypatch):
    real_setup(client, monkeypatch)
    c = new_campaign(client)
    add_recipient(client, c["id"], num("00"))
    client.post(f"/api/campaigns/{c['id']}/start")
    # Exotel Passthru: GET with query params, digits wrapped in double quotes
    r = client.get("/api/webhooks/exotel/response", params={"token": "tok", "CallSid": "CA1", "digits": '"1"', "CustomField": "1"})
    assert r.status_code == 200 and r.json()["result"] == "applied"
    rec = client.get(f"/api/campaigns/{c['id']}/recipients").json()[0]
    assert rec["outcome"] == "confirmed"
    dup = client.get("/api/webhooks/exotel/response", params={"token": "tok", "CallSid": "CA1", "digits": '"1"'})
    assert dup.json()["result"] == "duplicate"
    assert client.get("/api/webhooks/exotel/response", params={"token": "bad", "CallSid": "CA1", "digits": '"1"'}).status_code == 401
    # terminal StatusCallback (JSON) completes the call afterwards
    t = client.post("/api/webhooks/exotel?token=tok", json={"CallSid": "CA1", "Status": "completed", "Duration": "12"})
    assert t.json()["result"] == "applied"
    att = client.get(f"/api/campaigns/{c['id']}/attempts").json()[0]
    assert att["status"] == "completed" and att["is_simulated"] is False
    an = client.get("/api/analytics", params={"source": "real"}).json()
    assert an["totals"]["real_calls"] == 1 and an["outcomes"]["confirmed"] == 1


def test_passthru_finds_attempt_by_customfield_and_unknown_is_404(client, monkeypatch):
    real_setup(client, monkeypatch)
    c = new_campaign(client)
    add_recipient(client, c["id"], num("00"))
    client.post(f"/api/campaigns/{c['id']}/start")
    ok = client.get("/api/webhooks/exotel/response", params={"token": "tok", "CallSid": "DIFFERENT", "digits": '"2"', "CustomField": "1"})
    assert ok.status_code == 200
    assert client.get(f"/api/campaigns/{c['id']}/recipients").json()[0]["outcome"] == "declined"
    assert client.get("/api/webhooks/exotel/response", params={"token": "tok", "CallSid": "nope", "digits": '"1"'}).status_code == 404
    empty = client.get("/api/webhooks/exotel/response", params={"token": "tok", "CallSid": "CA1"})
    assert empty.json()["result"] == "duplicate" or "no digits" in empty.json()["result"] or empty.status_code == 200


def test_real_clarification_uses_clarify_mode(client, monkeypatch):
    fake = real_setup(client, monkeypatch)
    c = new_campaign(client)
    p = add_recipient(client, c["id"], num("04"))
    client.post(f"/api/campaigns/{c['id']}/start")
    client.get("/api/webhooks/exotel/response", params={"token": "tok", "CallSid": "CA1", "digits": '"7"'})   # unmapped key
    assert client.get(f"/api/campaigns/{c['id']}/recipients").json()[0]["outcome"] == "unclear"
    client.post("/api/webhooks/exotel?token=tok", json={"CallSid": "CA1", "Status": "completed"})
    assert client.post(f"/api/recipients/{p['id']}/clarify").json()["dispatched"] == 1
    assert fake.modes == ["main", "clarify"]
    client.get("/api/webhooks/exotel/response", params={"token": "tok", "CallSid": "CA2", "digits": '"1"'})
    assert client.get(f"/api/campaigns/{c['id']}/recipients").json()[0]["outcome"] == "confirmed"


def test_exotel_clarify_needs_its_own_flow():
    seen = []
    p = ExotelProvider(account_sid="s", api_key="k", api_token="t", caller_id="0800", flow_url="http://f/main",
                       clarify_flow_url="http://f/clarify",
                       client=httpx.Client(transport=httpx.MockTransport(
                           lambda r: seen.append(r.content.decode()) or httpx.Response(200, json={"Call": {"Sid": "x"}}))))
    p.initiate_call(attempt_id=1, attempt_number=2, to="+15550100104", language="en", message="", mode="clarify")
    assert "clarify" in seen[0] and "main" not in seen[0]
    q = ExotelProvider(account_sid="s", api_key="k", api_token="t", caller_id="0800", flow_url="http://f/main")
    assert q.supports_clarify is False


def test_get_call_status_uses_documented_call_details_path():
    seen = {}

    def h(req):
        seen["url"], seen["m"] = str(req.url), req.method
        return httpx.Response(200, json={"Call": {"Sid": "CA9", "Status": "completed"}})

    p = ExotelProvider(account_sid="sid", api_key="k", api_token="t", caller_id="0800", flow_url="http://f",
                       client=httpx.Client(transport=httpx.MockTransport(h)))
    assert p.get_call_status("CA9")["Status"] == "completed"
    assert seen == {"url": "https://api.exotel.com/v1/Accounts/sid/Calls/CA9.json", "m": "GET"}


def test_exotel_readiness_lists_names_never_values(client, monkeypatch):
    from member2.backend.app.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "exotel_api_token", "SUPER-SECRET")
    monkeypatch.setattr(s, "public_base_url", "https://abc.example")
    body = client.get("/api/settings/exotel-readiness").json()
    assert "SUPER-SECRET" not in str(body)
    byname = {c["name"]: c for c in body["checks"]}
    assert byname["EXOTEL_API_TOKEN"]["ok"] is True and byname["EXOTEL_API_KEY"]["ok"] is False
    assert body["ready"] is False
    assert body["urls"]["passthru_response"] == "https://abc.example/api/webhooks/exotel/response?token=<EXOTEL_WEBHOOK_TOKEN>"
