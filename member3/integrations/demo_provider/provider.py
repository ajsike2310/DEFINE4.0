"""Deterministic SIMULATED provider. No real call is ever placed.

The scenario is chosen from the last digit of the phone number so demos repeat
exactly. Every event is flagged simulated at the attempt level (is_simulated).
"""
from ..base import InitiateResult, ProviderEvent

# digit -> list of per-attempt scripts: (final status, optional response text, optional dtmf)
SCENARIOS: dict[str, list[tuple[str, str | None, str | None]]] = {
    "0": [("completed", "Yes, I'll be there.", None)],
    "1": [("completed", "No, I can't come", None)],
    "2": [("completed", "അതെ, വരാം", None)],
    "3": [("completed", "I'm busy. Call me after 5 PM.", None)],
    "4": [("completed", "Maybe. I'll see.", None)],
    "5": [("completed", "Please stop calling me", None)],
    "6": [("no_answer", None, None), ("completed", None, "1")],   # fails, then succeeds on retry
    "7": [("voicemail", None, None)],
    "8": [("busy", None, None)],
    "9": [("completed", "Where is the venue?", None)],
}


# Per-number overrides of the main scenario (last two digits), for variety beyond the 10 base scenarios.
OVERRIDES_BY_LAST2: dict[str, tuple[str, str | None, str | None]] = {
    "19": ("completed", "What time does it start?", None),     # schedule question
}

# Clarification call (one keypad yes/no question), keyed by the LAST TWO digits of the number.
# Anything not listed answers with silence -> classified unclear -> stays with a human.
CLARIFY_SCENARIOS: dict[str, tuple[str, str | None, str | None]] = {
    "04": ("completed", None, "1"),                  # presses 1 -> attending
    "14": ("completed", "hmm not sure", None),       # still unclear after the question
    "24": ("no_answer", None, None),                 # does not pick up
}


class DemoProvider:
    name = "demo"
    is_simulated = True

    def initiate_call(self, *, attempt_id, attempt_number, to, language, message, mode="main") -> InitiateResult:
        digit = to.strip()[-1:]
        if mode == "clarify":
            status, text, dtmf = CLARIFY_SCENARIOS.get(to.strip()[-2:], ("completed", None, None))
        elif to.strip()[-2:] in OVERRIDES_BY_LAST2:
            status, text, dtmf = OVERRIDES_BY_LAST2[to.strip()[-2:]]
        else:
            script = SCENARIOS.get(digit, SCENARIOS["4"])
            status, text, dtmf = script[min(attempt_number, len(script)) - 1]
        call_id = f"demo-{attempt_id}"
        events: list[ProviderEvent] = []
        if status in ("completed",):
            events.append(ProviderEvent(f"{call_id}:answered", call_id, "status", "answered"))
            events.append(ProviderEvent(f"{call_id}:response", call_id, "response", text=text, dtmf=dtmf))
            events.append(ProviderEvent(f"{call_id}:completed", call_id, "status", "completed"))
        else:
            events.append(ProviderEvent(f"{call_id}:{status}", call_id, "status", status))
        return InitiateResult(call_id, events)

    def cancel_call(self, provider_call_id: str) -> None:
        return None
