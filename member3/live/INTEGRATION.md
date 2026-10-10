# Live calls: how the backend plugs in

```python
from member3.live.config import LiveSettings
from member3.live.results import HttpResultSink
from member3.live.service import LiveService
from member3.live.campaign import CallContext, CampaignInfo

live = LiveService(LiveSettings.from_env(), sink=HttpResultSink(url, token))   # sink = any callable(CallResult)
app.include_router(live.router)                      # serves wss://<host>/live/exotel/<EXOTEL_WEBHOOK_TOKEN>

res = provider.initiate_call(...)                    # ExotelProvider with stream_url (EXOTEL_STREAM_URL) set
live.register_call(CallContext(                      # right after dialling: the stream finds the call by its Sid
    provider_call_id=res.provider_call_id, attempt_id=attempt.id, participant_id=p.id, campaign_id=c.id,
    participant_name=p.name,
    campaign=CampaignInfo(name=c.name, venue=c.venue, event_date=c.date, event_time=c.time, organiser=c.org)))
```

Rules: run **one worker** (the registry is in process memory; swap `source=` for a shared store to scale), serve over
TLS (`wss://`), and keep the stream secret out of logs (`logging_utils.install()` redacts it).

## Result the sink receives (one per call)
`event_id` (stable: de-duplicate on it), `provider_call_id`, `attempt_id`, `participant_id`, `campaign_id`,
`attendance` = confirmed | declined | callback_requested | information_requested | acknowledged | opted_out |
unclear | needs_review | no_response, `call_outcome` = completed | hung_up, `intent`, `next_action`, `language`,
`method` (dtmf|rules), `needs_review`, `requested_time` (only explicit "in 2 hours"), `time_hint`, `info_topic`, `ended_at`.
`HttpResultSink` retries 5xx/429 with backoff, sends `Idempotency-Key: <event_id>`, and appends anything it cannot
deliver to `logs/unsent_results.jsonl`. Call status (no answer, busy, failed) still arrives from Exotel's StatusCallback.

## Exotel facts learned on a live account (do not "fix" these)
* The flow-free "Connect Voice AI" call (`StreamUrl` + `StreamType=bidirectional`) works; needs account enablement.
* Exotel drops a `?query` on the stream URL, so the secret is in the **path**.
* Outbound audio messages must be exactly `{event, stream_sid, media:{payload}}`. Adding `sequence_number`, `chunk` or
  `timestamp` (the docs' example) makes Exotel cancel the stream ~100 ms later.
* `custom_parameters` are empty on this API; the call is matched by `call_sid`.
* Audio is raw 16-bit 8 kHz mono PCM; the server paces playback in real time.

## Languages
`CampaignInfo.language` = `en` | `hi` | `ta` picks the greeting. During the call the agent answers in the language the
caller used (detected by script): goodbyes, the clarification question and "where/when" answers all exist in English,
Hindi and Tamil. Malayalam rules and lines exist but Malayalam greetings do not, and ElevenLabs Multilingual v2 cannot
speak Malayalam (try `eleven_v3`). Hindi/Tamil wording is not native-reviewed: see `member3/NATIVE_REVIEW.md`.
Test any sentence through voice -> Scribe -> rules with `python -m scripts.check_languages "<text>" <intent>`.

## Conversational mode (opt-in)
`LiveService(settings, sink, conversational=True)` lets the caller switch language ("speak Hindi") and ask what the organiser's
data can answer (`CampaignInfo.info_answers`: venue, schedule, organiser, about from `CampaignInfo.description`) without ending
the call; the agent answers, asks the RSVP question again, and keeps listening (max 3 questions). Default is `False`, which keeps
the one-answer behaviour above. Helpers live in `live/dialogue.py`.
