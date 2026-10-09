import pytest

from member2.backend.app.services.states import InvalidTransition, check_call_transition, check_campaign_transition
from member4.quality.conftest import add_recipient, new_campaign


def test_call_transitions():
    check_call_transition("initiating", "answered")
    check_call_transition("answered", "completed")
    for a, b in [("completed", "answered"), ("no_answer", "completed"), ("queued", "completed")]:
        with pytest.raises(InvalidTransition):
            check_call_transition(a, b)


def test_campaign_transitions():
    check_campaign_transition("draft", "running")
    with pytest.raises(InvalidTransition):
        check_campaign_transition("completed", "running")


def test_analytics_empty_has_undefined_rates_not_zero(client):
    a = client.get("/api/analytics").json()
    assert a["totals"]["recipients"] == 0
    assert all(v is None for v in a["rates"].values())


def test_analytics_matches_stored_records(client):
    c = new_campaign(client)
    for d in (0, 1, 4, 6):   # confirm, decline, unclear, no_answer->pending
        add_recipient(client, c["id"], f"+1555010010{d}", preferred_language="en")
    client.post(f"/api/campaigns/{c['id']}/start")
    a = client.get("/api/analytics", params={"campaign_id": c["id"]}).json()
    t = a["totals"]
    assert t["calls_attempted"] == 4 and t["calls_answered"] == 3 and t["calls_finished"] == 4
    assert t["failed_or_unanswered"] == 1 and t["recipients_responded"] == 3
    assert a["outcomes"]["confirmed"] == 1 and a["outcomes"]["declined"] == 1 and a["outcomes"]["unclear"] == 1
    assert a["rates"]["answer_rate"] == 0.75           # answered / finished attempts
    assert a["rates"]["confirmation_rate"] == round(1 / 3, 4)   # confirmed / recipients_responded
    assert a["rates"]["completion_rate"] == 0.75       # resolved / recipients
    assert t["simulated_calls"] == 4 and t["real_calls"] == 0
    assert a["by_language"][0]["language"] == "en" and a["by_language"][0]["recipients"] == 4
    # campaigns created while the demo provider is configured are SIMULATED, never "real"
    assert client.get("/api/analytics", params={"source": "real"}).json()["totals"]["campaigns"] == 0
    assert client.get("/api/analytics", params={"source": "simulated"}).json()["totals"]["campaigns"] == 1
    assert client.get("/api/analytics", params={"source": "bogus"}).status_code == 422
