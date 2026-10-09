# Member 2 — Backend & data
`backend/app`: `api/routes.py` (HTTP only), `services/` (campaigns, events, states, demo), `models/entities.py`, `schemas/api.py`, `core/` (config, db). Tests live in `member4/quality`.
Run from repo root: `$env:PYTHONPATH=(pwd).Path; .venv\Scripts\python.exe -m uvicorn member2.backend.app.main:app --port 8000`. DB auto-created at `data/app.db`.
Next: Alembic, auth, scheduler for `scheduled_at`/due retries/follow-ups, Postgres.
