# Cadence dashboard

Create an event, add people, press one button: each person gets an automated call with their own message.

    python -m scripts.run_dashboard        # http://127.0.0.1:8002  (real calls when CALL_PROVIDER=exotel)

`CALL_PROVIDER=exotel` plus the `EXOTEL_*` / `ELEVENLABS_*` values in `.env` switches to real calls through the live voice
agent in `member3/live` (the dashboard embeds `LiveService`, so a call's result lands in the database directly). Run **one
worker**, serve over HTTPS, and set `DASHBOARD_TOKEN` before exposing it. Real dialling is limited to `EXOTEL_ALLOWED_NUMBERS`
while that is set, and to `CALL_WINDOW` hours.

## Two interfaces, one backend
* **Original dashboard**: `http://127.0.0.1:8002/` (plain HTML/JS, API under `/api`). Unchanged.
* **React app** (`frontend/`): `http://127.0.0.1:8002/app/`. It talks to a compatible API under `/api/v2` (`dashboard/v2.py`)
  that sits on the same database and call engine, so both show the same events, campaigns, people and results.
  Build it once, then it is served by the same server:

      cd frontend && npm install && npm run build

  For frontend development: `npm run dev` (http://localhost:5173/app/, proxies `/api` to the dashboard on 8002).
  `VITE_API_BASE` changes the API prefix (default `/api/v2`), `VITE_API_TARGET` the proxy target.
* Differences in the React app: Hindi and Tamil are offered next to English (Malayalam is not supported by the call agent),
  per-person personal messages (`{first_name}`, `{event}`, `{venue}`, `{date}`, `{time}`), automatic retry settings on a
  campaign, and a *Calling hours* section in Settings. The in-browser practice call is not part of this build
  (real calls use the live voice agent). "Sample data" campaigns are always simulated and can never ring a real phone.
* Event facts the agent may state (Events page: venue, schedule, ...) are the "approved information": a question about
  anything left blank goes to the follow-up queue instead of being guessed.

## Flow
1. **Events**: webinar, hackathon, seminar, workshop, conference, clinic appointment, school meeting, payment reminder, other.
2. **People** (per event): the event's contact list. Add one by one or import a CSV (`name, phone` required; optional `language`
   en/hi/ta and `segment`; any other column such as `amount` becomes a `{variable}`).
3. **Campaign** (per event, as many as you like: invitation, reminder, update, thank-you). **Each campaign has its own audience**:
   create it with everyone or nobody, then *Add people* from the event list, as a new person, or by CSV. Start calls; pause;
   **Retry non-responders**; call one person again; export CSV.
4. **Overview**: outcomes by campaign, language and audience segment.

## Personal messages (per campaign)
Script variables: `{name} {first_name} {event} {event_type} {date} {time} {venue} {organiser}` plus CSV columns.
A person's **personal message** belongs to their place in one campaign: the same person can hear a different message in an
invitation and in a reminder, and has none (the campaign script) where none is set. Set it when adding people, with a `message`
CSV column, or later with the *Message* button on their row. If the suggested script is left unedited, people set to Hindi/Tamil
hear it in their language; an edited script, or a personal message, is spoken as written. Invitation and reminder messages
without a question get "Will you be attending?" appended so the agent has something to listen for.

## Consent, RSVP and follow-ups
* **OK to call**: every person has a consent switch (CSV column `consent`, yes/no, default yes). People marked no stay on the
  list but are never added to a campaign or dialled, even if they were added before the switch was turned off.
* **RSVP**: each call updates the person's RSVP for the event: *attending*, *not attending* or *undecided*. A clear yes/no always
  replaces the previous answer; an unclear call never erases one. Shown on the event's People tab and in the overview.
* **Follow-up tasks** (Follow-ups page, with a count in the sidebar) are created when a machine cannot settle the outcome:
  an unclear answer, a callback request, a question about venue/time, or no contact after the maximum attempts. A person
  works through them with *Coming / Not coming / Done*, which also records the RSVP. A later clear answer closes the task itself.
* **Calling hours** (Settings): on/off and from/until (IST), saved in the database. They apply to real calls only. `CALL_WINDOW`
  in `.env` is just the first default.

## Automatic retries
When someone does not pick up, is busy, or picks up but says nothing, the dashboard calls them again after the campaign's
retry interval (Campaign > Settings: off, or 5 minutes to 4 hours) until the max attempts is reached. It only runs while the
campaign is started and not paused, inside the calling hours, and never for people who opted out or are not OK to call. People
who gave an unclear answer are *not* re-dialled; they get a follow-up task instead, as do people still unreached after the
last attempt. The scheduler checks every 20 seconds (`SCHEDULER_INTERVAL_S`).

## On the call (real calls)
The dashboard runs the live agent with conversation, keypad and answering-machine handling switched on:
* **Voice or keypad, both offered.** Every question call (invitation, reminder, attendance confirmation) ends with the keypad
  options: *1 confirm, 2 cannot attend, 3 call back, 4 more information, 9 stop calls* (unless you already wrote them in the
  message). If the person is silent the agent says it again, and an unclear answer or an unknown key re-asks once with
  "press 1 for yes and 2 for no". A key press works at any moment, even while the agent is still talking or listening.
  Key 4 reads out what is known (date/time, venue, organiser, what the event is about) and asks again.
* **Answering machines.** After pickup the agent listens for about 1.5 s before speaking. A person says a short "hello"; a recorded
  greeting is long (7 s or more), or contains phrases such as "leave a message after the beep" (English, Hindi, Tamil). The agent
  then hangs up without saying anything personal. The call is recorded as **Voicemail**, never as an answer or an RSVP, and is
  retried after the campaign's retry interval like an unanswered call; after the last attempt a follow-up task is created.
  *Settings > Answering machines* can switch on a short neutral note ("an automated call from <organiser> about <event>, we will try
  again later"), spoken after a pause for the beep. It never contains the guest's name or any answer. Off by default.
* **Language switch**: "speak Hindi", "Tamil please", "हिंदी में बोलिए", "தமிழில் பேசுங்கள்" switches the rest of the call to
  English, Hindi or Tamil, re-asks the question in that language and closes in it.
* **Questions it can answer** (only from the organiser's data, never improvised): venue, date/time, who is organising, and
  what the event is about (the event's *About this event* text). It answers, asks again, and carries on (up to three
  questions per call). Anything else it does not know goes to a person as a follow-up task.
* A plain yes / no / opt-out still ends the call as before. The plain `run_live` dev server is unchanged (none of this is on there).
* Hindi and Tamil lines are not native-reviewed. Machine detection is a timing and phrase heuristic, not Exotel's own
  answering-machine detection (which is not wired up), so an unusual machine greeting may be mistaken for a person and a
  very slow talker for a machine; the default is to treat doubtful cases as a person.

## Behaviour worth knowing
* "Non-responder" = no answer, busy, failed, voicemail, or picked up without a clear answer; capped by max attempts.
* Opt-outs ("stop calling me" / key 9) are stored and the person is never dialled again. **Erase** removes a person and their records.
* Numbers are normalised to E.164 (+91 assumed for 10-digit numbers); duplicates per event are rejected.
* Hindi and Tamil wording is not native-reviewed (`member3/NATIVE_REVIEW.md`).
* Only decisions are stored; audio is processed live and discarded, and transcripts are never saved.
