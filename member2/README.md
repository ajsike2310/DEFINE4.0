# Member 2: Backend and data

FastAPI + SQLAlchemy 2 + SQLite with Alembic migrations. Every URL is under `/api`; interactive docs at `/docs`.
The checklist of what was built and how it was verified is in [`CHECKLIST.md`](CHECKLIST.md). **Integrating Exotel? Start with [`EXOTEL_HANDOFF.md`](EXOTEL_HANDOFF.md).**

## Layers (enforced by `backend/tests/test_architecture.py`)
```
api/routers  ->  services  ->  repositories  ->  models  ->  core
 HTTP only        rules         every query        tables     config, db, errors, migrations
```
```
backend/app/
  main.py          app factory: CORS, request ids + access log, error envelope, optional scheduler loop, migrate at start-up
  cli.py           `db` commands (upgrade, downgrade, current, history, check, backup, stats, optimize) and `exotel`
                   commands (doctor [--probe], webhooks)
  api/             routes.py assembles the routers; deps.py; routers/ (system, events, campaigns, participants, followups,
                   leads, insights, demo, webhooks, browser_calls). A router parses the request and calls a service or a repository.
  services/        campaigns (lifecycle, dispatch, retries, clarify-once)  events (provider events -> outcomes)  participants
                   leads  suppression (global opt-out)  catalog  scheduler  exports  csv_io  overview  queue  presenters
                   browser_calls  providers  states  demo (sample-data tooling)
                   exotel_webhooks (callbacks -> events)  webhook_log (masked)  readiness  reconcile  pacing
  repositories/    events, campaigns, recipients, attempts, intents, followups, leads, webhook_logs, health. Never commit.
  models/          enums.py (closed vocabularies) + events.py, calling.py, leads.py, webhooks.py (tables, constraints, indexes)
  schemas/         request/response shapes: common, events, campaigns, participants, followups, leads, webhooks
                   (api.py re-exports them all)
  core/            config (validated), db (engine + pragmas), errors, ratelimit, migrate, dbtools, logs
backend/migrations/  Alembic env, versions 0001-0003, frozen schema snapshots, rebuild helper (README inside)
backend/tests/       this package's own tests, in addition to the shared suites in member3 and member4
backend/scripts/     benchmark_indexes.py, exotel_rehearsal.py (22-check dry run of the Exotel path against a stand-in server)
```

## Run
From the repo root: `.venv\Scripts\python.exe -m uvicorn member2.backend.app.main:app --port 8000`. The database
(`data/app.db`) is migrated to the latest revision at start-up, with a backup in `data/backups/` first if anything changes.
Tests: `.venv\Scripts\python.exe -m pytest member2` (everything: `pytest`).

## The database
* Constraints: CHECKs from the shared enums, E.164 phones, numeric ranges, foreign keys with explicit ON DELETE rules (enforced),
  one response per call, one open human review per participant, one provider call id per attempt.
* 24 named indexes and unique constraints, each tied to a query; guard tests check every foreign key is covered and none is redundant.
* WAL, busy timeout, foreign keys on. `python -m member2.backend.app.cli db check` audits integrity and consistency;
  `GET /api/health/database` returns the same report, `GET /api/health` the schema revision.
* Full description with an entity diagram: [`docs/DATA_MODEL.md`](../docs/DATA_MODEL.md). Writing a migration: [`backend/migrations/README.md`](backend/migrations/README.md).

## Behaviour worth knowing
* **Real calls (Exotel):** paced to the provider's rate limit, optionally capped per Start press (`REAL_CALLS_PER_START`), refused
  outside `EXOTEL_ALLOWED_NUMBERS`, retried (bounded) after a failed placement, and reconciled with the provider when a result
  never arrives. Every authenticated callback is kept, masked, at `GET /api/webhooks/log`.
* **Opt-out wins everywhere.** An opt-out applies to every record of that number in scope; such numbers cannot be added, imported,
  copied or converted again (same event always; real data across events; sample data stays inside its own event).
* **Scheduler** (off by default, `SCHEDULER_ENABLED=true`): starts explicitly scheduled campaigns and runs due retries;
  `POST /api/scheduler/tick` runs one pass.
* **Public sign-up** is throttled per client address; organiser entries are not.
* **Exports:** `GET /events/{id}/export/participants.csv` and `leads.csv`, masked unless `?masked=false`, spreadsheet-safe.
* **Observability:** `X-Request-ID` on every response; the access log never contains query strings or bodies.
* **Config fails fast** on bad values.

## Not done
No authentication; SQLite and one process only (rate limiter and scheduler state are in memory); no pause/resume.
