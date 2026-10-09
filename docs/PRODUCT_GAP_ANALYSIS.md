# Product Gap Analysis (audit of the existing "Define Cadence" build → Cadence for events)

Baseline audited before changes: not a git repo; 49 backend tests passing; frontend built; workflow verified with the simulated provider.

| Area | Existing state | Decision |
|---|---|---|
| Provider abstraction, demo provider, Exotel adapter | Working / mock-tested | **Reused unchanged** (demo scenarios retuned to event phrasing; allowlist + webhook token kept) |
| Duplicate-event ledger, state machine, bounded retries, consent/opt-out | Working, tested | **Reused**; one fix: terminal-only `completed` callback (no prior `answered`) is now accepted, otherwise a real call could stay "initiating" forever |
| Campaign model | Generic purposes, no event | **Modified**: `event_id` required; purposes → attendance, announcement, schedule/venue update, submission-deadline reminder, participant follow-up |
| Event concept | Missing | **Added**: `events` table, CRUD API, `approved_info` (venue/schedule/reporting_time/submission_deadline) |
| Intents | confirm/decline/callback/info/opt-out/unclear/human | **Added** acknowledgement; confirm→acknowledged for non-attendance campaigns; info topic detection; callback time hint |
| Info requests | Generic follow-up | **Modified**: answer only from approved info, else human review (never invented) |
| Participants | Per-campaign recipients, phone only | **Modified**: `external_ref` (participant id), CSV `participant_id`/`opted_out`, reuse from another campaign of the same event, filters (unresolved, callback, retry-eligible, opted-out), per-participant history |
| Follow-ups | Flat list | **Added**: prioritised queue with participant, reason, latest outcome, recommended action (fixed rules P1–P3) |
| Analytics | Campaign-level; "real" filter keyed on campaign flag | **Modified**: event filter, `acknowledged`, `needs_attention`; **bug fixed**: demo-provider campaigns created via the wizard were counted as "real" — campaigns are now simulated whenever the demo provider is configured or the event is the sample |
| Frontend | Generic campaign app | **Modified**: Cadence branding, event selector, event-scoped dashboard, wizard (purpose → message → participants → review, launch/draft, double-click guard, placeholder guard), Participants, Follow-up queue, Events pages |
| Seed data | Clinic appointments | **Replaced** by labelled DEFINE 4.0 sample |
| Scheduling | Not implemented | **Still open** (wizard says so) |
| Exotel live / DTMF-speech return / STT | Unverified | **Still blocked** (no credentials) |
| Browser-level testing | None | **Partial**: jsdom render tests with mocked API; no real-browser run |
| Migrations | None | Still none; startup now fails with a clear message on an old-schema DB |
