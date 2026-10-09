"""Exotel adapter. Implements ONLY what was verified in Exotel's public docs
(see docs/EXOTEL_INTEGRATION.md): "Connect Number to Call Flow" via
POST {base}/v1/Accounts/{sid}/Calls/connect with HTTP Basic auth (api key:token).

NOT verified / not implemented: StatusCallback payload schema, webhook
signatures, and how DTMF/speech from the flow reaches us. Real operation has
never been run against a live account from this codebase.
"""
import re

import httpx

from ..base import InitiateResult, ProviderError

STATUS_MAP = {  # Exotel "Status" values listed in the Call response docs
    "queued": "initiating", "in-progress": "answered", "completed": "completed",
    "failed": "failed", "busy": "busy", "no-answer": "no_answer",
}


class ExotelProvider:
    name = "exotel"
    is_simulated = False

    def __init__(self, *, account_sid, api_key, api_token, caller_id, flow_url,
                 base_url="https://api.exotel.com", status_callback=None, client=None, allowed_numbers=(),
                 clarify_flow_url="", stream_url=""):
        self.stream_url = stream_url
        self.clarify_flow_url = clarify_flow_url
        self.supports_clarify = bool(clarify_flow_url)
        # Safety: when set, ONLY these numbers can be dialled (approved test numbers).
        self.allowed_numbers = set(allowed_numbers)
        missing = [k for k, v in dict(account_sid=account_sid, api_key=api_key, api_token=api_token,
                                      caller_id=caller_id,
                                      flow_url=flow_url or stream_url).items() if not v]
        if missing:
            raise ProviderError("Exotel not configured; missing: " + ", ".join(missing))
        self.sid, self.key, self.token = account_sid, api_key, api_token
        self.caller_id, self.flow_url, self.base_url = caller_id, flow_url, base_url.rstrip("/")
        self.status_callback = status_callback
        self.client = client or httpx.Client(timeout=15)

    def get_call_status(self, call_sid: str) -> dict:
        """Call Details API (documented: GET /v1/Accounts/{sid}/Calls/{CallSid}.json). Used by the
        setup check script and for reconciling a call whose callback never arrived."""
        resp = self.client.get(f"{self.base_url}/v1/Accounts/{self.sid}/Calls/{call_sid}.json",
                               auth=(self.key, self.token))
        if resp.status_code >= 400:
            raise ProviderError(f"Exotel returned HTTP {resp.status_code}")
        return resp.json().get("Call") or {}

    def initiate_call(self, *, attempt_id, attempt_number, to, language, message, mode="main") -> InitiateResult:
        if self.allowed_numbers and to not in self.allowed_numbers:
            raise ProviderError("number not in EXOTEL_ALLOWED_NUMBERS; refusing to dial")
        flow = self.flow_url
        if mode == "clarify":
            if not self.clarify_flow_url:
                raise ProviderError("EXOTEL_CLARIFY_FLOW_URL not configured; clarification calls unavailable")
            flow = self.clarify_flow_url
        if self.stream_url and mode == "main":
            # "Connect Voice AI" (Exotel blog "one API call your AI bot is on the phone"): dials and opens a
            # bidirectional audio stream to our WebSocket with no dashboard flow. Needs account enablement.
            data = {"From": to, "CallerId": self.caller_id, "StreamUrl": self.stream_url,
                    "StreamType": "bidirectional", "CustomField": str(attempt_id)}
        else:
            data = {"From": to, "CallerId": self.caller_id, "Url": flow,
                    "CallType": "trans", "CustomField": str(attempt_id)}
        if self.status_callback:
            data["StatusCallback"] = self.status_callback
            data["StatusCallbackEvents[0]"] = "terminal"
            data["StatusCallbackEvents[1]"] = "answered"
        # ".json" selects JSON output; Exotel's v1 API answers in XML without it.
        resp = self.client.post(f"{self.base_url}/v1/Accounts/{self.sid}/Calls/connect.json",
                                data=data, auth=(self.key, self.token))
        if resp.status_code >= 400:
            raise ProviderError(f"Exotel returned HTTP {resp.status_code}")
        try:
            sid = (resp.json().get("Call") or {}).get("Sid")
        except ValueError:
            m = re.search(r"<Sid>([^<]+)</Sid>", resp.text)      # XML fallback
            sid = m.group(1) if m else None
            if not sid:
                raise ProviderError(f"Exotel returned HTTP {resp.status_code} with an unreadable body; the call "
                                    "may still have been placed, check the Exotel call log")
        if not sid:
            raise ProviderError("Exotel response missing Call.Sid")
        return InitiateResult(sid)

    def cancel_call(self, provider_call_id: str) -> None:
        raise ProviderError("cancel not implemented (no verified Exotel cancel endpoint)")
