"""Provider-agnostic calling interface. Business logic only sees these types."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ProviderEvent:
    event_id: str                      # unique per provider; used for duplicate protection
    provider_call_id: str
    kind: str                          # "status" | "response"
    status: str | None = None          # normalized: ringing|answered|completed|failed|busy|no_answer|voicemail
    text: str | None = None            # recognised speech text, if the provider supplies it
    dtmf: str | None = None
    audio_ref: str | None = None


@dataclass
class InitiateResult:
    provider_call_id: str
    # Events available immediately (demo provider only; real providers deliver via webhook).
    events: list[ProviderEvent] = field(default_factory=list)


class ProviderError(Exception):
    pass


class CallProvider(Protocol):
    name: str
    is_simulated: bool

    def initiate_call(self, *, attempt_id: int, attempt_number: int, to: str,
                      language: str, message: str, mode: str = "main") -> InitiateResult:
        """mode: "main" (normal campaign call) | "clarify" (single yes/no follow-up question)."""
        ...

    def cancel_call(self, provider_call_id: str) -> None: ...
