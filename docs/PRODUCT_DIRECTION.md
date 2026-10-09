# Product Direction — Cadence

**Cadence — Intelligent Voice Outreach for Events.** *Every call. A clear next step.*

A complementary layer for hackathon/technical-event organisers: contact participants by voice, understand what they said, and turn each conversation into a trackable outcome and a next action. It is **not** an event platform and does not replace Devfolio or any registration/submission/judging system.

## Boundary
**Owns:** outbound participant communication, campaigns, multilingual (EN/ML, rule-based) interactions, response classification, confirmation/callback tracking, opt-out handling, bounded retries, a follow-up queue, outcome analytics.
**Does not own:** discovery, registration marketplace, submissions, judging, prizes, payments, ticketing, check-in.

## Sample scenario
DEFINE 4.0 at MBCET, Thiruvananthapuram is used **only as a labelled demonstration scenario**. Participants are fictional (`+1 555-01xx`), calls are simulated, and the only configured "approved" fact is the venue string supplied by the team. No claim is made that the organisers requested, adopted, partnered on, or shared data for Cadence. No schedule, reporting time, deadline or contact has been invented.

## Core workflow
Event → Campaign (purpose, message, languages) → Participants (CSV / reuse / manual, consent-gated) → Calls (demo provider, or Exotel once verified) → Intent → Outcome → Follow-up queue → Dashboard/Analytics.

## Differentiator (implemented as rules, not as AI claims)
- Technical call status ≠ participant intent ≠ next action.
- "Yes" confirms attendance **only** in attendance campaigns; otherwise it is an *acknowledgement*.
- Unclear/hedged/conflicting replies are never confirmations; they create a human-review follow-up.
- Callback times: only explicit relative offsets are scheduled; "after 5 PM" is recorded as a note with the date marked unconfirmed.
- Information requests are answered only from organiser-approved event info; otherwise routed to a person.
- Opt-out always wins, cancels open follow-ups, blocks calls/retries; imported opted-out rows are never called.
- Retries: only technical failures, bounded, never after a resolution.
- Simulated vs real is a stored property of every attempt and campaign and is filterable in analytics.

## Signature features (what makes Cadence more than an auto-dialler)
1. **Clarify-once loop.** An unclear attendance answer is not left as a dashboard red flag: with one click the organiser places a single short yes/no keypad call. A clear 1/2 settles it and closes the review task automatically; silence, a wrong key or "not sure" stays *unclear* and goes to a person. Exactly once per participant, never for opted-out or non-consenting people, never counted as a retry.
2. **Headcount range & certainty.** Instead of a vanity "confirmed" count, the dashboard shows an honest bound — *floor* (said yes) to *ceiling* (not said no) — plus a certainty meter and exactly which unresolved groups would narrow it. Clarification visibly tightens the range. It is a bound on stated intent, never a prediction or check-in.
3. **Approved-facts-only answers.** Questions are answered only from facts the organiser approved; anything else goes to a human.

## Platform integration stance
CSV import first. No Devfolio API/scraping (no verified API or authorised access). See `docs/INTEGRATIONS.md`.
