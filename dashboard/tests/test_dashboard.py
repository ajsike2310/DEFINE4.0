import time

import pytest
from fastapi.testclient import TestClient

from dashboard.config import Settings
from dashboard.main import create_app
from dashboard.phone import normalize_phone


@pytest.fixture
def client():
    s = Settings(call_provider="demo", db_path=":memory:", dial_interval_s=0, call_window="")
    with TestClient(create_app(s, start_reconciler=False)) as c:
        yield c


def wait_done(client, cid, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        camp = client.get(f"/api/campaigns/{cid}").json()
        if camp["state"] != "running":
            return camp
        time.sleep(0.05)
    raise AssertionError("campaign never finished")


def make_event(client, **kw):
    body = dict(name="DevCon", type="hackathon", event_date="2026-11-15", event_time="10:00",
                venue="Main Hall", organiser="Acme College") | kw
    r = client.post("/api/events", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_phone_normalisation():
    assert normalize_phone("98765 43210") == "+919876543210"
    assert normalize_phone("+91 98765-43210") == "+919876543210"
    assert normalize_phone("12345") is None


def test_full_flow_and_personal_messages(client):
    ev = make_event(client)
    csv = ("name,phone,language,segment\n"
           "Asha Rao,9876543210,en,Students\n"                 # last digit 0 -> confirms
           "Bala,9876543211,en,Students\n"                     # declines
           "Chitra,9876543216,hi,Faculty\n"                    # 6 -> no answer, then keypad 1
           "Dev,9876543215,en,Faculty\n"                       # 5 -> opts out
           "Bad,123,en,x\n")
    imp = client.post(f"/api/events/{ev['id']}/participants/import", json={"csv": csv}).json()
    assert imp["added"] == 4 and imp["error_count"] == 1
    people = {p["name"]: p for p in client.get(f"/api/events/{ev['id']}/participants").json()}

    camp = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "Invites", "purpose": "invite"}).json()
    assert client.post(f"/api/campaigns/{camp['id']}/launch").status_code == 400              # nobody added yet
    r = client.post(f"/api/campaigns/{camp['id']}/members", json={"everyone": True}).json()
    assert r["added"] == 4
    assert client.post(f"/api/campaigns/{camp['id']}/members", json={"everyone": True}).json()["added"] == 0   # no duplicates

    # personal message belongs to the campaign, set on the person's membership
    calls = {c["participant_name"]: c for c in client.get(f"/api/campaigns/{camp['id']}").json()["calls"]}
    assert client.patch(f"/api/calls/{calls['Bala']['id']}", json={"message": "Hi {first_name}, you are a finalist in {event}! Will you come?"}).status_code == 200
    pv = client.post(f"/api/campaigns/{camp['id']}/preview", json={"participant_id": people["Bala"]["id"]}).json()
    assert pv["text"].startswith("Hi Bala, you are a finalist in DevCon!")
    hi_text = client.post(f"/api/campaigns/{camp['id']}/preview", json={"participant_id": people["Chitra"]["id"]}).json()["text"]
    assert "Chitra" in hi_text and "नमस्ते" in hi_text

    assert client.post(f"/api/campaigns/{camp['id']}/launch").status_code == 200
    done = wait_done(client, camp["id"])
    out = {c["participant_name"]: c["outcome"] for c in done["calls"]}
    assert out == {"Asha Rao": "confirmed", "Bala": "declined", "Chitra": "no_answer", "Dev": "opted_out"}
    assert next(c for c in done["calls"] if c["participant_name"] == "Bala")["message"].startswith("Hi Bala, you are a finalist")

    assert any(p["opted_out"] for p in client.get(f"/api/events/{ev['id']}/participants").json())
    assert client.post(f"/api/campaigns/{camp['id']}/retry").status_code == 200
    done = wait_done(client, camp["id"])
    assert {c["participant_name"]: c["outcome"] for c in done["calls"]}["Chitra"] == "confirmed"
    assert client.post(f"/api/campaigns/{camp['id']}/retry").status_code == 400

    ov = client.get("/api/overview").json()
    assert ov["totals"]["total"] == 4 and ov["totals"]["confirmed"] == 2
    assert {x["key"] for x in ov["by_language"]} == {"en", "hi"}
    assert {x["key"] for x in ov["by_segment"]} == {"Students", "Faculty"}


def test_message_is_per_campaign(client):
    ev = make_event(client)
    pid = client.post(f"/api/events/{ev['id']}/participants", json={"name": "Esha Nair", "phone": "9000000000"}).json()["id"]
    a = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "Invite"}).json()
    b = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "Reminder", "purpose": "reminder"}).json()
    client.post(f"/api/campaigns/{a['id']}/members", json={"participant_ids": [pid], "message": "Hi {first_name}, special invite to {event}. Coming?"})
    client.post(f"/api/campaigns/{b['id']}/members", json={"participant_ids": [pid]})     # no personal message here
    ta = client.post(f"/api/campaigns/{a['id']}/preview", json={"participant_id": pid}).json()["text"]
    tb = client.post(f"/api/campaigns/{b['id']}/preview", json={"participant_id": pid}).json()["text"]
    assert ta.startswith("Hi Esha, special invite") and tb.startswith("Hello Esha! This is a reminder")
    client.post(f"/api/campaigns/{a['id']}/launch"); wait_done(client, a["id"])
    # only the campaign that was run has called; the other is untouched and its members can be removed
    cb = client.get(f"/api/campaigns/{b['id']}").json()["calls"]
    assert cb[0]["status"] == "pending" and client.delete(f"/api/calls/{cb[0]['id']}").status_code == 204
    ca = client.get(f"/api/campaigns/{a['id']}").json()["calls"]
    assert client.delete(f"/api/calls/{ca[0]['id']}").status_code == 409                  # already called


def test_add_new_person_and_csv_into_campaign(client):
    ev = make_event(client, type="payment", name="Fees", venue="")
    camp = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "Dues", "purpose": "reminder"}).json()
    r = client.post(f"/api/campaigns/{camp['id']}/people", json={"name": "Gita", "phone": "9000000003", "fields": {"amount": "Rs 900"}, "message": "Hi {first_name}, {amount} is due. Can you pay today?"})
    assert r.status_code == 201
    imp = client.post(f"/api/campaigns/{camp['id']}/import", json={"csv": 'name,phone,amount,message\nHari,9000000004,Rs 500,"{first_name}, pay {amount}?"\nGita,9000000003,,\n'}).json()
    assert imp["added"] == 2 and imp["error_count"] == 0                                   # Gita reused, not duplicated
    done = client.get(f"/api/campaigns/{camp['id']}").json()
    assert len(done["calls"]) == 2
    texts = {c["participant_name"]: client.post(f"/api/campaigns/{camp['id']}/preview", json={"participant_id": c["participant_id"]}).json()["text"] for c in done["calls"]}
    assert texts["Hari"] == "Hari, pay Rs 500?" and "Rs 900" in texts["Gita"]
    assert len(client.get(f"/api/events/{ev['id']}/participants").json()) == 2


def test_late_additions_join_a_running_campaign(client):
    ev = make_event(client, type="webinar", venue="")
    camp = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "RSVP"}).json()
    for n, ph in (("Esha", "9000000000"), ("Farid", "9000000001")):
        client.post(f"/api/campaigns/{camp['id']}/people", json={"name": n, "phone": ph})
        client.post(f"/api/campaigns/{camp['id']}/launch")
        wait_done(client, camp["id"])
    done = client.get(f"/api/campaigns/{camp['id']}").json()
    assert len(done["calls"]) == 2 and all(c["status"] == "completed" for c in done["calls"])
    assert "online" in done["calls"][0]["message"]


def test_duplicates_validation_and_erasure(client):
    ev = make_event(client)
    ok = client.post(f"/api/events/{ev['id']}/participants", json={"name": "A", "phone": "9000000002"})
    assert ok.status_code == 201
    assert client.post(f"/api/events/{ev['id']}/participants", json={"name": "A", "phone": "+919000000002"}).status_code == 409
    assert client.post(f"/api/events/{ev['id']}/participants", json={"name": "A", "phone": "abc"}).status_code == 422
    assert client.delete(f"/api/participants/{ok.json()['id']}").status_code == 204
    assert client.get(f"/api/events/{ev['id']}/participants").json() == []


def test_token_protects_api():
    s = Settings(call_provider="demo", db_path=":memory:", dashboard_token="s3cret")
    with TestClient(create_app(s, start_reconciler=False)) as c:
        assert c.get("/api/events").status_code == 401
        assert c.get("/api/events", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def people(client, ev, rows):
    ids = {}
    for name, phone, *rest in rows:
        r = client.post(f"/api/events/{ev['id']}/participants", json={"name": name, "phone": phone, **(rest[0] if rest else {})})
        assert r.status_code == 201, r.text
        ids[name] = r.json()["id"]
    return ids


def test_consent_blocks_calls(client):
    ev = make_event(client)
    ids = people(client, ev, [("Yes Person", "9000000010"), ("No Person", "9000000011", {"can_call": False})])
    camp = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "C"}).json()
    r = client.post(f"/api/campaigns/{camp['id']}/members", json={"everyone": True}).json()
    assert r["added"] == 1                                                                       # the 'no' person is skipped
    assert client.post(f"/api/campaigns/{camp['id']}/members", json={"participant_ids": [ids["No Person"]]}).json()["added"] == 0
    assert client.post(f"/api/campaigns/{camp['id']}/people", json={"name": "Zed", "phone": "9000000012", "can_call": False}).status_code == 409
    imp = client.post(f"/api/campaigns/{camp['id']}/import", json={"csv": "name,phone,consent\nAa,9000000013,no\nBb,9000000014,yes\n"}).json()
    assert imp["added"] == 2
    calls = {c["participant_name"]: c for c in client.get(f"/api/campaigns/{camp['id']}").json()["calls"]}
    assert "Aa" not in calls or calls["Aa"]["blocked"]
    # a person already in a campaign who is later marked 'not OK' is never dialled
    pid = next(c["participant_id"] for c in calls.values() if c["participant_name"] == "Bb")
    client.patch(f"/api/participants/{pid}", json={"name": "Bb", "phone": "9000000014", "can_call": False})
    client.post(f"/api/campaigns/{camp['id']}/launch")
    done = wait_done(client, camp["id"])
    out = {c["participant_name"]: c["status"] for c in done["calls"]}
    assert out["Yes Person"] == "completed" and out["Bb"] == "pending"
    assert client.post(f"/api/calls/{next(c['id'] for c in done['calls'] if c['participant_name'] == 'Bb')}/redial").status_code == 400


def test_rsvp_and_follow_up_tasks(client):
    ev = make_event(client)
    ids = people(client, ev, [("Comes", "9100000000"), ("Declines", "9100000001"), ("Unsure", "9100000004"),
                              ("CallMe", "9100000003"), ("Asks", "9100000009"), ("Busy", "9100000008")])
    camp = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "RSVP", "max_attempts": 1}).json()
    client.post(f"/api/campaigns/{camp['id']}/members", json={"everyone": True})
    client.post(f"/api/campaigns/{camp['id']}/launch"); wait_done(client, camp["id"])
    rsvp = {p["name"]: p["rsvp"] for p in client.get(f"/api/events/{ev['id']}/participants").json()}
    assert rsvp == {"Comes": "attending", "Declines": "not_attending", "Unsure": "undecided",
                    "CallMe": "undecided", "Asks": "undecided", "Busy": ""}
    tasks = {t["participant_name"]: t for t in client.get("/api/tasks").json()}
    assert set(tasks) == {"Unsure", "CallMe", "Asks", "Busy"}                                    # Comes / Declines need nothing
    assert tasks["Unsure"]["kind"] == "in_person_call" and tasks["CallMe"]["kind"] == "callback"
    assert tasks["Asks"]["kind"] == "answer_question" and "after 1 attempt" in tasks["Busy"]["reason"]
    assert client.get("/api/overview").json()["open_tasks"] == 4
    # a person completes a task
    done = client.patch(f"/api/tasks/{tasks['Unsure']['id']}", json={"status": "done", "note": "Spoke in person: coming"}).json()
    assert done["status"] == "done" and len(client.get("/api/tasks").json()) == 3
    assert len(client.get("/api/tasks?status=done").json()) == 1


def test_later_clear_answer_resolves_task_and_keeps_rsvp(client):
    app = client.app
    ev = make_event(client)
    ids = people(client, ev, [("Unsure", "9100000004")])
    camp = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "R"}).json()
    client.post(f"/api/campaigns/{camp['id']}/members", json={"everyone": True})
    client.post(f"/api/campaigns/{camp['id']}/launch"); done = wait_done(client, camp["id"])
    assert len(client.get("/api/tasks").json()) == 1
    call = done["calls"][0]
    app.state.db.update("calls", call["id"], attendance="confirmed")                              # as if a retry got a clear yes
    app.state.engine._record_rsvp({"participant_id": ids["Unsure"], "campaign_id": camp["id"]}, "confirmed")
    app.state.engine._followup(call["id"])
    assert client.get("/api/tasks").json() == [] and client.get("/api/tasks?status=done").json()[0]["note"].startswith("Resolved")
    app.state.engine._record_rsvp({"participant_id": ids["Unsure"], "campaign_id": camp["id"]}, "unclear")
    assert client.get(f"/api/events/{ev['id']}/participants").json()[0]["rsvp"] == "attending"      # unclear never erases a yes


def test_calling_hours_setting(client):
    eng = client.app.state.engine
    assert client.get("/api/settings").json()["calling_hours"]["enabled"] is False                  # no CALL_WINDOW in the test settings
    r = client.put("/api/settings/calling-hours", json={"enabled": True, "start": "09:00", "end": "09:30"})
    assert r.status_code == 200 and r.json()["calling_hours"]["start"] == "09:00"
    assert client.put("/api/settings/calling-hours", json={"enabled": True, "start": "21:00", "end": "09:00"}).status_code == 422
    assert client.put("/api/settings/calling-hours", json={"enabled": True, "start": "9am", "end": "10:00"}).status_code == 422
    eng.provider.is_simulated = False                                                                # hours only apply to real calls
    try:
        from datetime import datetime, timezone
        eng.local_now = lambda: datetime(2026, 1, 1, 7, 0)
        with pytest.raises(Exception, match="Outside calling hours"):
            eng._check_window()
        eng.local_now = lambda: datetime(2026, 1, 1, 9, 10)
        eng._check_window()                                                                          # inside: fine
        eng.local_now = lambda: datetime(2026, 1, 1, 2, 0)
        client.put("/api/settings/calling-hours", json={"enabled": False, "start": "09:00", "end": "21:00"})
        eng._check_window()                                                                          # switched off: always fine
    finally:
        eng.provider.is_simulated = True


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    path = str(tmp_path / "old.db")
    c = sqlite3.connect(path)
    c.executescript("""CREATE TABLE events (id INTEGER PRIMARY KEY, name TEXT, type TEXT, mode TEXT, venue TEXT, event_date TEXT,
      event_time TEXT, organiser TEXT, description TEXT, created_at TEXT);
      CREATE TABLE participants (id INTEGER PRIMARY KEY, event_id INTEGER, name TEXT, phone TEXT, language TEXT, segment TEXT,
      custom_message TEXT, fields TEXT, opted_out INTEGER NOT NULL DEFAULT 0, created_at TEXT, UNIQUE(event_id, phone));
      INSERT INTO events VALUES (1,'Old','webinar','online','','2026-01-01','10:00','Org','','x');
      INSERT INTO participants VALUES (1,1,'Old Timer','+919000000099','','','','{}',0,'x');""")
    c.commit(); c.close()
    from dashboard.db import Db
    d = Db(path)
    p = d.one("SELECT can_call, rsvp FROM participants WHERE id=1")
    assert p["can_call"] == 1 and p["rsvp"] == ""


def test_resolving_a_task_can_record_the_rsvp(client):
    ev = make_event(client)
    ids = people(client, ev, [("Unsure", "9100000004")])
    camp = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "R"}).json()
    client.post(f"/api/campaigns/{camp['id']}/members", json={"everyone": True})
    client.post(f"/api/campaigns/{camp['id']}/launch"); wait_done(client, camp["id"])
    t = client.get("/api/tasks").json()[0]
    assert client.patch(f"/api/tasks/{t['id']}", json={"status": "done", "rsvp": "maybe"}).status_code == 422
    assert client.patch(f"/api/tasks/{t['id']}", json={"status": "done", "rsvp": "attending", "note": "met at office"}).status_code == 200
    assert client.get(f"/api/events/{ev['id']}/participants").json()[0]["rsvp"] == "attending"


def test_comment_after_blank_env_value_is_not_a_value():
    env = {"PUBLIC_BASE_URL": "# e.g. https://<id>.ngrok-free.app", "EXOTEL_FLOW_URL": "   # flow", "EXOTEL_CALLER_ID": " +911234567890 ",
           "CALL_PROVIDER": "exotel"}
    s = Settings.from_env(env)
    assert s.public_base_url == "" and s.exotel_flow_url == "" and s.exotel_caller_id == "+911234567890"
    assert Settings.from_env({"PUBLIC_BASE_URL": "https://abc.ngrok-free.app"}).public_base_url == "https://abc.ngrok-free.app"
    assert Settings.from_env({"PUBLIC_BASE_URL": "abc.ngrok-free.app"}).public_base_url == ""      # must be a full URL


def run_retries(client, cid, times=1):
    for _ in range(times):
        client.app.state.engine.run_due_retries()
        wait_done(client, cid)


def test_unanswered_calls_are_retried_after_the_interval_until_max_attempts(client):
    ev = make_event(client)
    people(client, ev, [("Later", "9200000006"), ("AlwaysBusy", "9200000008"), ("Answers", "9200000000")])
    camp = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "R", "max_attempts": 3, "retry_interval_min": 0}).json()
    assert camp["auto_retry"] is True and camp["retry_interval_min"] == 0
    client.post(f"/api/campaigns/{camp['id']}/members", json={"everyone": True})
    client.post(f"/api/campaigns/{camp['id']}/launch")
    first = wait_done(client, camp["id"])
    st = {c["participant_name"]: c for c in first["calls"]}
    assert st["Answers"]["status"] == "completed" and st["Answers"]["next_attempt_at"] is None      # answered: never retried
    assert st["Later"]["status"] == "no_answer" and st["Later"]["next_attempt_at"] and first["state"] == "waiting"
    assert client.get("/api/tasks").json() == []                                                  # nothing for a human yet

    run_retries(client, camp["id"])                                                               # attempt 2
    second = {c["participant_name"]: c for c in client.get(f"/api/campaigns/{camp['id']}").json()["calls"]}
    assert second["Later"]["outcome"] == "confirmed" and second["Later"]["attempts"] == 2          # picked up on the retry
    assert second["AlwaysBusy"]["attempts"] == 2 and second["Answers"]["attempts"] == 1

    run_retries(client, camp["id"])                                                               # attempt 3 = the last
    third = client.get(f"/api/campaigns/{camp['id']}").json()
    busy = next(c for c in third["calls"] if c["participant_name"] == "AlwaysBusy")
    assert busy["attempts"] == 3 and busy["next_attempt_at"] is None and third["state"] == "completed"
    assert client.app.state.engine.run_due_retries() == 0                                          # limit reached: no more
    tasks = client.get("/api/tasks").json()
    assert [t["participant_name"] for t in tasks] == ["AlwaysBusy"] and "3 attempts" in tasks[0]["reason"]


def test_retries_respect_interval_pause_switch_and_consent(client):
    ev = make_event(client)
    people(client, ev, [("A", "9200000008")])
    eng = client.app.state.engine
    slow = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "slow", "retry_interval_min": 60}).json()
    off = client.post(f"/api/events/{ev['id']}/campaigns", json={"name": "off", "auto_retry": False}).json()
    for c in (slow, off):
        client.post(f"/api/campaigns/{c['id']}/members", json={"participant_ids": [client.get(f"/api/events/{ev['id']}/participants").json()[0]["id"]]})
        client.post(f"/api/campaigns/{c['id']}/launch"); wait_done(client, c["id"])
    calls = lambda c: client.get(f"/api/campaigns/{c['id']}").json()["calls"][0]
    assert calls(slow)["next_attempt_at"] and eng.run_due_retries() == 0                            # 60 min has not passed
    assert calls(off)["next_attempt_at"] is None                                                   # switched off for that campaign
    # make the slow one due, then pause it: a paused campaign is never retried behind the user's back
    eng.db.update("calls", calls(slow)["id"], next_attempt_at="2000-01-01T00:00:00+00:00")
    client.post(f"/api/campaigns/{slow['id']}/pause")
    assert eng.run_due_retries() == 0
    eng.db.update("campaigns", slow["id"], status="active")
    pid = calls(slow)["participant_id"]
    client.patch(f"/api/participants/{pid}", json={"name": "A", "phone": "9200000008", "can_call": False})
    assert eng.run_due_retries() == 0                                                              # no consent: not retried


def test_old_campaign_database_gets_retry_columns(tmp_path):
    import sqlite3
    path = str(tmp_path / "old2.db")
    c = sqlite3.connect(path)
    c.executescript("""CREATE TABLE campaigns (id INTEGER PRIMARY KEY, event_id INTEGER, name TEXT, purpose TEXT, language TEXT,
      template TEXT, segment TEXT, max_attempts INTEGER, status TEXT, created_at TEXT, launched_at TEXT);
      CREATE TABLE calls (id INTEGER PRIMARY KEY, campaign_id INTEGER, participant_id INTEGER, status TEXT, attempts INTEGER,
      custom_message TEXT, updated_at TEXT);
      INSERT INTO campaigns VALUES (1,1,'old','invite','en','t','',3,'active','x',NULL);""")
    c.commit(); c.close()
    from dashboard.db import Db
    d = Db(path)
    row = d.one("SELECT auto_retry, retry_interval_min FROM campaigns WHERE id=1")
    assert row == {"auto_retry": 1, "retry_interval_min": 30}
    assert "next_attempt_at" in {r["name"] for r in d.q("PRAGMA table_info(calls)")}
