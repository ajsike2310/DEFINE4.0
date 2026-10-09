# Exotel Integration

**Status: everything on our side is built and tested against Exotel's *documented* request/response shapes using mock transports and fake "real" providers. It has never run against a live Exotel account.** What is left is configuration + one verification pass (runbook below).

## Verified from Exotel docs (developer.exotel.com / support.exotel.com, fetched 2026-10-09)
- **Place a call into a flow:** `POST https://api.exotel.com/v1/Accounts/{sid}/Calls/connect`, form-encoded, HTTP Basic `api_key:api_token`. Params: `From` (the person we call), `CallerId` (ExoPhone), `Url` = `http://my.exotel.com/{sid}/exoml/start_voice/{app_id}`, optional `CallType=trans`, `TimeLimit`, `TimeOut`, `StatusCallback`, `StatusCallbackEvents` (`terminal`, `answered`), `CustomField` (≤128 chars, passed to the applets). Response: `Call{Sid, Status, ...}`; statuses `queued, in-progress, completed, failed, busy, no-answer`. Rate limit 200/min.
- **StatusCallback payload (example):** `CallSid, Status, From, To, Direction, Duration, RecordingUrl, StartTime, EndTime`; JSON if `StatusCallbackContentType=application/json`.
- **Passthru applet:** sends a request (GET or POST, configurable) with `CallSid, CallFrom, CallTo, Direction, CurrentTime`, plus `digits` when a Gather/IVR applet ran before it (**value arrives wrapped in double quotes**) and `CustomField` for API-initiated calls.
- **Call Details:** `GET https://api.exotel.com/v1/Accounts/{sid}/Calls/{CallSid}.json`.

## How Cadence uses it
| Step | Implementation |
|---|---|
| Place call | `ExotelProvider.initiate_call` — flow call; `CustomField` = our attempt id; clarify-once calls use `EXOTEL_CLARIFY_FLOW_URL` |
| Keypad answer | Flow = Gather → **Passthru** → `GET /api/webhooks/exotel/response?token=…`. We strip the quotes from `digits`, record "answered", then the response; keys 1/2/3/4/9 as in the prompt |
| Call end | StatusCallback (terminal+answered) → `POST /api/webhooks/exotel?token=…`; `completed` without a prior `answered` is accepted |
| Find the attempt | by `CallSid`, falling back to `CustomField` |
| Duplicates | ledger key `CallSid:status` / `CallSid:digits:N`; one classified response per attempt |
| Reconcile | `ExotelProvider.get_call_status(sid)` (Call Details) |

## Runbook — when the credentials arrive
1. Put values in `.env` (never commit): `EXOTEL_ACCOUNT_SID, EXOTEL_API_KEY, EXOTEL_API_TOKEN, EXOTEL_CALLER_ID` (ExoPhone), `EXOTEL_WEBHOOK_TOKEN` (long random string), `EXOTEL_ALLOWED_NUMBERS` (**your own approved test numbers only**), `CALL_PROVIDER=exotel`.
2. Expose the backend: e.g. `ngrok http 8000` / cloudflared → set `PUBLIC_BASE_URL=https://<public host>`. Restart the backend.
3. In the Exotel dashboard build the flow (App Bazaar): *Greeting/Gather (keypad, 1 digit) → Passthru* with URL `https://<host>/api/webhooks/exotel/response?token=<EXOTEL_WEBHOOK_TOKEN>`, method GET. Copy its URL (`http://my.exotel.com/<sid>/exoml/start_voice/<app_id>`) to `EXOTEL_FLOW_URL`. Optional second flow with "1 = yes, 2 = no" → `EXOTEL_CLARIFY_FLOW_URL`. Prompt audio/TTS and language support are configured **in Exotel**; we have not verified Malayalam voice support.
4. `.venv\Scripts\python.exe scripts\exotel_check.py` → all required boxes ticked (the Settings page shows the same checklist and the URLs).
5. One real smoke call to your own phone: `scripts\exotel_check.py --call +91XXXXXXXXXX --yes` (refuses unless the number is allow-listed). Confirm Status polling reaches `completed`.
6. Create a **new** campaign (campaigns created under `CALL_PROVIDER=demo` stay simulated forever), add yourself as a participant with consent, launch, press 1/2/3/4/9 and watch the campaign page: attempt shows **Real**, outcome follows the key.
7. **Verify the unverified bits and fix if they differ:** (a) the actual StatusCallback body for your account (fields/casing/content type); (b) whether Passthru sends `CallSid` equal to the `Sid` returned at call placement (we fall back to `CustomField` if not); (c) that Passthru fires before the terminal StatusCallback; (d) `digits` formatting. Handlers: `member2/backend/app/api/routes.py` (`webhook_exotel*`).

## Still unverified / not implemented
- Everything above on a live account; webhook signing (none documented → shared-secret token only); speech/voicebot capture and STT; voicemail (`AnsweredBy`) semantics; Malayalam TTS; call cancel; DLT/TRAI compliance for outbound calling in India (organiser's responsibility to confirm before any non-test call).
