"""Browser demo "call": a person plays the participant in the web app. It is NOT a phone call.

The attempt is flagged simulated (provider "browser_demo"), so it is excluded from real-call metrics. The only
event it emits is `answered`; the participant's reply (keypad press, typed text or transcribed speech) arrives
later through the API and goes through the same intent pipeline as any provider response.
"""
from ..base import InitiateResult, ProviderEvent


class BrowserDemoProvider:
    name = "browser_demo"
    is_simulated = True
    supports_clarify = True

    def initiate_call(self, *, attempt_id, attempt_number, to, language, message, mode="main") -> InitiateResult:
        call_id = f"browser-{attempt_id}"
        return InitiateResult(call_id, [ProviderEvent(f"{call_id}:answered", call_id, "status", "answered")])

    def cancel_call(self, provider_call_id: str) -> None:
        return None
