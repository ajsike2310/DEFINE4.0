"""Event-communication workflow tests (simulated provider unless stated)."""
import pytest

from member3.integrations.base import InitiateResult
from member4.quality.conftest import add_recipient, new_campaign, new_event


def P(d):
    return f"+1555010010{d}"


def run(client, cid, retries=3):
    assert client.post(f"/api/campaigns/{cid}/start").status_code == 200
    for _ in range(retries):
        if "error" in client.post(f"/api/campaigns/{cid}/retry-due", params={"force": True}).json():
            break


def outcomes(client, cid):
    return {r["phone"]: r["outcome"] for r in client.get(f"/api/campaigns/{cid}/recipients").json()}


def test_event_crud_and_validation(client):
    e = new_event(client, name="DEFINE 4.0 sample", approved_info={"venue": "  MBCET  ", "schedule": ""})
    assert e["approved_info"] == {"venue": "MBCET"}          # blanks dropped, trimmed
    assert client.post("/api/events", json={"name": "X", "approved_info": {"parking": "A"}}).status_code == 422
    p = client.patch(f"/api/events/{e['id']}", json={"approved_info": {"venue": "Hall B", "schedule": "10am"}})
    assert p.json()["approved_info"]["schedule"] == "10am"
    assert client.get("/api/events/999").status_code == 404


def test_campaign_belongs_to_event(client):
    e1, e2 = new_event(client, name="Event One"), new_event(client, name="Event Two")
    c = new_campaign(client, event_id=e1["id"])
    new_campaign(client, event_id=e2["id"])
    assert c["event_id"] == e1["id"]
    assert [x["id"] for x in client.get("/api/campaigns", params={"event_id": e1["id"]}).json()] == [c["id"]]
    bad = client.post("/api/campaigns", json={"event_id": 999, "name": "Nope", "messages": {"en": "x"}, "languages": ["en"]})
    assert bad.status_code == 404
    old = client.post("/api/campaigns", json={"event_id": e1["id"], "name": "Old", "purpose": "payment_reminder",
                                              "messages": {"en": "x"}, "languages": ["en"]})
    assert old.status_code == 422


def test_yes_is_attendance_only_for_attendance_campaigns(client):
    att = new_campaign(client)
    ann = new_campaign(client, purpose="event_announcement")
    for c in (att, ann):
        add_recipient(client, c["id"], P(0))
        client.post(f"/api/campaigns/{c['id']}/start")
    assert outcomes(client, att["id"])[P(0)] == "confirmed"
    assert outcomes(client, ann["id"])[P(0)] == "acknowledged"     # not an attendance confirmation
    a = client.get("/api/analytics", params={"campaign_id": ann["id"]}).json()
    assert a["outcomes"]["confirmed"] == 0 and a["outcomes"]["acknowledged"] == 1


def test_callback_after_5pm_is_pending_with_note_not_scheduled(client):
    c = new_campaign(client)
    add_recipient(client, c["id"], P(3))
    run(client, c["id"])
    f = client.get("/api/followups", params={"campaign_id": c["id"]}).json()[0]
    assert f["action_type"] == "callback" and f["status"] == "pending" and f["scheduled_at"] is None
    assert "after 5 PM" in f["note"] and "date not confirmed" in f["note"]


def test_info_request_uses_only_approved_info(client):
    with_info = new_event(client, name="With info", approved_info={"venue": "MBCET, Thiruvananthapuram"})
    without = new_event(client, name="No info")
    c1, c2 = new_campaign(client, event_id=with_info["id"]), new_campaign(client, event_id=without["id"])
    for c in (c1, c2):
        add_recipient(client, c["id"], P(9))          # "Where is the venue?"
        client.post(f"/api/campaigns/{c['id']}/start")
    f1 = client.get("/api/followups", params={"campaign_id": c1["id"]}).json()[0]
    f2 = client.get("/api/followups", params={"campaign_id": c2["id"]}).json()[0]
    assert f1["action_type"] == "send_information" and "MBCET, Thiruvananthapuram" in f1["note"]
    assert f2["action_type"] == "human_review" and "no approved event information" in f2["note"]


class Scripted:
    """Simulated provider answering with a fixed spoken sentence."""
    name, is_simulated = "demo", True

    def __init__(self, text):
        self.text = text

    def initiate_call(self, *, attempt_id, **kw):
        from member3.integrations.base import ProviderEvent
        cid = f"s-{attempt_id}"
        return InitiateResult(cid, [ProviderEvent(f"{cid}:a", cid, "status", "answered"),
                                    ProviderEvent(f"{cid}:r", cid, "response", text=self.text),
                                    ProviderEvent(f"{cid}:c", cid, "status", "completed")])

    def cancel_call(self, _):
        pass


def test_schedule_question_with_only_venue_configured_goes_to_human(client):
    e = new_event(client, approved_info={"venue": "MBCET"})        # no schedule approved
    c = new_campaign(client, event_id=e["id"])
    add_recipient(client, c["id"], P(0))
    client.app_.state.provider_override = Scripted("What time does it start?")
    # sample/simulated campaigns use DemoProvider, so bypass: patch the campaign to non-demo path
    import member2.backend.app.api.routes as routes
    orig = routes.provider_for
    routes.provider_for = lambda request, campaign: request.app.state.provider_override
    try:
        client.post(f"/api/campaigns/{c['id']}/start")
    finally:
        routes.provider_for = orig
    f = client.get("/api/followups", params={"campaign_id": c["id"]}).json()[0]
    assert f["action_type"] == "human_review" and "no approved event information" in f["note"]
    assert "venue" not in f["note"].replace("MBCET", "")            # nothing invented


def test_followup_queue_priority_and_enrichment(client):
    e = new_event(client, approved_info={"venue": "MBCET"})
    c = new_campaign(client, event_id=e["id"])
    for d in (3, 4, 9):                       # callback, unclear, info request
        add_recipient(client, c["id"], P(d), external_ref=f"PX-{d}")
    run(client, c["id"])
    q = client.get("/api/followups/queue", params={"event_id": e["id"]}).json()
    assert len(q) == 3
    assert [i["priority"] for i in q] == sorted(i["priority"] for i in q)
    kinds = {i["participant_ref"]: i for i in q}
    assert kinds["PX-4"]["action_type"] == "human_review" and kinds["PX-4"]["priority"] == 2
    assert kinds["PX-9"]["priority"] == 3 and kinds["PX-9"]["recommended_action"]
    assert all(i["is_simulated"] for i in q) and kinds["PX-4"]["latest_outcome"] == "unclear"
    # completing removes it from the open queue; opt-out cancels the rest
    client.patch(f"/api/followups/{kinds['PX-9']['followup_id']}", json={"status": "completed"})
    rid = kinds["PX-3"]["recipient_id"]
    client.post(f"/api/recipients/{rid}/opt-out")
    left = client.get("/api/followups/queue", params={"event_id": e["id"]}).json()
    assert [i["participant_ref"] for i in left] == ["PX-4"]
    assert client.get("/api/followups/queue", params={"event_id": 12345}).json() == []


def test_participant_filters_and_history(client):
    c = new_campaign(client)
    for d in (0, 4, 5, 6, 8):
        add_recipient(client, c["id"], P(d))
    client.post(f"/api/campaigns/{c['id']}/start")
    f = lambda **p: {r["phone"] for r in client.get("/api/recipients", params={"campaign_id": c["id"], **p}).json()}
    assert f(attention="true") == {P(4)}                         # unclear only; 6/8 still retryable (pending)
    assert f(opted_out="true") == {P(5)}
    assert f(retry_eligible="true") == {P(6), P(8)}
    rid = next(r["id"] for r in client.get(f"/api/campaigns/{c['id']}/recipients").json() if r["phone"] == P(4))
    h = client.get(f"/api/recipients/{rid}/history").json()
    assert len(h["attempts"]) == 1 and h["intents"][0]["intent"] == "unclear" and h["followups"][0]["action_type"] == "human_review"
    assert client.get("/api/recipients/9999/history").status_code == 404


def test_copy_participants_same_event_only(client):
    e = new_event(client)
    a, b = new_campaign(client, event_id=e["id"]), new_campaign(client, event_id=e["id"])
    add_recipient(client, a["id"], P(0))
    gone = add_recipient(client, a["id"], P(1))
    add_recipient(client, a["id"], P(2), consent="revoked")
    client.post(f"/api/recipients/{gone['id']}/opt-out")
    r = client.post(f"/api/campaigns/{b['id']}/recipients/copy-from/{a['id']}").json()
    assert r == {"copied": 1, "skipped": 2}
    assert set(outcomes(client, b["id"])) == {P(0)}
    assert client.post(f"/api/campaigns/{b['id']}/recipients/copy-from/{a['id']}").json() == {"copied": 0, "skipped": 3}
    other = new_campaign(client)
    assert client.post(f"/api/campaigns/{other['id']}/recipients/copy-from/{a['id']}").status_code == 422


def test_csv_participant_id_and_optout_column(client):
    c = new_campaign(client)
    csv_data = ("name,phone,participant_id,opted_out\n"
                "Asha,+15550100100,DEF-1,\nBen,+15550100101,DEF-2,yes\n")
    r = client.post(f"/api/campaigns/{c['id']}/recipients/import", data={"consent_confirmed": "true"},
                    files={"file": ("p.csv", csv_data, "text/csv")}).json()
    assert r["imported"] == 2
    recs = {x["external_ref"]: x for x in client.get(f"/api/campaigns/{c['id']}/recipients").json()}
    assert recs["DEF-2"]["opted_out"] and recs["DEF-2"]["outcome"] == "opted_out"
    res = client.post(f"/api/campaigns/{c['id']}/start").json()
    assert res["dispatched"] == 1                              # opted-out participant never called


def test_sample_event_full_workflow(client):
    """Event -> campaign -> participants -> calls -> intents -> follow-ups -> analytics, all simulated."""
    seeded = client.post("/api/demo/seed").json()
    ev = client.get(f"/api/events/{seeded['event_id']}").json()
    assert ev["is_demo"] and ev["name"].startswith("[SAMPLE]") and "schedule" not in ev["approved_info"]
    run(client, seeded["id"])
    o = outcomes(client, seeded["id"])
    assert o[P(0)] == "confirmed" and o[P(1)] == "declined" and o[P(2)] == "confirmed"
    assert o[P(3)] == "callback_requested" and o[P(4)] == "unclear" and o[P(5)] == "opted_out"
    assert o[P(6)] == "confirmed" and o[P(7)] == "no_response" and o[P(8)] == "no_response"
    assert o[P(9)] == "information_requested"
    a = client.get("/api/analytics", params={"event_id": ev["id"]}).json()
    assert a["totals"]["real_calls"] == 0 and a["totals"]["recipients"] == 11
    assert a["needs_attention"] == 6            # callback, 2 unclear, info, 2 not reached
    q = client.get("/api/followups/queue", params={"event_id": ev["id"]}).json()
    assert {i["action_type"] for i in q} == {"callback", "human_review", "send_information"}
    assert client.delete("/api/demo").json()["deleted_campaigns"] == 1
    assert client.get("/api/events").json() == []


# ---- real-vs-simulated labelling with a fake REAL provider (no network) ----------------------------
class FakeReal:
    name, is_simulated = "exotel", False

    def initiate_call(self, **kw):
        return InitiateResult("CA-fake-1")

    def cancel_call(self, _):
        pass


def test_real_provider_calls_are_labelled_real_and_terminal_only_callback_works(client, monkeypatch):
    from member2.backend.app.core.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "call_provider", "exotel")
    monkeypatch.setattr(s, "exotel_webhook_token", "secret-token")
    client.app_.state.provider_override = FakeReal()
    c = new_campaign(client)
    assert c["is_demo"] is False
    add_recipient(client, c["id"], P(0))
    assert client.post(f"/api/campaigns/{c['id']}/start").json()["dispatched"] == 1
    att = client.get(f"/api/campaigns/{c['id']}/attempts").json()[0]
    assert att["is_simulated"] is False and att["status"] == "initiating"
    assert client.post("/api/webhooks/exotel?token=wrong", json={"CallSid": "CA-fake-1", "Status": "completed"}).status_code == 401
    ok = client.post("/api/webhooks/exotel?token=secret-token", json={"CallSid": "CA-fake-1", "Status": "completed"})
    assert ok.json()["result"] == "applied"
    dup = client.post("/api/webhooks/exotel?token=secret-token", json={"CallSid": "CA-fake-1", "Status": "completed"})
    assert dup.json()["result"] == "duplicate"
    att = client.get(f"/api/campaigns/{c['id']}/attempts").json()[0]
    assert att["status"] == "completed" and att["answered_at"]
    # a completed call alone is NOT an attendance confirmation
    assert outcomes(client, c["id"])[P(0)] == "pending"
    t = client.get("/api/analytics", params={"source": "real"}).json()
    assert t["totals"]["real_calls"] == 1 and t["outcomes"]["confirmed"] == 0
    assert client.get("/api/analytics", params={"source": "simulated"}).json()["totals"]["campaigns"] == 0
