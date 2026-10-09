"""Measure the hot queries on the OLD schema (frozen legacy dump) and the CURRENT one, with identical data.

    python -m member2.backend.scripts.benchmark_indexes [--rows 50000] [--repeat 200]

Both databases are scratch files in a temp folder. Reports the median time per query and the SQLite plan.
"""
import argparse
import shutil
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

from member2.backend.app.core import migrate

LEGACY_SQL = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "legacy_schema.sql"


def populate(con: sqlite3.Connection, n: int) -> None:
    """Valid under both schemas. n participants over 50 campaigns; ~60% called; leads, follow-ups, responses."""
    q = con.execute
    q("INSERT INTO events (id, name, description, approved_info, is_demo, created_at, updated_at) "
      "VALUES (1, 'Bench', '', '{}', 0, '2026-01-01 00:00:00', '2026-01-01 00:00:00')")
    q("""WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 50)
         INSERT INTO campaigns (id, event_id, name, purpose, messages, languages, status, scheduled_at, max_attempts,
                                require_consent, is_demo, created_at, updated_at)
         SELECT i, 1, 'Campaign ' || i, 'attendance_confirmation', '{"en":"x"}', '["en"]',
                CASE i % 4 WHEN 0 THEN 'scheduled' WHEN 1 THEN 'draft' WHEN 2 THEN 'running' ELSE 'completed' END,
                CASE WHEN i % 4 = 0 THEN datetime('2030-01-01', '+' || i || ' days') END, 3, 1, 0,
                '2026-01-01 00:00:00', '2026-01-01 00:00:00' FROM n""")
    q("""WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < :n)
         INSERT INTO recipients (id, campaign_id, name, phone, consent_status, opted_out, outcome, is_demo, created_at, updated_at)
         SELECT i, (i % 50) + 1, 'P' || i, '+91' || printf('%010d', 9000000000 + i),
                CASE WHEN i % 40 = 0 THEN 'revoked' ELSE 'granted' END, CASE WHEN i % 40 = 0 THEN 1 ELSE 0 END,
                CASE WHEN i % 40 = 0 THEN 'opted_out' WHEN i % 5 < 3 THEN 'confirmed' ELSE 'pending' END, 0,
                '2026-01-01 00:00:00', '2026-01-01 00:00:00' FROM n""", {"n": n})
    q("""INSERT INTO call_attempts (id, campaign_id, recipient_id, provider, is_simulated, provider_call_id, attempt_number,
                                   mode, call_language, status, created_at)
         SELECT id, campaign_id, id, 'exotel', 0, 'CA' || printf('%012d', id), 1, 'main', 'en', 'completed', '2026-01-01 00:00:00'
         FROM recipients WHERE outcome != 'pending'""")
    q("""INSERT INTO intent_results (id, call_attempt_id, recipient_id, campaign_id, intent, score, method, detected_language,
                                    evidence, notes, needs_review, next_action, processing_status, created_at)
         SELECT id, id, recipient_id, campaign_id, 'confirm', 1.0, 'dtmf', 'unknown', 'dtmf:1', '[]', 0, 'record_outcome',
                'processed', '2026-01-01 00:00:00' FROM call_attempts""")
    q("""INSERT INTO follow_ups (campaign_id, recipient_id, action_type, status, scheduled_at, note, created_at)
         SELECT campaign_id, id, 'callback', CASE WHEN id % 3 = 0 THEN 'pending' WHEN id % 3 = 1 THEN 'scheduled' ELSE 'completed' END,
                datetime('2030-01-01', '+' || (id % 400) || ' hours'), '', '2026-01-01 00:00:00'
         FROM recipients WHERE id % 10 = 0""")
    q("""WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < :n)
         INSERT INTO leads (event_id, name, phone, source, consent_status, status, notes, is_demo, created_at, updated_at)
         SELECT 1, 'L' || i, '+91' || printf('%010d', 7000000000 + i), 'manual',
                CASE WHEN i % 25 = 0 THEN 'revoked' ELSE 'granted' END, 'new', '', 0,
                '2026-01-01 00:00:00', '2026-01-01 00:00:00' FROM n""", {"n": n // 2})
    con.commit()


def queries(n: int) -> list[tuple[str, str, tuple]]:
    phones = tuple(f"+91{9000000000 + k * 997:010d}" for k in range(1, 21))
    marks = ", ".join("?" * len(phones))
    lead_phones = tuple(f"+91{7000000000 + k * 97:010d}" for k in range(1, 21))
    return [
        ("opt-out lookup (20 numbers)", f"SELECT phone FROM recipients WHERE phone IN ({marks}) AND (opted_out = 1 OR consent_status = 'revoked')", phones),
        ("revoked-lead lookup (20 numbers)", f"SELECT phone FROM leads WHERE phone IN ({marks}) AND consent_status = 'revoked'", lead_phones),
        ("campaign participants by outcome", "SELECT id FROM recipients WHERE campaign_id = ? AND outcome = 'pending'", (7,)),
        ("scheduler: scheduled campaigns due", "SELECT id FROM campaigns WHERE status = 'scheduled' AND scheduled_at <= '2030-02-01 00:00:00'", ()),
        ("webhook: attempt by provider call id", "SELECT id FROM call_attempts WHERE provider = 'exotel' AND provider_call_id = ?", (f"CA{n // 2:012d}",)),
        ("work queue: open follow-ups by time", "SELECT id FROM follow_ups WHERE status IN ('pending', 'scheduled') ORDER BY scheduled_at LIMIT 50", ()),
        ("analytics: responses by intent", "SELECT intent, COUNT(*) FROM intent_results WHERE campaign_id = ? GROUP BY intent", (7,)),
        ("latest response of a participant", "SELECT id FROM intent_results WHERE recipient_id = ? ORDER BY id DESC LIMIT 1", (n // 2,)),
    ]


def median_ms(con, sql, params, repeat) -> float:
    times = []
    for _ in range(repeat):
        t = time.perf_counter()
        con.execute(sql, params).fetchall()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times)


def plan(con, sql, params) -> str:
    lines = [r[3] for r in con.execute("EXPLAIN QUERY PLAN " + sql, params)]
    return " | ".join(lines)[:90]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=50000, help="participants (leads = half)")
    ap.add_argument("--repeat", type=int, default=200)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="cadence-bench-"))
    try:
        old, new = tmp / "old.db", tmp / "new.db"
        con_old = sqlite3.connect(old)
        con_old.executescript(LEGACY_SQL.read_text(encoding="utf-8"))
        populate(con_old, args.rows)
        con_old.execute("ANALYZE")
        migrate.upgrade_database(f"sqlite:///{new.as_posix()}")
        con_new = sqlite3.connect(new)
        populate(con_new, args.rows)
        con_new.execute("ANALYZE")
        print(f"{args.rows:,} participants, {args.rows // 2:,} leads, median of {args.repeat} runs (ms)\n")
        print(f"{'query':40} {'old':>9} {'new':>9} {'speed-up':>9}   plan on the new schema")
        for name, sql, params in queries(args.rows):
            a, b = median_ms(con_old, sql, params, args.repeat), median_ms(con_new, sql, params, args.repeat)
            print(f"{name:40} {a:9.3f} {b:9.3f} {a / b:8.1f}x   {plan(con_new, sql, params)}")
        con_old.close()
        con_new.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
