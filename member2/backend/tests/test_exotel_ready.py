"""Backend readiness for the Exotel integration (member 3 plugs the provider in; member 2 owns everything around it)."""
import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import text

from member2.backend.app import cli
from member2.backend.app.core.config import Settings, get_settings
from member2.backend.app.repositories import webhook_logs as log_repo
from member2.backend.app.services import pacing, readiness, webhook_log
from member3.integrations.base import InitiateResult

from .conftest import add_recipient, new_campaign, new_event

TOKEN = "t0ken-" + "x" * 20


class FakeExotel:
    """Stands in for the real provider: places no call, returns a call SID like Exotel does."""
    name, is_simulated, supports_clarify = "exotel", False, True

    def __init__(self):
        self.placed = []

    def initiate_call(self, *, attempt_id, attempt_number, to, language, message, mode="main"):
        self.placed.append(to)
        return InitiateResult(f"CA{attempt_id:06d}")

    def cancel_call(self, provider_call_id):
        return None


@pytest.fixture
def live(client, monkeypatch):
    """A real (non-sample) campaign with one participant and one real attempt, webhooks enabled."""
    s = get_settings()
    monkeypatch.setattr(s, "call_provider", "exotel")
    monkeypatch.setattr(s, "exotel_webhook_token", TOKEN)
    fake = FakeExotel()
    client.app_.state.provider_override = fake
    cid = new_campaign(client)["id"]
    rec = add_recipient(client, cid, "+919876543210")
    assert client.post(f"/api/campaigns/{cid}/start").json()["dispatched"] == 1
    attempt = client.get(f"/api/campaigns/{cid}/attempts").json()[0]
    return {"campaign": cid, "recipient": rec["id"], "attempt": attempt["id"], "sid": attempt["provider_call_id"], "fake": fake}


def log(client, **params):
    return client.get("/api/webhooks/log", params=params).json()


# ---- webhook log ---------------------------------------------------------------------------------------------------
def test_keypad_callback_is_handled_and_logged_without_token_or_whole_phone(live, client):
    r = client.get("/api/webhooks/exotel/response", params={"token": TOKEN, "CallSid": live["sid"], "digits": '"1"',
                                                            "CallFrom": "+919876543210", "CustomField": str(live["attempt"])})
    assert r.status_code == 200
    assert client.get(f"/api/campaigns/{live['campaign']}/recipients").json()[0]["outcome"] == "confirmed"
    (row,) = log(client, provider="exotel")
    assert row["endpoint"] == "response" and row["ok"] is True and row["call_attempt_id"] == live["attempt"]
    assert row["method"] == "GET" and row["request_id"] and row["result"] == "applied"
    assert row["payload"]["digits"] == '"1"' and row["payload"]["CallSid"] == live["sid"]
    assert "token" not in row["payload"] and TOKEN not in str(row)
    assert row["payload"]["CallFrom"] != "+919876543210" and "*" in row["payload"]["CallFrom"]


def test_status_callback_form_post_is_logged_and_duplicates_are_visible(live, client):
    body = {"CallSid": live["sid"], "Status": "completed", "From": "+919876543210", "Duration": "12"}
    first = client.post("/api/webhooks/exotel", params={"token": TOKEN}, data=body)
    again = client.post("/api/webhooks/exotel", params={"token": TOKEN}, data=body)
    assert first.status_code == again.status_code == 200
    rows = log(client)
    assert [r["result"] for r in rows] == ["duplicate", "applied"] and all(r["endpoint"] == "status" for r in rows)
    assert rows[0]["payload"]["Duration"] == "12" and "9876543210" not in str(rows)


def test_a_callback_for_an_unknown_call_is_kept_so_the_mismatch_can_be_seen(live, client):
    r = client.post("/api/webhooks/exotel", params={"token": TOKEN}, data={"CallSid": "CA-nope", "Status": "completed"})
    assert r.status_code == 404
    (row,) = log(client, ok=False)
    assert row["result"] == "unknown_call" and row["call_attempt_id"] is None and row["payload"]["CallSid"] == "CA-nope"


def test_an_unrecognised_status_is_kept(live, client):
    client.post("/api/webhooks/exotel", params={"token": TOKEN}, data={"CallSid": live["sid"], "Status": "teleported"})
    assert log(client)[0]["result"] == "unrecognised_payload"


def test_callbacks_with_a_bad_token_are_refused_and_not_stored(live, client):
    assert client.post("/api/webhooks/exotel", params={"token": "wrong"}, data={"CallSid": live["sid"]}).status_code == 401
    assert client.get("/api/webhooks/exotel/response", params={"CallSid": live["sid"]}).status_code == 401
    assert log(client) == []


def test_logging_can_be_switched_off(live, client, monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_log_days", 0)
    client.post("/api/webhooks/exotel", params={"token": TOKEN}, data={"CallSid": live["sid"], "Status": "completed"})
    assert log(client) == []


def test_a_logging_failure_never_breaks_the_callback(live, client, monkeypatch):
    monkeypatch.setattr(webhook_log, "mask_payload", lambda p: 1 / 0)
    r = client.post("/api/webhooks/exotel", params={"token": TOKEN}, data={"CallSid": live["sid"], "Status": "completed"})
    assert r.status_code == 200 and r.json()["result"] == "applied"
    assert client.get(f"/api/campaigns/{live['campaign']}/attempts").json()[0]["status"] == "completed"


def test_old_entries_are_pruned_on_a_schedule_of_writes(client):
    s = get_settings()
    with client.app_.state.engine.begin() as c:
        for _ in range(49):
            c.execute(text("INSERT INTO webhook_logs (provider, endpoint, method, received_at, ok, result, payload) "
                           "VALUES ('exotel', 'status', 'POST', datetime('now', '-60 days'), 1, 'applied', '{}')"))
    with client.app_.state.session_factory() as db:
        webhook_log.record(db, s, provider="exotel", endpoint="status", method="POST", payload={}, ok=True, result="applied")
        assert db.scalar(text("SELECT COUNT(*) FROM webhook_logs")) == 1          # row 50 triggered the prune, old ones gone
        assert log_repo.delete_older_than(db, __import__("datetime").datetime(2000, 1, 1, tzinfo=__import__("datetime").timezone.utc)) == 0


def test_mask_payload_rules():
    out = webhook_log.mask_payload({"token": "SECRET", "From": "+919876543210", "To": "09876543210", "CallSid": "1234567890123",
                                    "digits": '"1"', "Note": "hello", "RecordingUrl": "https://x/r.mp3", "x" * 100: "k",
                                    "Empty": None, "Long": "z" * 500})
    assert "token" not in out and out["From"].startswith("+91") and "*" in out["From"] and "*" in out["To"]
    assert out["CallSid"] == "1234567890123" and out["digits"] == '"1"' and out["Note"] == "hello"
    assert len(out["Long"]) == 200 and out["Empty"] == "" and len(next(k for k in out if k.startswith("xx"))) == 60
    assert len(webhook_log.mask_payload({f"k{i}": "v" for i in range(100)})) == webhook_log.MAX_KEYS


def test_log_endpoint_validates_and_filters(live, client):
    client.post("/api/webhooks/exotel", params={"token": TOKEN}, data={"CallSid": live["sid"], "Status": "completed"})
    assert len(log(client, provider="exotel", ok=True)) == 1 and log(client, provider="other") == []
    assert client.get("/api/webhooks/log", params={"limit": 0}).status_code == 422
    assert client.get("/api/webhooks/log", params={"limit": 201}).status_code == 422


# ---- readiness -------------------------------------------------------------------------------------------------------
def configure_everything(monkeypatch, **over):
    s = get_settings()
    for k, v in dict(call_provider="exotel", exotel_account_sid="sid", exotel_api_key="key", exotel_api_token="SUPER-SECRET",
                     exotel_caller_id="0800", exotel_flow_url="http://my.exotel.com/sid/exoml/start_voice/1",
                     exotel_webhook_token=TOKEN, public_base_url="https://abc.example", **over).items():
        monkeypatch.setattr(s, k, v)
    return s


def test_readiness_is_ready_when_everything_is_set_and_never_leaks_values(client, monkeypatch):
    configure_everything(monkeypatch)
    body = client.get("/api/settings/exotel-readiness").json()
    assert body["ready"] is True and body["next_steps"] == []
    assert "SUPER-SECRET" not in str(body) and TOKEN not in str(body)
    assert body["urls"]["status_callback"] == "https://abc.example/api/webhooks/exotel?token=<EXOTEL_WEBHOOK_TOKEN>"
    assert body["limits"] == {"max_calls_per_minute": 200, "real_calls_per_start": 0, "allowed_numbers": 0}
    assert body["webhooks_seen_last_24h"] == {"status": 0, "response": 0}


def test_readiness_says_what_to_do_next(client):
    body = client.get("/api/settings/exotel-readiness").json()
    assert body["ready"] is False
    assert any(step.startswith("EXOTEL_FLOW_URL: ") for step in body["next_steps"])
    assert any("ngrok" in step for step in body["next_steps"])


def test_readiness_counts_what_exotel_has_sent(live, client, monkeypatch):
    client.post("/api/webhooks/exotel", params={"token": TOKEN}, data={"CallSid": live["sid"], "Status": "completed"})
    client.get("/api/webhooks/exotel/response", params={"token": TOKEN, "CallSid": live["sid"], "digits": "1"})
    assert client.get("/api/settings/exotel-readiness").json()["webhooks_seen_last_24h"] == {"status": 1, "response": 1}


def _probe(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_probe_confirms_the_public_url_reaches_this_backend(client, monkeypatch):
    s = configure_everything(monkeypatch)
    with client.app_.state.session_factory() as db:
        good = readiness.exotel_readiness(db, s, probe=True, client=_probe(lambda r: httpx.Response(200, json={"status": "ok"})))
        page = readiness.exotel_readiness(db, s, probe=True, client=_probe(lambda r: httpx.Response(200, text="<html>ngrok</html>")))
        down = readiness.exotel_readiness(db, s, probe=True, client=_probe(lambda r: httpx.Response(502)))

        def boom(request):
            raise httpx.ConnectError("refused")
        dead = readiness.exotel_readiness(db, s, probe=True, client=_probe(boom))
    pick = lambda rep: next(c for c in rep["checks"] if c["name"] == "backend reachable at PUBLIC_BASE_URL")   # noqa: E731
    assert pick(good)["ok"] is True and good["ready"] is True
    assert pick(page)["ok"] is False and "warning page" in pick(page)["detail"] and page["ready"] is False
    assert pick(down)["ok"] is False and "502" in pick(down)["detail"]
    assert pick(dead)["ok"] is False and "ConnectError" in pick(dead)["detail"]


def test_probe_asks_for_the_health_url_and_sends_the_tunnel_bypass_header(client, monkeypatch):
    s = configure_everything(monkeypatch)
    seen = {}

    def handler(request):
        seen["url"], seen["hdr"] = str(request.url), request.headers.get("ngrok-skip-browser-warning")
        return httpx.Response(200, json={"status": "ok"})
    with client.app_.state.session_factory() as db:
        readiness.exotel_readiness(db, s, probe=True, client=_probe(handler))
    assert seen == {"url": "https://abc.example/api/health", "hdr": "1"}


def test_probe_without_a_public_url_fails_with_a_clear_reason(client):
    body = client.get("/api/settings/exotel-readiness", params={"probe": "true"}).json()
    check = next(c for c in body["checks"] if c["name"] == "backend reachable at PUBLIC_BASE_URL")
    assert check["ok"] is False and "not set" in check["detail"]


# ---- pacing and the first-test cap ---------------------------------------------------------------------------------
def test_pacer_spaces_calls_to_the_limit_and_never_delays_the_first():
    t, slept = [0.0], []
    p = pacing.Pacer(120, clock=lambda: t[0], sleep=lambda d: (slept.append(round(d, 3)), t.__setitem__(0, t[0] + d)))
    p.wait()
    p.wait()
    p.wait()
    assert slept == [0.5, 0.5]
    t[0] += 10                                                   # idle for a while: no catching up, no waiting
    p.wait()
    assert slept == [0.5, 0.5]


def test_only_real_providers_are_paced():
    s = get_settings()
    assert pacing.for_provider(FakeExotel(), s) is not None
    from member3.integrations.demo_provider.provider import DemoProvider
    assert pacing.for_provider(DemoProvider(), s) is None


def test_the_per_press_cap_holds_the_rest_back_until_start_is_pressed_again(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "call_provider", "exotel")
    monkeypatch.setattr(s, "real_calls_per_start", 2)
    monkeypatch.setattr(s, "exotel_max_calls_per_minute", 600)
    fake = FakeExotel()
    client.app_.state.provider_override = fake
    cid = new_campaign(client)["id"]
    for i in range(5):
        add_recipient(client, cid, f"+91987654321{i}")
    results = [client.post(f"/api/campaigns/{cid}/start").json() for _ in range(3)]
    assert [(r["dispatched"], r["held_back"]) for r in results] == [(2, 3), (2, 1), (1, 0)]
    assert len(fake.placed) == 5 and len(set(fake.placed)) == 5               # nobody dialled twice
    assert client.get(f"/api/campaigns/{cid}").json()["status"] in ("running", "completed")


def test_simulated_campaigns_ignore_the_cap(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "real_calls_per_start", 1)
    cid = new_campaign(client)["id"]
    for i in range(4):
        add_recipient(client, cid, f"+91987654321{i}")
    out = client.post(f"/api/campaigns/{cid}/start").json()
    assert out["dispatched"] == 4 and out["held_back"] == 0


# ---- settings --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("field,value", [
    ("exotel_webhook_token", "short"), ("exotel_allowed_numbers", "98765"), ("exotel_allowed_numbers", "+919876543210,oops"),
    ("public_base_url", "ftp://x.example"), ("exotel_base_url", "http://api.exotel.com"), ("exotel_max_calls_per_minute", 0),
    ("exotel_max_calls_per_minute", 601), ("real_calls_per_start", -1), ("webhook_log_days", 400)])
def test_bad_exotel_settings_fail_fast(field, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_exotel_settings_are_normalised():
    s = Settings(exotel_allowed_numbers=" +919876543210 , +919876543211,", public_base_url=" https://x.example/ ",
                 exotel_base_url="https://api.in.exotel.com/", exotel_webhook_token=" " + TOKEN + " ")
    assert s.allowed_numbers == ["+919876543210", "+919876543211"] and s.public_base_url == "https://x.example"
    assert s.exotel_base_url == "https://api.in.exotel.com" and s.exotel_webhook_token == TOKEN


# ---- command line ----------------------------------------------------------------------------------------------------
def test_doctor_command_reports_and_sets_its_exit_code(tmp_path, capsys, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'doc.db').as_posix()}"
    assert cli.main(["--url", url, "exotel", "doctor"]) == 1
    out = capsys.readouterr().out
    assert "[MISSING] EXOTEL_FLOW_URL" in out and "NOT ready yet" in out and "to do: PUBLIC_BASE_URL" in out
    configure_everything(monkeypatch)
    assert cli.main(["--url", url, "exotel", "doctor"]) == 0
    out = capsys.readouterr().out
    assert "READY for a test call" in out and "SUPER-SECRET" not in out and TOKEN not in out
    assert "StatusCallback URL : https://abc.example/api/webhooks/exotel?token=<EXOTEL_WEBHOOK_TOKEN>" in out


def test_webhooks_command_lists_recent_callbacks(tmp_path, capsys):
    url = f"sqlite:///{(tmp_path / 'hooks.db').as_posix()}"
    assert cli.main(["--url", url, "exotel", "webhooks"]) == 0
    assert "no Exotel callbacks received yet" in capsys.readouterr().out
