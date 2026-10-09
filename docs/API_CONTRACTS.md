# API Contracts (prefix `/api`; interactive docs at `/docs`)

**Errors:** `{"error": {"code": "...", "message": "...", "details": null | [{"field","message"}]}}` with codes `validation_error` (422), `not_found` (404), `invalid_state` (409), `duplicate` (409), `no_recipients` (422), `bad_csv` (422), `provider_unavailable` (503), `unauthorized` (401), `webhook_disabled` (503).

| Method & path | Purpose |
|---|---|
| GET `/health` | liveness + DB check |
| GET `/settings` | read-only config (no secrets), incl. `purposes` |
| POST `/events` | `{name, description?, approved_info{venue,schedule,reporting_time,submission_deadline}, organizer_contact?}` -> 201 (blank values dropped; unknown keys 422) |
| GET `/events`, `/events/{id}`; PATCH `/events/{id}` | list/view/update (includes `campaign_count`) |
| POST `/campaigns` | body `{event_id (required, 404 if unknown), name, purpose, messages{lang:text}, languages[], max_attempts 1-5, require_consent, scheduled_at?}` -> 201. `purpose` ∈ attendance_confirmation, event_announcement, schedule_venue_update, submission_deadline_reminder, participant_followup. `is_demo` (= simulated) is set by the server |
| GET `/campaigns?event_id=&status=`, `/campaigns/{id}` | list/view (includes `recipient_count`, `event_id`) |
| PATCH `/campaigns/{id}` | edit while draft/scheduled |
| POST `/campaigns/{id}/cancel` | -> cancelled (409 if terminal) |
| POST `/campaigns/{id}/start` | first-attempt dispatch; returns `{dispatched, skipped[{recipient_id, reason}]}` |
| POST `/campaigns/{id}/retry-due?force=` | dispatch due retries (`force` ignores backoff) |
| POST `/campaigns/{id}/recipients` | `{name, phone(E.164), external_ref?, preferred_language?, segment?, consent_status}` |
| POST `/campaigns/{id}/recipients/import` | multipart CSV `file` + `consent_confirmed`; columns in `docs/INTEGRATIONS.md`; returns `{imported, rejected, errors[]}` |
| POST `/campaigns/{id}/recipients/copy-from/{src}` | reuse eligible participants of another campaign of the same event (422 `different_event`); returns `{copied, skipped}` |
| GET `/campaigns/{id}/recipients` | list (filter: outcome) |
| GET `/recipients?event_id=&campaign_id=&outcome=&language=&attention=&opted_out=&retry_eligible=` | cross-campaign participant list; `attention` = unclear/human/callback/info/not-reached and not opted out |
| GET `/recipients/{id}/history` | `{recipient, attempts[], intents[], followups[]}` |
| POST `/recipients/{id}/opt-out` | operator-recorded opt-out |
| GET `/campaigns/{id}/attempts`, `/intents` | call attempts / classified responses |
| GET `/followups`, PATCH `/followups/{id}` | list; update status/scheduled_at |
| GET `/followups/queue?event_id=&campaign_id=` | open follow-ups enriched with participant, reason, latest outcome, recommended action, `priority` 1-3 (+ `priority_reason`), `is_simulated`; sorted by priority. Rules: P1 scheduled callback due ≤1h; P2 human review or callback without time; P3 information to relay |
| GET `/analytics?campaign_id=&event_id=&source=all\|real\|simulated` | metrics (adds `needs_attention`) |
| POST `/recipients/{id}/clarify`, POST `/campaigns/{id}/clarify` | **Clarify-once**: one short yes/no call (mode `clarify`) to participants whose attendance answer was *unclear*. 409 `clarify_not_allowed` unless: attendance campaign, outcome unclear, consent ok, not opted out, no prior clarification, no live call, provider has a clarify flow. Returns `{dispatched, skipped[]}` |
| GET `/settings/exotel-readiness` | checklist of required/optional Exotel settings (names only) + webhook URL templates |
| POST `/demo/seed`, DELETE `/demo` | simulated demo data (11 sample participants) |
| POST `/webhooks/demo` | inject simulated provider event `{event_id, provider_call_id, kind, status?, text?, dtmf?}` |
| POST `/webhooks/exotel?token=` | Exotel StatusCallback: `CallSid`, `Status` (JSON or form); attempt found by CallSid or `CustomField` |
| GET/POST `/webhooks/exotel/response?token=` | Passthru target: `CallSid`, `digits` (quotes stripped), `CustomField`; records answered + keypad response |
| (both) | need `EXOTEL_WEBHOOK_TOKEN` (503 if unset, 401 if wrong); idempotent |

`GET /analytics` additionally returns `headcount` (`{participants, confirmed, declined, unknown, unknown_breakdown, floor, ceiling, certainty}` or `null`) and `clarification` (`{attempted, resolved}`). Attempts carry `mode` (`main`|`clarify`). Queue items carry `can_clarify`, `clarification_attempted`.

**Provider interface** (`member3/integrations/base.py`): `initiate_call(attempt_id, attempt_number, to, language, message) -> InitiateResult(provider_call_id, events[])`, `cancel_call(id)`. Events: `ProviderEvent(event_id, provider_call_id, kind=status|response, status, text, dtmf, audio_ref)`; `(provider, event_id)` is unique.

**Keypad map:** 1 confirm (attendance campaigns) / acknowledge (others), 2 decline, 3 callback, 4 info, 9 opt-out.
**Intents → outcomes:** confirm→confirmed (attendance only, else acknowledged), decline→declined, callback_requested, information_requested, acknowledgement→acknowledged, opt_out→opted_out, unclear, human_required.
