"""SQLite storage. One shared connection guarded by a lock: the dialer thread, the live-call result sink and the
HTTP handlers all write. No transcripts or audio are ever stored here, only decisions."""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL DEFAULT 'webinar',
  mode TEXT NOT NULL DEFAULT 'in_person', venue TEXT DEFAULT '', event_date TEXT, event_time TEXT,
  organiser TEXT DEFAULT '', description TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS participants (
  id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name TEXT NOT NULL, phone TEXT NOT NULL, language TEXT DEFAULT '', segment TEXT DEFAULT '',
  custom_message TEXT DEFAULT '', fields TEXT DEFAULT '{}', opted_out INTEGER NOT NULL DEFAULT 0,
  can_call INTEGER NOT NULL DEFAULT 1, rsvp TEXT DEFAULT '', rsvp_at TEXT, rsvp_campaign_id INTEGER,
  created_at TEXT NOT NULL, UNIQUE(event_id, phone));
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT 'invite', language TEXT NOT NULL DEFAULT 'en',
  template TEXT NOT NULL, segment TEXT DEFAULT '', max_attempts INTEGER NOT NULL DEFAULT 3,
  status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL, launched_at TEXT,
  auto_retry INTEGER NOT NULL DEFAULT 1, retry_interval_min INTEGER NOT NULL DEFAULT 30);
CREATE TABLE IF NOT EXISTS calls (
  id INTEGER PRIMARY KEY, campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending', attendance TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  provider_call_id TEXT, message TEXT DEFAULT '', needs_review INTEGER NOT NULL DEFAULT 0,
  language_detected TEXT, method TEXT, requested_time TEXT, time_hint TEXT, info_topic TEXT,
  custom_message TEXT DEFAULT '', error TEXT DEFAULT '', next_attempt_at TEXT, last_event_id TEXT, updated_at TEXT NOT NULL, UNIQUE(campaign_id, participant_id));
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY, call_id INTEGER NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
  number INTEGER NOT NULL, provider_call_id TEXT, status TEXT NOT NULL DEFAULT 'dialing',
  started_at TEXT NOT NULL, ended_at TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  campaign_id INTEGER REFERENCES campaigns(id) ON DELETE CASCADE,
  participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  call_id INTEGER REFERENCES calls(id) ON DELETE SET NULL,
  kind TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open', note TEXT DEFAULT '',
  created_at TEXT NOT NULL, done_at TEXT);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_calls_campaign ON calls(campaign_id);
CREATE INDEX IF NOT EXISTS idx_attempts_pcid ON attempts(provider_call_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Db:
    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._c = sqlite3.connect(path, check_same_thread=False)
        self._c.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._c.executescript(SCHEMA)
            cols = {r["name"] for r in self._c.execute("PRAGMA table_info(calls)")}
            for tbl, name, ddl in (("calls", "next_attempt_at", "TEXT"), ("campaigns", "auto_retry", "INTEGER NOT NULL DEFAULT 1"),
                                   ("campaigns", "retry_interval_min", "INTEGER NOT NULL DEFAULT 30")):
                have = {r["name"] for r in self._c.execute(f"PRAGMA table_info({tbl})")}
                if name not in have:                        # databases created before automatic retries
                    self._c.execute(f"ALTER TABLE {tbl} ADD COLUMN {name} {ddl}")
            pcols = {r["name"] for r in self._c.execute("PRAGMA table_info(participants)")}
            for name, ddl in (("can_call", "INTEGER NOT NULL DEFAULT 1"), ("rsvp", "TEXT DEFAULT ''"),
                              ("rsvp_at", "TEXT"), ("rsvp_campaign_id", "INTEGER")):
                if name not in pcols:                   # databases created before consent / RSVP tracking
                    self._c.execute(f"ALTER TABLE participants ADD COLUMN {name} {ddl}")
            self._c.commit()
            if "custom_message" not in cols:            # databases created before messages became per-campaign
                self._c.execute("ALTER TABLE calls ADD COLUMN custom_message TEXT DEFAULT ''")
                self._c.execute("UPDATE calls SET custom_message=(SELECT custom_message FROM participants "
                                "WHERE participants.id=calls.participant_id) WHERE status='pending'")
                self._c.commit()

    def q(self, sql: str, args=()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._c.execute(sql, args).fetchall()]

    def one(self, sql: str, args=()) -> dict | None:
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql: str, args=()) -> int:
        """Execute a write; returns lastrowid."""
        with self._lock:
            cur = self._c.execute(sql, args)
            self._c.commit()
            return cur.lastrowid

    def insert(self, table: str, **vals) -> int:
        cols = ",".join(vals)
        return self.x(f"INSERT INTO {table} ({cols}) VALUES ({','.join('?' * len(vals))})", tuple(vals.values()))

    def update(self, table: str, row_id: int, **vals) -> None:
        if vals:
            self.x(f"UPDATE {table} SET {','.join(k + '=?' for k in vals)} WHERE id=?", (*vals.values(), row_id))


def loads(s: str | None) -> dict:
    try:
        v = json.loads(s or "{}")
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}
