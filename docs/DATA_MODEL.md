# Data Model

Tables (`member2/backend/app/models/entities.py`): `events` (name, description, `approved_info` JSON, organizer_contact, is_demo), `campaigns` (now `event_id` FK; `is_demo` = simulated-only, set when the event is the sample or the demo provider is configured), `recipients` (unique campaign+phone), `call_attempts` (unique recipient+attempt_number; `is_simulated`), `provider_events` (unique provider+event_id — duplicate ledger), `intent_results`, `follow_ups`. Timestamps are UTC, timezone-aware.

**Call status:** queued -> initiating -> ringing/answered -> completed; terminal failures: failed, busy, no_answer, voicemail; cancelled. (`states.py`)
**Recipient outcome:** pending, confirmed (= said they will attend; **intent, not verified check-in — Cadence records no check-in**), acknowledged, declined, callback_requested, information_requested, unclear, human_required, opted_out, no_response ("never reached" after retries exhausted).
**Campaign status:** draft/scheduled -> running -> completed | cancelled. A running campaign auto-completes when nobody can still be contacted automatically.

Only matched phrases / short normalized text are stored as `evidence` — no transcripts or recordings.

`call_attempts.mode`: `main` | `clarify` (the single yes/no follow-up call; at most one per participant, never counted as a retry; a failed clarification leaves the outcome `unclear` and the human-review follow-up open).

## Headcount range (`headcount_range`)
Attendance-confirmation campaigns only; one row per phone — the most recent *definite* answer (confirmed/declined) wins, otherwise the latest row. `floor` = confirmed; `ceiling` = participants − declined; `certainty` = (confirmed + declined) ÷ participants. Opted-out people are "not yet certain" (they cannot be called). A bound on **stated intent**, not a forecast and not check-in.

## Metric definitions (`member4/analytics/metrics.py`)
- **calls_finished:** attempts in a terminal status. **answered:** attempts with `answered_at`.
- **answer_rate** = answered ÷ finished attempts. **failure_rate** = (failed+busy+no_answer+voicemail) ÷ finished attempts.
- **completion_rate** = recipients whose outcome ≠ pending ÷ all recipients.
- **confirmation / decline / unclear rate** = recipients with that outcome ÷ recipients with ≥1 classified response (`recipients_responded`).
- **participants selected** = recipients rows in scope (a person in two campaigns counts twice; filter by campaign for a clean figure). **unique participants contacted** = distinct recipients with ≥1 attempt. **calls attempted** = attempts (≠ participants). Answered calls ≠ confirmed attendance. **needs_attention** = not opted out and outcome ∈ unclear, human_required, callback_requested, information_requested, no_response.
- Zero denominators return `null` (shown as "—"). `source` splits simulated (demo campaigns) from real.
- Outcomes are what recipients said on calls; no causal claim is made.
