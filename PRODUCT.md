# Product

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

## Users
Event organizers running an event (the codebase has demo events and per-event approved info). They set up outreach campaigns to participants, watch outcomes as calls complete, and work through the cases the automation could not close.

## Product Purpose
Cadence ("Define Cadence") automates outbound voice outreach for events: attendance confirmation, announcements, schedule or venue updates, submission-deadline reminders, and participant follow-up. Success is that an organizer reaches every participant, learns each one's outcome (confirmed, declined, callback requested, info requested, unclear, opted out, not reached), and spends human time only on the cases that need it.

## Positioning
Voice calls in English and Malayalam that speak only organizer-approved event information, respect consent and opt-out, classify what the participant said, and hand unresolved cases to a prioritized human follow-up queue with a recommended action.

## Operating Context
- Entities: events, campaigns (purpose, per-language messages, schedule, max attempts, consent requirement), participants/recipients (phone, preferred language, segment, consent status), call attempts, detected intents, follow-ups, a follow-up queue, analytics, a quality page, a public join page, and settings including Exotel telephony.
- Calls can be simulated (demo events and simulated queue items exist); a browser call and a live call view exist.
- Malayalam message rendering is an open verification item.

## Capabilities and Constraints
- Two clients on one backend API (default `127.0.0.1:8000`): `frontend/` (React, TypeScript, Vite, Tailwind 4; all HTTP via typed `src/services/api.ts`) and `app/` (Expo SDK 57, React Native, react-native-web, expo-router, lucide icons, Inter).
- Phone numbers are shown masked in the UI.
- Outcome and call-status vocabulary is fixed in `labels.ts` (e.g. "Needs human", "Not reached", "Attending (confirmed)"); reuse it.
- Undecided: pricing, deployment target, and any marketing or landing surface.

## Brand Commitments
Product name "Cadence" (project title "Define Cadence"). No logo, voice guide, or visual commitments were stated.

## Evidence on Hand
Demo events, fixtures in `app/tests/fixtures/` (campaigns, participants, attempts, analytics, follow-ups, Exotel). No customer testimonials, case studies, or benchmarks exist; do not fabricate them.

## Product Principles
1. The organizer's attention is the scarce resource: surface what needs a human first, with the reason and recommended action.
2. Trust over cleverness: the system says only approved information and honors consent and opt-out visibly.
3. Outcomes in plain language, shown consistently across web and native.
4. Bilingual by default: English and Malayalam are first-class in content and layout.
5. Simulated and real activity are always distinguishable.

## Accessibility & Inclusion
Malayalam script must render correctly and not be truncated or clipped. No other standard was specified.
