"""Indexes: every foreign key is covered, none is redundant, and the hot queries really use them."""
import pytest
from sqlalchemy import inspect

from member2.backend.app.core import dbtools
from member2.backend.app.core.db import Base

from .conftest import add_recipient, new_campaign, new_event


def _index_column_lists(insp, table: str) -> list[tuple[str, ...]]:
    cols = [tuple(ix["column_names"]) for ix in insp.get_indexes(table) if ix.get("dialect_options", {}).get("sqlite_where") is None]
    cols += [tuple(u["column_names"]) for u in insp.get_unique_constraints(table)]
    cols.append(tuple(insp.get_pk_constraint(table)["constrained_columns"]))
    return cols


def test_every_foreign_key_is_the_start_of_some_index(client):
    insp = inspect(client.app_.state.engine)
    uncovered = []
    for table in Base.metadata.sorted_tables:
        lists = _index_column_lists(insp, table.name)
        for fk in insp.get_foreign_keys(table.name):
            need = tuple(fk["constrained_columns"])
            if not any(cols[:len(need)] == need for cols in lists):
                uncovered.append(f"{table.name}{need}")
    assert uncovered == [], f"foreign keys without a usable index (deletes and joins would scan): {uncovered}"


def test_no_index_is_a_redundant_prefix_of_another(client):
    insp = inspect(client.app_.state.engine)
    redundant = []
    for table in Base.metadata.sorted_tables:
        plain = [(ix["name"], tuple(ix["column_names"])) for ix in insp.get_indexes(table.name)
                 if ix.get("dialect_options", {}).get("sqlite_where") is None]
        everything = [c for _, c in plain] + [tuple(u["column_names"]) for u in insp.get_unique_constraints(table.name)]
        for name, cols in plain:
            if any(len(other) > len(cols) and other[:len(cols)] == cols for other in everything):
                redundant.append(f"{table.name}.{name}")
    assert redundant == [], f"indexes already served by a longer index: {redundant}"


def test_names_follow_the_convention(client):
    insp = inspect(client.app_.state.engine)
    for table in Base.metadata.sorted_tables:
        for ix in insp.get_indexes(table.name):
            assert ix["name"].startswith(("ix_", "uq_")), ix["name"]


# ---- query plans -----------------------------------------------------------------------------------------------
@pytest.fixture
def seeded(client):
    """A few thousand rows so the planner has something to choose between."""
    ev = new_event(client)["id"]
    camps = [new_campaign(client, event_id=ev, name=f"Campaign {i}")["id"] for i in range(3)]
    with client.app_.state.engine.begin() as c:
        for cid in camps:
            c.exec_driver_sql("INSERT INTO recipients (campaign_id, name, phone, is_demo) "
                              "SELECT ?, 'P', '+9198' || printf('%07d', ?*100000 + value), 1 FROM "
                              "(WITH RECURSIVE n(value) AS (SELECT 1 UNION ALL SELECT value + 1 FROM n WHERE value < 700) "
                              "SELECT value FROM n)", (cid, cid))
    dbtools.optimize(client.app_.state.engine)
    return {"event": ev, "campaigns": camps}


def plan(client, sql, **params):
    return dbtools.query_plan(client.app_.state.engine, sql, params)


def uses(lines, index, table=None):
    """The plan searches an index (SQLite names a UNIQUE constraint's index sqlite_autoindex_<table>_N) and never scans."""
    named = any(index in line or (table and f"sqlite_autoindex_{table}_" in line) for line in lines)
    return named and not any(line.startswith("SCAN ") for line in lines)


def test_suppression_lookup_uses_the_phone_index(client, seeded):
    p = plan(client, "SELECT phone FROM recipients WHERE phone IN ('+919800000001', '+919800000002') "
                     "AND (opted_out = 1 OR consent_status = 'revoked')")
    assert uses(p, "ix_recipients_phone"), p


def test_participant_list_by_campaign_and_outcome_uses_its_composite_index(client, seeded):
    p = plan(client, "SELECT id FROM recipients WHERE campaign_id = :c AND outcome = 'pending'", c=seeded["campaigns"][0])
    assert uses(p, "ix_recipients_campaign_id_outcome"), p


def test_duplicate_check_inside_a_campaign_uses_the_unique_constraint(client, seeded):
    p = plan(client, "SELECT phone FROM recipients WHERE campaign_id = :c", c=seeded["campaigns"][0])
    assert uses(p, "uq_recipient_campaign_phone", table="recipients") or uses(p, "ix_recipients_campaign_id_outcome"), p


def test_scheduler_due_scan_uses_status_and_time(client, seeded):
    p = plan(client, "SELECT id FROM campaigns WHERE status = 'scheduled' AND scheduled_at <= '2030-01-01 00:00:00'")
    assert uses(p, "ix_campaigns_status_scheduled_at"), p


def test_event_campaign_listing_uses_the_event_index(client, seeded):
    p = plan(client, "SELECT id FROM campaigns WHERE event_id = :e AND status = 'draft'", e=seeded["event"])
    assert uses(p, "ix_campaigns_event_id_status"), p


def test_webhook_lookup_by_provider_call_id_uses_the_unique_index(client, seeded):
    p = plan(client, "SELECT id FROM call_attempts WHERE provider = 'exotel' AND provider_call_id = 'abc'")
    assert uses(p, "uq_call_attempts_provider_call"), p


def test_attempts_of_a_participant_use_the_attempt_number_constraint(client, seeded):
    p = plan(client, "SELECT id FROM call_attempts WHERE recipient_id = 1 ORDER BY attempt_number")
    assert uses(p, "uq_attempt_number", table="call_attempts"), p


def test_response_lookups_use_their_indexes(client, seeded):
    assert uses(plan(client, "SELECT id FROM intent_results WHERE call_attempt_id = 1"), "uq_intent_results_call_attempt_id", table="intent_results")
    assert uses(plan(client, "SELECT id FROM intent_results WHERE recipient_id = 1 ORDER BY id"), "ix_intent_results_recipient_id_id")
    assert uses(plan(client, "SELECT intent, COUNT(*) FROM intent_results WHERE campaign_id = 1 GROUP BY intent"),
                "ix_intent_results_campaign_id_intent")


def test_follow_up_queue_and_open_review_use_indexes(client, seeded):
    assert uses(plan(client, "SELECT id FROM follow_ups WHERE status IN ('pending', 'scheduled') ORDER BY scheduled_at"),
                "ix_follow_ups_status_scheduled_at")
    assert uses(plan(client, "SELECT id FROM follow_ups WHERE campaign_id = 1 AND status = 'pending'"),
                "ix_follow_ups_campaign_id_status")
    assert uses(plan(client, "SELECT id FROM follow_ups WHERE recipient_id = 1 AND action_type = 'human_review' "
                             "AND status IN ('pending', 'scheduled')"), "follow_ups")


def test_lead_lookups_use_their_indexes(client, seeded):
    assert uses(plan(client, "SELECT id FROM leads WHERE event_id = 1 AND status = 'new'"), "ix_leads_event_id_status")
    assert uses(plan(client, "SELECT id FROM leads WHERE phone = '+919800000001'"), "ix_leads_phone")
    assert uses(plan(client, "SELECT id FROM leads WHERE recipient_id = 1"), "ix_leads_recipient_id")


def test_repository_queries_are_index_backed_end_to_end(client, seeded):
    """The real repository statements, not hand-written look-alikes."""
    from sqlalchemy.dialects import sqlite
    from member2.backend.app.models import Recipient
    from sqlalchemy import select
    stmt = select(Recipient.phone).where(Recipient.phone.in_(["+919800000001"]))
    sql = str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert uses(plan(client, sql), "ix_recipients_phone")
