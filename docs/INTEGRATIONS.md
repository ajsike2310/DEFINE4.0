# Integrations & Boundaries

## Telephony — Exotel
See `docs/EXOTEL_INTEGRATION.md`. Adapter exists and is mock-tested; **never run live**; response collection (DTMF/speech) from an Exotel flow back to Cadence is unverified.

## Event platforms (e.g. Devfolio)
**No integration exists.** We have not verified any Devfolio API, its terms, authentication, or whether it exposes participant contact data; public listings do not grant access to registrants' phone numbers, and scraping private data is out of scope. The proposed complementary workflow is: organiser exports an **authorised** participant list from their platform → imports the CSV into Cadence.

### CSV contract (`POST /api/campaigns/{id}/recipients/import`)
Required: `name`, `phone` (E.164). Optional: `participant_id`, `language` (`en`|`ml`), `segment`, `opted_out` (`yes|true|1|y` → imported as opted out, never called).
Validation: UTF-8, ≤1 MB, row-level errors returned with line numbers (first 50), duplicate phones within the campaign rejected, malformed rows never silently imported, contact lists are not logged. `consent_confirmed=true` must be sent for rows to be callable; otherwise consent is `unknown` and they are skipped at launch.

### Future API integration seam
Any verified source only needs to produce `RecipientIn` objects (`name, phone, external_ref, preferred_language, segment, consent_status`) and call the same add/import service; campaign execution is unaffected.
