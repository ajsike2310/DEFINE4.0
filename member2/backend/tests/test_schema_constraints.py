"""The database itself rejects bad data, whatever code (or hand-written SQL) tries to write it."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from member2.backend.app.models import enums
from member2.backend.app.services import states

from .conftest import add_recipient, new_campaign, new_event


def run(client, stmt, **params):
    with client.app_.state.engine.begin() as c:
        return c.execute(text(stmt), params)


def scalar(client, stmt, **params):
    with client.app_.state.engine.connect() as c:
        return c.execute(text(stmt), params).scalar()


@pytest.fixture
def world(client):
    """An event, a campaign, a participant, and one finished call with its response (all through the API)."""
    ev = new_event(client)
    camp = new_campaign(client, event_id=ev["id"])
    rec = add_recipient(client, camp["id"], "+919876543210")
    client.post(f"/api/campaigns/{camp['id']}/start")
    attempt = client.get(f"/api/campaigns/{camp['id']}/attempts").json()[0]
    draft = new_campaign(client, event_id=ev["id"], name="Still a draft")["id"]      # for tests that must add rows
    client.post(f"/api/events/{ev['id']}/leads", json={"name": "Lead Zero", "phone": "+919876543200"})
    run(client, "INSERT INTO follow_ups (campaign_id, recipient_id, action_type, status) VALUES (:c, :r, 'callback', 'pending')",
        c=camp["id"], r=rec["id"])
    return {"event": ev["id"], "campaign": camp["id"], "recipient": rec["id"], "attempt": attempt["id"], "draft": draft}


# ---- closed vocabularies ---------------------------------------------------------------------------------------
BAD_VALUES = [
    ("campaigns", "status", "paused"), ("campaigns", "purpose", "spam"),
    ("recipients", "outcome", "maybe"), ("recipients", "consent_status", "yes"),
    ("call_attempts", "status", "ringing_loudly"), ("call_attempts", "mode", "auto"),
    ("follow_ups", "status", "open"), ("follow_ups", "action_type", "email"),
    ("leads", "status", "won"), ("leads", "source", "bought_list"), ("leads", "consent_status", "implied"),
    ("intent_results", "intent", "shrug"), ("intent_results", "method", "magic"),
]


@pytest.mark.parametrize("table,column,bad", BAD_VALUES)
def test_unknown_vocabulary_value_is_rejected(client, world, table, column, bad):
    with pytest.raises(IntegrityError, match=f"ck_{table}_{column}"):
        run(client, f"UPDATE {table} SET {column} = :v WHERE id = 1", v=bad)


def test_every_enum_value_is_accepted_by_its_column(client, world):
    for status in enums.values(enums.CampaignStatus):
        run(client, "UPDATE campaigns SET status = :v WHERE id = 1", v=status)
    for outcome in enums.values(enums.Outcome):
        run(client, "UPDATE recipients SET outcome = :v WHERE id = 1", v=outcome)


# ---- formats and ranges ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("phone", ["12345", "9876543210", "+", "+91 98765 43210 99999999"])
def test_phone_must_look_like_e164(client, world, phone):
    with pytest.raises(IntegrityError, match="phone_e164"):
        run(client, "UPDATE recipients SET phone = :p WHERE id = 1", p=phone)


def test_numeric_ranges(client, world):
    with pytest.raises(IntegrityError, match="max_attempts_range"):
        run(client, "UPDATE campaigns SET max_attempts = 9 WHERE id = 1")
    with pytest.raises(IntegrityError, match="attempt_number_positive"):
        run(client, "UPDATE call_attempts SET attempt_number = 0 WHERE id = 1")
    with pytest.raises(IntegrityError, match="score_range"):
        run(client, "UPDATE intent_results SET score = 1.5 WHERE id = 1")
    with pytest.raises(IntegrityError, match="counts_consistent"):
        run(client, "INSERT INTO import_runs (kind, event_id, rows_total, imported, rejected) VALUES ('leads', :e, 3, 3, 3)",
            e=world["event"])


# ---- relationships ---------------------------------------------------------------------------------------------
def test_foreign_keys_are_enforced(client, world):
    assert scalar(client, "PRAGMA foreign_keys") == 1
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        run(client, "INSERT INTO recipients (campaign_id, name, phone) VALUES (999, 'Ghost', '+919876543299')")


def test_delete_rules(client, world):
    w = world
    lead = client.post(f"/api/events/{w['event']}/leads", json={"name": "Lead One", "phone": "+919876543211",
                                                                "consent_status": "granted"}).json()
    client.post("/api/leads/convert", json={"campaign_id": w["draft"], "lead_ids": [lead["id"]]})
    assert scalar(client, "SELECT recipient_id FROM leads WHERE id = :i", i=lead["id"]) is not None
    # an event that still has campaigns cannot be deleted
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        run(client, "DELETE FROM events WHERE id = :e", e=w["event"])
    # deleting a participant clears the lead's link instead of leaving it dangling
    run(client, "DELETE FROM recipients WHERE id = (SELECT recipient_id FROM leads WHERE id = :i)", i=lead["id"])
    assert scalar(client, "SELECT recipient_id FROM leads WHERE id = :i", i=lead["id"]) is None
    # deleting a campaign removes everything that belongs to it
    run(client, "DELETE FROM campaigns WHERE id = :c", c=w["campaign"])
    for table in ("recipients", "call_attempts", "intent_results", "follow_ups"):
        assert scalar(client, f"SELECT COUNT(*) FROM {table}") == 0, table
    # the provider-event ledger keeps its rows but loses the link to the deleted call
    assert scalar(client, "SELECT COUNT(*) FROM provider_events") > 0
    assert scalar(client, "SELECT COUNT(*) FROM provider_events WHERE call_attempt_id IS NOT NULL") == 0


# ---- uniqueness the code relies on -----------------------------------------------------------------------------
def test_one_classified_response_per_call(client, world):
    assert scalar(client, "SELECT COUNT(*) FROM intent_results WHERE call_attempt_id = :a", a=world["attempt"]) == 1
    with pytest.raises(IntegrityError, match="intent_results.call_attempt_id"):
        run(client, "INSERT INTO intent_results (call_attempt_id, recipient_id, campaign_id, intent, score, method, "
                    "detected_language, next_action) VALUES (:a, :r, :c, 'confirm', 1, 'dtmf', 'en', 'record_outcome')",
            a=world["attempt"], r=world["recipient"], c=world["campaign"])


def test_one_open_review_per_participant(client, world):
    ins = ("INSERT INTO follow_ups (campaign_id, recipient_id, action_type, status) "
           "VALUES (:c, :r, :t, :s)")
    base = dict(c=world["campaign"], r=world["recipient"])
    run(client, ins, **base, t="human_review", s="pending")
    with pytest.raises(IntegrityError, match="follow_ups.recipient_id"):
        run(client, ins, **base, t="human_review", s="scheduled")          # second open review
    run(client, ins, **base, t="callback", s="pending")                    # other kinds are unrestricted
    run(client, "UPDATE follow_ups SET status = 'completed' WHERE action_type = 'human_review'")
    run(client, ins, **base, t="human_review", s="pending")                # a closed one does not block a new one


def test_provider_call_id_identifies_one_attempt_per_provider(client, world):
    cid = scalar(client, "SELECT provider_call_id FROM call_attempts WHERE id = :a", a=world["attempt"])
    other = add_recipient(client, world["draft"], "+919876543212")
    ins = ("INSERT INTO call_attempts (campaign_id, recipient_id, provider, attempt_number, call_language, provider_call_id) "
           "VALUES (:c, :r, :p, 1, 'en', :id)")
    base = dict(c=world["draft"], r=other["id"])
    with pytest.raises(IntegrityError, match="call_attempts.provider"):
        run(client, ins, **base, p="demo", id=cid)                         # same provider, same call id
    run(client, ins, **base, p="exotel", id=cid)                           # another provider may reuse the string
    run(client, "DELETE FROM call_attempts WHERE provider = 'exotel'")
    run(client, ins.replace(":id", "NULL"), **base, p="demo")              # unknown ids are not unique


def test_server_defaults_fill_what_the_code_omits(client, world):
    run(client, "INSERT INTO events (name) VALUES ('Raw SQL event')")
    row = run(client, "SELECT description, approved_info, is_demo, created_at, updated_at FROM events "
                      "WHERE name = 'Raw SQL event'").one()
    assert row[0] == "" and row[1] == "{}" and row[2] == 0 and row[3] and row[4]
    run(client, "INSERT INTO recipients (campaign_id, name, phone) VALUES (:c, 'Raw', '+919876543277')", c=world["draft"])
    got = run(client, "SELECT consent_status, outcome, opted_out FROM recipients WHERE phone = '+919876543277'").one()
    assert tuple(got) == ("unknown", "pending", 0)


# ---- the vocabularies agree with the state machines ------------------------------------------------------------
def test_enums_match_the_state_machines():
    assert set(states.CALL_TRANSITIONS) == set(enums.values(enums.CallStatus))
    assert set(states.CAMPAIGN_TRANSITIONS) == set(enums.values(enums.CampaignStatus))
    assert states.RESOLVED_OUTCOMES | states.OPEN_OUTCOMES == set(enums.values(enums.Outcome))
    assert set(states.INTENT_TO_OUTCOME) == set(enums.values(enums.Intent))
    assert set(states.INTENT_TO_OUTCOME.values()) <= set(enums.values(enums.Outcome))
    assert states.RETRYABLE <= set(enums.values(enums.CallStatus))
