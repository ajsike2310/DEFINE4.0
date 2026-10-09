# Hackathon Checklist
`[x]` done & verified · `[~]` partial/unverified · `[ ]` not started · `[!]` blocked

## Environment / architecture
- [x] Environment audit · [x] venv · [x] Product direction + gap analysis (docs/PRODUCT_*.md)
- [x] Data model, API contracts, integrations boundary documented · [x] Provider interface · [x] State transitions

## Application (event workflow)
- [x] Backend starts, DB initialises, data survives restart (verified on earlier build; event build run live on port 8001 with temp DB — restart not repeated)
- [x] Event CRUD + approved info (API tests) · [x] Campaign tied to event (API tests)
- [x] Participant add / CSV import (participant_id, opted_out) / reuse from campaign / filters / history (API tests)
- [x] Call attempts, intents, outcomes, follow-ups persisted · [x] Follow-up queue with rule-based priority
- [x] Analytics from stored rows, event filter, simulated/real split
- [~] Frontend: build + typecheck pass; render tests with mocked API (dashboard, queue, wizard guards) pass; **not exercised in a real browser**; Events, Participants, Campaign detail pages have no render test
- [ ] Scheduled launch (not supported; documented)

## Calling
- [x] Demo provider · [x] Events update correct records · [x] Duplicate events safe
- [x] Terminal-only provider callback handled (tested with fake real provider)
- [x] Real vs simulated labelled (attempt, campaign, UI badges, analytics filter)
- [~] Exotel: status + keypad (Gather→Passthru) + clarify-flow paths implemented from documented shapes and tested with fake real providers/mock HTTP; readiness page + `scripts/exotel_check.py` ready
- [!] Real Exotel verified live: not possible, the organisers reported an Exotel API key problem and will tell the judges (runbook in docs/EXOTEL_INTEGRATION.md)
- [x] Browser demo call with ElevenLabs voice + speech-to-text (mocked tests; replies use the same rules; recorded as simulated) · [x] run live with a real key (English works; Malayalam transcription weak)
- [x] Hands-free live call: speaks, listens, answers, clarify-once by voice (14 backend tests; driven in headless Chrome with a fake mic) · [ ] not tried with a human voice or in other browsers
- [x] Clarify-once loop (API tests incl. once-only, no-answer, opt-out, non-attendance) · [x] Headcount range (tests)

## Intelligence
- [x] Intents incl. acknowledgement · [x] EN/ML/mixed/Manglish phrase tests (≈30 synthetic cases; not an accuracy claim)
- [x] Ambiguity safe · [x] Callback (explicit offsets scheduled; "after 5 PM" = note only) · [x] Opt-out · [x] Retry
- [x] Info requests answered only from approved info · [!] No speech-to-text for phone calls (browser demo call transcribes with ElevenLabs once a key is set)

## Quality
- [x] Python tests: 116 passed (last run) · [x] Frontend build + 33 tests (incl. every page rendered against REAL API responses recorded by `member4/scripts/record_fixtures.py`)
- [x] Custom notifications: toasts, notification centre (bell), confirm dialog, live follow-up alerts (12 tests + driven in headless Chrome at desktop and 390 px)
- [x] Three labelled sample events + one-click simulation (`POST /api/demo/seed-all?run=`)
- [~] E2E: scripted live run vs real server (`member4/scripts/demo_e2e.py`); no browser E2E
- [x] Leads, campaign management, Data and AI quality page (API + render tested; checked in headless Chrome at 1440 and 390 px)
- [x] Known issues documented · [~] `scripts\setup.ps1` not re-run from scratch · [ ] Demo rehearsed in a browser
