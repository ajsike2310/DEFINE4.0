# Cadence — Intelligent Voice Outreach for Events
*Every call. A clear next step.*

Cadence helps hackathon/technical-event organisers call participants, understand each reply (attending / declined / callback / question / opt-out / unclear), and manage the next step from one dashboard. It complements event platforms (registration, submissions, judging) — it does not replace them. See `docs/PRODUCT_DIRECTION.md`.

> **Honest status:** the event workflow is verified with a **simulated** provider and fictional sample participants. DEFINE 4.0 @ MBCET is a *demonstration scenario only* — no organiser adoption or data access is claimed. Real Exotel calling, speech-to-text, real-browser UI checks and real-world language accuracy are **not** verified. See `docs/KNOWN_ISSUES.md`.

## Feature status
| Feature | Status |
|---|---|
| Events with organiser-approved info; campaigns belong to an event; 5 campaign purposes | Working (API tested) |
| Participants: add, CSV import (`participant_id`, `opted_out`), reuse across campaigns, consent gating, filters, history | Working (API tested) |
| Demo provider; duplicate-event protection; bounded retries; opt-out suppression | Working (tested) |
| Intents (EN / Malayalam / mixed, keypad) incl. acknowledgement; safe ambiguity handling | Working, rule-based, small synthetic test set |
| Follow-up queue with rule-based priorities | Working (API tested) |
| **Clarify-once loop** (one yes/no keypad call for unclear answers) | Working (API tested, simulated) |
| **Headcount range + certainty meter** (floor–ceiling of stated attendance) | Working (API + render tested) |
| Notifications: toasts, notification centre, custom confirm dialogs, live alerts for new follow-ups | Working (tested; polling-based, per browser) |
| **Lead generation**: public sign-up link (explicit consent box), CSV import, manual add, transparent readiness score, convert to campaign participants | Working (API + render tested) |
| **Campaign management**: progress, rule-based next step, duplicate | Working (API + render tested) |
| **Data and AI quality** page: integrity checks, import acceptance, consent/language coverage, response-engine behaviour, live phrase check | Working; behaviour figures, not accuracy |
| **Live call (browser demo)**: hands-free voice conversation. The agent speaks (ElevenLabs), listens, transcribes, answers with fixed lines, asks the one clarification question when unsure, and ends the call. A manual keys/text variant also exists. Replies use the same rules; always recorded as simulated, never a phone call | Working in English (driven in headless Chrome with a fake microphone against the live ElevenLabs service); Malayalam speech transcription is weak |
| Exotel: status + keypad webhooks, readiness page, `scripts/exotel_check.py` | Implemented to documented shapes; **awaiting credentials** (runbook: `docs/EXOTEL_INTEGRATION.md`) |
| Event-scoped analytics, documented denominators, real vs simulated split | Working |
| React UI (event selector, dashboard, wizard, campaign detail, participants, queue, events, analytics, settings) | Builds; render-tested with mocked API; **not browser-verified** |
| Scheduled launch, speech-to-text on real phone calls, on-call clarification, auth, Devfolio/other platform API | Not implemented |

## Setup & run (Windows PowerShell, repo root)
```powershell
scripts\setup.ps1      # venv, deps, .env
scripts\dev.ps1        # backend :8000 (docs at /docs), frontend :5173 -> http://localhost:5173
```
Manual: `$env:PYTHONPATH=(pwd).Path; .venv\Scripts\python.exe -m uvicorn member2.backend.app.main:app --port 8000` and `cd member1\frontend; npm run dev` (`$env:VITE_API_TARGET` overrides the proxy target).
**After any `git pull`/code update, restart BOTH servers** — a backend left running on old code makes the dashboard show 404 errors (`/api/events` missing).
**Upgrading from the pre-event build:** stop the servers and delete `data\` (no migrations; the backend refuses an old database with a clear message).

## Demo
Default `CALL_PROVIDER=demo`. Follow `docs/DEMO_SCRIPT.md`, or run `.venv\Scripts\python.exe member4\scripts\demo_e2e.py`.

## Tests
```powershell
.venv\Scripts\python.exe -m pytest                      # backend + intelligence + integration
cd member1\frontend; npm run build; npm test            # typecheck/build + unit/render tests
```

## Docs
`docs/PRODUCT_DIRECTION.md`, `PRODUCT_GAP_ANALYSIS.md`, `ARCHITECTURE.md`, `API_CONTRACTS.md`, `DATA_MODEL.md`, `INTEGRATIONS.md`, `EXOTEL_INTEGRATION.md`, `SECURITY_AND_PRIVACY.md`, `KNOWN_ISSUES.md`, `HACKATHON_CHECKLIST.md`, `DEMO_SCRIPT.md`.

## Team ownership
Member 1 `member1/` event-focused frontend · Member 2 `member2/` backend & data · Member 3 `member3/` Exotel, demo provider, intents · Member 4 `member4/` analytics, integration tests, demo readiness.
