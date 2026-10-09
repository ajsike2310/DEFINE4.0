"""What the backend receives when a live call ends: participant, campaign, attendance decision, call outcome."""
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import httpx

from ..intelligence.intent.taxonomy import Intent
from ..intelligence.pipeline import IntentDecision
from .campaign import CallContext

log = logging.getLogger("member3.live")

ATTENDANCE = {
    Intent.CONFIRM: "confirmed", Intent.DECLINE: "declined", Intent.CALLBACK: "callback_requested",
    Intent.INFO: "information_requested", Intent.ACK: "acknowledged", Intent.OPT_OUT: "opted_out",
    Intent.UNCLEAR: "unclear", Intent.HUMAN: "needs_review",
}


@dataclass
class CallResult:
    event_id: str                      # stable per call: the backend can de-duplicate on it
    provider_call_id: str
    attempt_id: int | str
    participant_id: str
    campaign_id: str
    attendance: str                    # confirmed | declined | callback_requested | ... | no_response
    call_outcome: str                  # completed | hung_up
    intent: str | None = None
    next_action: str | None = None
    language: str | None = None
    method: str | None = None          # dtmf | rules | none
    needs_review: bool = False
    requested_time: str | None = None  # ISO, only for explicit relative times ("in 2 hours")
    time_hint: str | None = None       # e.g. "after 5 PM"; informational
    info_topic: str | None = None
    ended_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def build_result(ctx: CallContext, decision: IntentDecision | None, *, call_outcome: str) -> CallResult:
    base = dict(event_id=f"{ctx.provider_call_id}:result", provider_call_id=ctx.provider_call_id,
                attempt_id=ctx.attempt_id, participant_id=ctx.participant_id, campaign_id=ctx.campaign_id,
                call_outcome=call_outcome, ended_at=datetime.now(timezone.utc).isoformat())
    if decision is None:               # caller hung up (or the stream failed) before giving an answer
        return CallResult(attendance="no_response", needs_review=True, **base)
    return CallResult(
        attendance=ATTENDANCE[decision.intent], intent=decision.intent.value, next_action=decision.next_action.value,
        language=decision.language, method=decision.method,
        needs_review=decision.needs_review or decision.intent in (Intent.UNCLEAR, Intent.HUMAN),
        requested_time=decision.requested_time.isoformat() if decision.requested_time else None,
        time_hint=decision.time_hint, info_topic=decision.info_topic, **base)


ResultSink = Callable[[CallResult], None]


class LogSink:
    """Development sink: prints the decision only (never transcripts)."""

    def __call__(self, r: CallResult) -> None:
        print(f"[result] call={r.provider_call_id} participant={r.participant_id} campaign={r.campaign_id} "
              f"attendance={r.attendance} outcome={r.call_outcome} review={r.needs_review}", flush=True)


class HttpResultSink:
    """POSTs the result JSON to the backend with retries. Anything that still fails is appended to a local
    dead-letter file so a result is never silently lost."""

    def __init__(self, url: str, token: str = "", *, client: httpx.Client | None = None, retries: int = 3,
                 backoff_s: float = 0.5, dead_letter_path: str | None = "logs/unsent_results.jsonl",
                 sleep: Callable[[float], None] = time.sleep):
        self.url, self.token, self.retries, self.backoff_s = url, token, retries, backoff_s
        self.dead_letter_path, self._sleep = dead_letter_path, sleep
        self._http = client or httpx.Client(timeout=10)

    def __call__(self, r: CallResult) -> None:
        headers = {"Idempotency-Key": r.event_id}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for attempt in range(self.retries):
            try:
                resp = self._http.post(self.url, json=r.to_dict(), headers=headers)
                if resp.status_code < 400:
                    return
                if resp.status_code < 500 and resp.status_code != 429:
                    break                                       # our request is wrong; retrying will not help
                log.warning("result post: HTTP %s (attempt %d)", resp.status_code, attempt + 1)
            except httpx.HTTPError as exc:
                log.warning("result post failed: %s (attempt %d)", type(exc).__name__, attempt + 1)
            if attempt + 1 < self.retries:
                self._sleep(self.backoff_s * 2 ** attempt)
        self._dead_letter(r)

    def _dead_letter(self, r: CallResult) -> None:
        log.error("result for call %s could not be delivered; saved to dead-letter file", r.provider_call_id)
        if self.dead_letter_path:
            os.makedirs(os.path.dirname(self.dead_letter_path) or ".", exist_ok=True)
            with open(self.dead_letter_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(r.to_dict()) + "\n")
