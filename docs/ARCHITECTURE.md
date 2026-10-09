# Architecture

```
React SPA (member1)  --/api (Vite proxy)-->  FastAPI (member2)
                                               |-- services/campaigns.py   dispatch, start, retry, completion
                                               |-- services/events.py      dedupe -> status/intent -> outcome + follow-ups
                                               |-- services/states.py      all state rules
                                               |-- SQLAlchemy / SQLite
                                               |-- member3.integrations    CallProvider: DemoProvider | ExotelProvider
                                               |-- member3.intelligence    pipeline: input -> normalize -> rules -> decision
                                               '-- member4.analytics       metrics computed from stored rows
```

**Flow:** create campaign -> add recipients (consent flag) -> `POST /start` -> `dispatch()` creates a `CallAttempt` and calls the provider -> provider events (immediate for demo, webhook for Exotel) go through `apply_event()` -> status transition or `process_response()` -> `IntentResult` + recipient outcome + `FollowUp` -> analytics.

**Separation:** call status (technical) vs recipient outcome (meaning) are different columns with separate rules in `states.py`. Routes hold no business logic. Providers never touch the DB.

**Python import root:** the repo root is on `PYTHONPATH` (`pytest.ini`, `scripts/dev.ps1`); packages are `member2.backend.app`, `member3.*`, `member4.*`.

**Safety rules in code:** demo campaigns can only use `DemoProvider`; unclear/hedged/conflicting text is never confirmation; opt-out always wins and cancels open follow-ups; callback time is only set for explicit relative offsets ("in 2 hours"); retries only for failed/busy/no_answer/voicemail, bounded by `max_attempts`, only through `retry-due` (respects backoff).
