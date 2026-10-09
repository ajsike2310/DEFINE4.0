# Security & Privacy (hackathon baseline — not production-secure, not a compliance claim)

**Implemented:** secrets only via env/`.env` (git-ignored; `.env.example` placeholders); input validation (E.164, CSV size/encoding, enums, tz-aware times); phone numbers masked in UI and logs; evidence stored as matched phrases only (no transcripts/recordings); consent gating and opt-out honoured through start, retries and follow-ups; opt-out beats every other signal; Exotel webhook rejected without shared token (constant-time compare); optional `EXOTEL_ALLOWED_NUMBERS` allowlist for real calls; duplicate-event ledger; demo data cannot reach a real provider.

**Data location:** local SQLite file (`data/app.db`) on the host running the backend; `DATA_LOCATION_NOTE` documents this. No data leaves the machine except Exotel API calls when that provider is enabled.

**Not implemented / remaining work:** authentication and roles on the API (anyone who can reach port 8000 can read all data — run locally only); full phone numbers are returned by the API (masking is UI-side); encryption at rest; retention/deletion policy beyond demo reset; DNC-registry checks and legal review of calling hours/consent (e.g. TRAI/DLT in India); webhook signing (not offered by Exotel docs); audit log.
