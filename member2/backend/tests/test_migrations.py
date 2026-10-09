"""Migrations: they reproduce the shipped schema, match the models exactly, and upgrade real data safely."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from member2.backend.app import cli
from member2.backend.app.core import dbtools, migrate
from member2.backend.app.core.db import Base
from member2.backend.app.main import create_app
from member2.backend.migrations import rebuild
from member2.backend.migrations.dump_schema import dump, models_schema, normalise

LEGACY_SQL = Path(__file__).parent / "fixtures" / "legacy_schema.sql"
ROOT = Path(__file__).resolve().parents[3]
TS = "2026-01-01 10:00:00.000000"
HEAD = "0003"
TABLES = ["events", "campaigns", "recipients", "call_attempts", "provider_events", "intent_results", "follow_ups",
          "leads", "import_runs"]


def url_of(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def counts(path: Path) -> dict:
    con = sqlite3.connect(path)
    try:
        return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in TABLES}
    finally:
        con.close()


def schema_of(path: Path) -> list[tuple]:
    engine = create_engine(url_of(path))
    try:
        return normalise(dump(engine))
    finally:
        engine.dispose()


def legacy_db(tmp_path: Path, name="app.db", with_data=True, drop_tables=()) -> Path:
    """A database exactly as earlier builds left it: no version table, no new constraints, real-looking rows."""
    path = tmp_path / name
    con = sqlite3.connect(path)
    con.executescript(LEGACY_SQL.read_text(encoding="utf-8"))
    for t in drop_tables:
        con.execute(f"DROP TABLE {t}")
    if with_data:
        ins = lambda table, **v: con.execute(                                                      # noqa: E731
            f"INSERT INTO {table} ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})", list(v.values()))
        ins("events", id=1, name="Hack Night", description="", approved_info='{"venue": "Hall A"}', is_demo=0,
            created_at=TS, updated_at=TS)
        for cid, status in ((1, "completed"), (2, "draft")):
            ins("campaigns", id=cid, event_id=1, name=f"Campaign {cid}", purpose="attendance_confirmation",
                messages='{"en": "Press 1"}', languages='["en"]', status=status, max_attempts=3, require_consent=1,
                is_demo=0, created_at=TS, updated_at=TS)
        people = [(1, 1, "Asha", "+919876543210", "granted", 0, "confirmed"), (2, 1, "Ben", "+919876543211", "granted", 0, "pending"),
                  (3, 1, "Chitra", "+919876543212", "revoked", 1, "opted_out"), (4, 2, "Asha", "+919876543210", "granted", 0, "pending")]
        for rid, cid, name, phone, consent, out, outcome in people:
            ins("recipients", id=rid, campaign_id=cid, name=name, phone=phone, consent_status=consent, opted_out=out,
                outcome=outcome, is_demo=0, created_at=TS, updated_at=TS)
        ins("call_attempts", id=1, campaign_id=1, recipient_id=1, provider="demo", is_simulated=1, provider_call_id="demo-1",
            attempt_number=1, mode="main", call_language="en", status="completed", created_at=TS)
        ins("provider_events", id=1, provider="demo", event_id="demo-1:answered", call_attempt_id=1, kind="status",
            result="applied", received_at=TS)
        ins("intent_results", id=1, call_attempt_id=1, recipient_id=1, campaign_id=1, intent="confirm", score=1.0,
            method="dtmf", detected_language="unknown", evidence="dtmf:1", notes="[]", needs_review=0,
            next_action="record_outcome", processing_status="processed", created_at=TS)
        ins("follow_ups", id=1, campaign_id=1, recipient_id=2, source_intent_id=1, action_type="human_review",
            status="pending", note="check", created_at=TS)
        ins("leads", id=1, event_id=1, name="Asha", phone="+919876543210", source="registration_form",
            consent_status="granted", status="converted", notes="", recipient_id=1, is_demo=0, created_at=TS, updated_at=TS)
        ins("import_runs", id=1, kind="leads", event_id=1, filename="x.csv", rows_total=3, imported=2, rejected=1,
            reasons='{"duplicate phone": 1}', is_demo=0, created_at=TS)
    con.commit()
    con.close()
    return path


def fresh_db(tmp_path, upto="head", name="fresh.db") -> Path:
    path = tmp_path / name
    migrate.upgrade_database(url_of(path), upto)
    return path


# ---- the schema the migrations produce -------------------------------------------------------------------------
def test_baseline_revision_reproduces_the_shipped_schema(tmp_path):
    from_migration = schema_of(fresh_db(tmp_path, "0001"))
    from_old_build = schema_of(legacy_db(tmp_path, with_data=False))
    assert from_migration == from_old_build


def test_head_schema_is_exactly_what_the_models_declare(tmp_path):
    migrated = schema_of(fresh_db(tmp_path))
    assert migrated == normalise(models_schema()), "models changed without a migration (see migrations/README.md)"


def test_autogenerate_finds_no_difference_between_models_and_migrations(tmp_path):
    engine = create_engine(url_of(fresh_db(tmp_path)))
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    finally:
        engine.dispose()
    assert diff == []


def test_frozen_snapshot_matches_the_models():
    assert normalise(rebuild.load("v3")) == normalise(models_schema())


def test_revision_chain_is_linear_and_head_is_known():
    assert migrate.head_revision() == HEAD


# ---- upgrading databases that already hold data -----------------------------------------------------------------
def test_legacy_database_is_adopted_and_upgraded_without_losing_anything(tmp_path):
    path = legacy_db(tmp_path)
    before = counts(path)
    ids_before = sqlite3.connect(path).execute("SELECT id, phone, outcome FROM recipients ORDER BY id").fetchall()
    info = migrate.upgrade_database(url_of(path))
    assert info["adopted_legacy"] is True and info["from"] == "0001" and info["to"] == HEAD
    assert counts(path) == before
    con = sqlite3.connect(path)
    assert con.execute("SELECT id, phone, outcome FROM recipients ORDER BY id").fetchall() == ids_before
    assert con.execute("SELECT version_num FROM alembic_version").fetchall() == [(HEAD,)]
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert con.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert con.execute("SELECT updated_at = created_at FROM follow_ups").fetchone() == (1,)      # new column backfilled
    assert schema_of(path) == normalise(models_schema())
    with pytest.raises(sqlite3.IntegrityError, match="phone_e164"):
        con.execute("UPDATE recipients SET phone = '123' WHERE id = 1")
    con.close()


def test_a_backup_is_written_first_and_is_a_faithful_copy(tmp_path):
    path = legacy_db(tmp_path)
    before = counts(path)
    info = migrate.upgrade_database(url_of(path))
    backup = Path(info["backup"])
    assert backup.parent == tmp_path / "backups" and backup.exists()
    assert counts(backup) == before
    assert "alembic_version" not in {r[0] for r in sqlite3.connect(backup).execute("SELECT name FROM sqlite_master")}


def test_an_empty_or_current_database_needs_no_backup(tmp_path):
    first = migrate.upgrade_database(url_of(tmp_path / "new.db"))
    assert first["backup"] is None and first["to"] == HEAD and not (tmp_path / "backups").exists()
    again = migrate.upgrade_database(url_of(tmp_path / "new.db"))
    assert again["backup"] is None and again["from"] == again["to"] == HEAD


def test_tables_added_after_the_first_release_are_created_when_adopting(tmp_path):
    path = legacy_db(tmp_path, with_data=False, drop_tables=("leads", "import_runs"))
    migrate.upgrade_database(url_of(path))
    assert schema_of(path) == normalise(models_schema())


def test_data_that_breaks_a_new_rule_stops_the_migration_and_changes_nothing(tmp_path):
    path = legacy_db(tmp_path)
    con = sqlite3.connect(path)
    con.execute("UPDATE recipients SET phone = '12345' WHERE id = 2")
    con.commit()
    con.close()
    legacy_shape = schema_of(path)
    with pytest.raises(rebuild.MigrationDataError, match="recipients.*Nothing was changed"):
        migrate.upgrade_database(url_of(path))
    assert schema_of(path) == legacy_shape                       # still the old schema, no half-built tables
    names = {r[0] for r in sqlite3.connect(path).execute("SELECT name FROM sqlite_master")}
    assert "alembic_version" not in names and not any(n.endswith("__old") for n in names)
    assert counts(path)["recipients"] == 4
    fixed = sqlite3.connect(path)
    fixed.execute("UPDATE recipients SET phone = '+919876543299' WHERE id = 2")
    fixed.commit()
    fixed.close()
    assert migrate.upgrade_database(url_of(path))["to"] == HEAD          # and it succeeds once the data is fixed


def test_rows_pointing_at_missing_records_stop_the_migration(tmp_path):
    path = legacy_db(tmp_path)
    con = sqlite3.connect(path)
    con.execute("UPDATE call_attempts SET recipient_id = 999 WHERE id = 1")
    con.commit()
    con.close()
    with pytest.raises(rebuild.MigrationDataError, match="do not exist"):
        migrate.upgrade_database(url_of(path))
    assert counts(path)["call_attempts"] == 1


def test_duplicate_responses_for_one_call_stop_the_migration(tmp_path):
    path = legacy_db(tmp_path)
    con = sqlite3.connect(path)
    con.execute("INSERT INTO intent_results (call_attempt_id, recipient_id, campaign_id, intent, score, method, "
                "detected_language, evidence, notes, needs_review, next_action, processing_status, created_at) "
                "SELECT call_attempt_id, recipient_id, campaign_id, intent, score, method, detected_language, evidence, "
                "notes, needs_review, next_action, processing_status, created_at FROM intent_results")
    con.commit()
    con.close()
    with pytest.raises(rebuild.MigrationDataError, match="intent_results"):
        migrate.upgrade_database(url_of(path))


# ---- going back ----------------------------------------------------------------------------------------------------
def test_downgrade_restores_the_baseline_schema_and_keeps_every_row(tmp_path):
    path = legacy_db(tmp_path)
    before = counts(path)
    migrate.upgrade_database(url_of(path))
    info = migrate.downgrade_database(url_of(path), "0001")
    assert info["to"] == "0001" and Path(info["backup"]).exists()
    assert counts(path) == before
    assert schema_of(path) == schema_of(legacy_db(tmp_path, "pristine.db", with_data=False))
    assert migrate.upgrade_database(url_of(path))["to"] == HEAD           # and forward again


# ---- the app and the tools use it ---------------------------------------------------------------------------------
def test_starting_the_app_on_a_legacy_database_migrates_it_and_serves_its_data(tmp_path):
    path = legacy_db(tmp_path)
    with TestClient(create_app(url_of(path))) as client:
        assert [e["name"] for e in client.get("/api/events").json()] == ["Hack Night"]
        assert len(client.get("/api/recipients").json()) == 4
        health = client.get("/api/health").json()
        assert health["schema"] == {"managed_by": "alembic", "current": HEAD, "head": HEAD, "up_to_date": True}
        assert client.get("/api/health/database").json()["check"]["ok"] is True
        assert client.post("/api/events", json={"name": "Second event"}).status_code == 201


def test_a_running_database_uses_foreign_keys_wal_and_a_busy_timeout(tmp_path):
    app = create_app(url_of(tmp_path / "live.db"))
    with app.state.engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert c.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
    app.state.engine.dispose()


def test_backups_are_pruned_to_the_newest_few(tmp_path):
    path = legacy_db(tmp_path)
    made = [migrate.backup_database(url_of(path), label="t", keep=3) for _ in range(6)]
    kept = sorted((tmp_path / "backups").glob("*.db"))
    assert len(kept) == 3 and set(kept) <= set(made)


def test_command_line_tools(tmp_path, capsys):
    path = legacy_db(tmp_path)
    url = url_of(path)
    assert cli.main(["--url", url, "db", "upgrade"]) == 0
    assert cli.main(["--url", url, "db", "current"]) == 0
    assert json.loads(capsys.readouterr().out.split("}\n", 1)[1])["up_to_date"] is True
    assert cli.main(["--url", url, "db", "check"]) == 0
    assert cli.main(["--url", url, "db", "stats"]) == 0
    assert cli.main(["--url", url, "db", "backup"]) == 0
    assert cli.main(["--url", url, "db", "optimize"]) == 0
    assert cli.main(["--url", url, "db", "history"]) == 0


def test_check_command_fails_loudly_when_data_is_inconsistent(tmp_path):
    path = fresh_db(tmp_path)
    con = sqlite3.connect(path)
    con.executescript("INSERT INTO events (id, name) VALUES (1, 'E'); "
                      "INSERT INTO campaigns (id, event_id, name, messages, languages, is_demo) VALUES (1, 1, 'C1', '{}', '[\"en\"]', 0); "
                      "INSERT INTO recipients (id, campaign_id, name, phone, opted_out, outcome, consent_status, is_demo) "
                      "VALUES (1, 1, 'P', '+919876543210', 1, 'confirmed', 'granted', 0);")      # opted out but "confirmed"
    con.commit()
    con.close()
    engine = create_engine(url_of(path))
    report = dbtools.integrity_report(engine)
    engine.dispose()
    assert report["ok"] is False
    assert [r["key"] for r in report["rules"] if r["violations"]] == ["opt_out_wins"]
    assert cli.main(["--url", url_of(path), "db", "check"]) == 1


def test_the_alembic_command_line_works_against_the_same_database(tmp_path):
    path = legacy_db(tmp_path)
    migrate.upgrade_database(url_of(path))
    env = {**os.environ, "DATABASE_URL": url_of(path), "PYTHONPATH": str(ROOT)}
    out = subprocess.run([sys.executable, "-m", "alembic", "-c", "member2/backend/alembic.ini", "current"], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert HEAD in out.stdout + out.stderr


# ---- revision 0003 (webhook log) ----------------------------------------------------------------------------------
def test_upgrading_from_0002_adds_only_the_webhook_log_table_and_keeps_all_data(tmp_path):
    path = legacy_db(tmp_path)
    migrate.upgrade_database(url_of(path), "0002")
    before = counts(path)
    assert "webhook_logs" not in {r[0] for r in sqlite3.connect(path).execute("SELECT name FROM sqlite_master")}
    info = migrate.upgrade_database(url_of(path))
    assert info["from"] == "0002" and info["to"] == HEAD and Path(info["backup"]).exists()
    assert counts(path) == before
    assert schema_of(path) == normalise(models_schema())
    down = migrate.downgrade_database(url_of(path), "0002")
    assert down["to"] == "0002" and counts(path) == before
    assert "webhook_logs" not in {r[0] for r in sqlite3.connect(path).execute("SELECT name FROM sqlite_master")}
