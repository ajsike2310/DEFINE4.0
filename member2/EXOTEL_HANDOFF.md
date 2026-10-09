# Exotel handoff: backend (member 2) to provider (member 3)

**Backend status: ready.** Everything around the provider is built, tested (336 tests, none of them against a live Exotel) and
safe to point at a real account. What is *not* done is the part only a live account can settle: the real payloads. The backend
records them for you (below), so the first live call tells you exactly what to adjust.

## Dry run first (no Exotel account needed)
`python -m member2.backend.scripts.exotel_rehearsal` starts a stand-in Exotel and a real backend on a scratch database, runs the
REAL `ExotelProvider` against it, and drives readiness, a campaign, Passthru and StatusCallback callbacks, a duplicate, a wrong token,
a lost result and the webhook log: 22 checks. Run it after any change on either side. It proves the two halves agree with
Exotel's *documented* shapes; only a live call proves Exotel itself does.

## Start here (in this order)
1. **Keys into `.env`** (git-ignored; never in chat, tickets or commits): `EXOTEL_ACCOUNT_SID`, `EXOTEL_API_KEY`,
   `EXOTEL_API_TOKEN`, `EXOTEL_CALLER_ID` (your ExoPhone), `EXOTEL_FLOW_URL`, `CALL_PROVIDER=exotel`, and **`EXOTEL_ALLOWED_NUMBERS`
   = your own test numbers**. `EXOTEL_WEBHOOK_TOKEN` is already generated. `EXOTEL_BASE_URL` must match your Exotel cluster
   (`https://api.exotel.com` Singapore, `https://api.in.exotel.com` Mumbai; a wrong region fails authentication).
   `REAL_CALLS_PER_START=3` is set for the first test; raise it later.
2. **Tunnel:** `ngrok http 8000` (or cloudflared), put its https address in `PUBLIC_BASE_URL`, restart the backend.
3. **Check:** `python -m member2.backend.app.cli exotel doctor --probe`. It lists what is missing in plain words, proves the tunnel
   reaches this backend, and prints the two URLs to paste into Exotel (StatusCallback and the Passthru GET URL).
4. **Smoke call** to your own phone: `python scripts\exotel_check.py --call +91XXXXXXXXXX --yes`.
5. **Real campaign:** create a **new** event (not a sample one; sample events are simulated and can never reach Exotel), a campaign
   in it, add yourself with consent, press Start. The attempt shows **Real**.
6. **Watch it arrive:** `python -m member2.backend.app.cli exotel webhooks` (or `GET /api/webhooks/log`). Every authenticated
   callback is kept, masked, with how the backend handled it (`applied`, `duplicate`, `unknown_call`, `unrecognised_payload`).

## The contract

### What the backend calls
`member3/integrations/factory.build_provider(settings)` builds the provider (it reads `exotel_*`, `public_base_url`, the allow-list).
The backend then calls:

| Call | Expectation |
|---|---|
| `provider.initiate_call(attempt_id, attempt_number, to, language, message, mode)` | Place the call. Return `InitiateResult(provider_call_id)` with **no events** (real providers report through callbacks). `attempt_id` must travel as Exotel `CustomField`: callbacks that arrive before we saved the call SID are matched by it. |
| `ProviderError` from `initiate_call` | Raise it for any placement failure (HTTP error, missing SID). The backend records the attempt as **failed** with your message (first 200 characters: **no secrets, no phone numbers**) and schedules a bounded retry. |
| `provider.get_call_status(sid)` (optional) | Return Exotel's Call Details dict (needs a `Status` key). Used by reconcile; if absent, reconcile reports "this provider cannot report call status". |
| attributes | `name = "exotel"`, `is_simulated = False`, `supports_clarify` (False when no clarify flow is configured). |

The backend already stops real calls to numbers outside `EXOTEL_ALLOWED_NUMBERS` before it creates an attempt (the participant is
skipped with a reason); keep your own check too. Clarify-once calls arrive as `mode="clarify"` and should use the clarify flow.

### What Exotel sends back (handled in `services/exotel_webhooks.py`)
| Endpoint | Meaning | Our handling |
|---|---|---|
| `POST /api/webhooks/exotel?token=...` | StatusCallback (`CallSid`, `Status`, ...; form or JSON) | `Status` mapped through `STATUS_MAP` in your `exotel/provider.py` to `answered / completed / failed / busy / no_answer`; event id `"{CallSid}:{status}"` |
| `GET or POST /api/webhooks/exotel/response?token=...` | Passthru after the keypad Gather (`CallSid`, `CustomField`, `digits`) | records "answered", then the keypad response; quotes around `digits` are stripped; event id `"{CallSid}:digits:{digits}"`; keys 1 confirm, 2 decline, 3 call me back, 4 information, 9 stop |

Attempts are found by `CallSid`, else by `CustomField`. Duplicates are harmless (the event ledger rejects a repeated id). A terminal
status without an earlier "answered" is accepted. `completed` does not mean the person answered *and replied*: the outcome only
changes when a keypad response arrives. If your `STATUS_MAP` gains a status, the backend picks it up (it imports your map).

### Failure handling you get for free
* Placement failed -> failed attempt + retry with backoff, at most `max_attempts`, then the participant is `no_response`.
* Callback never arrived -> after `STALE_CALL_MINUTES` (20) `POST /api/campaigns/{id}/reconcile` (the scheduler does it too when on)
  asks `get_call_status` and applies the answer with the same event id as the callback, so a late callback is a duplicate.
  A call with no SID at all is closed as failed **without** retry (it might have been placed; retrying could dial twice).
* Opt-out (keypad 9 or recorded) applies to every record of that number; nothing is dialled again.

## Safety rails already in the backend
Allow-list pre-check; `REAL_CALLS_PER_START` cap (held-back participants stay pending, press Start again); pacing to
`EXOTEL_MAX_CALLS_PER_MINUTE` (200, Exotel's documented limit); shared-secret token on callbacks (>=16 characters, constant-time
compare, 401 otherwise, nothing stored for bad tokens); callbacks masked in the log; sample campaigns can never use a real provider;
retries bounded; settings validated at start-up (bad region URL, short token, malformed allow-list are refused with a message).

## Still unverified: confirm on the first live call, then tell member 2 what differs
1. The real StatusCallback body (field names, casing, JSON or form). *Look at the log.*
2. Whether Passthru's `CallSid` equals the SID returned when the call was placed (we fall back to `CustomField`).
3. That Passthru fires before the terminal StatusCallback (if not: the completed status arrives first and is accepted, the keypad
   response still counts because `answered` is recorded at Passthru time).
4. `digits` formatting.
5. Whether 200 calls per minute is the right pacing for your account (it is the documented figure, not measured).
6. Call Details `Status` values (reconcile assumes the same spellings as the callbacks).
7. Everything about Malayalam voice, speech capture and DLT/TRAI rules (not our code; see `docs/EXOTEL_INTEGRATION.md`).

If a field name differs, the one place to change is `_status` / `_response` in `services/exotel_webhooks.py`
(tests: `tests/test_exotel_ready.py`, `member4/quality/integration/test_clarify_and_headcount.py`).

## Commands
```
python -m member2.backend.app.cli exotel doctor [--probe]   readiness, in words; exit code 1 until ready
python -m member2.backend.app.cli exotel webhooks -n 20     last callbacks, masked
python -m member2.backend.app.cli db check | backup | stats  data health
GET  /api/settings/exotel-readiness?probe=true               the same readiness as JSON (the Settings page uses it)
GET  /api/webhooks/log?ok=false                              only callbacks that failed to apply
POST /api/campaigns/{id}/reconcile?minutes=0                 ask Exotel about every open real call now
POST /api/scheduler/tick                                     one scheduler pass on demand
```
Tests never read your real `.env` (a repo-level `conftest.py` blanks the Exotel and ElevenLabs variables for pytest), so filling it
in cannot break the suite.
