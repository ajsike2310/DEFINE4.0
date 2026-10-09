"""Provider callback schemas."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .common import ORM


class WebhookEventIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    provider_call_id: str
    kind: str
    status: str | None = None
    text: str | None = None
    dtmf: str | None = None

    @field_validator("kind")
    @classmethod
    def _k(cls, v):
        if v not in ("status", "response"):
            raise ValueError("kind must be status|response")
        return v

    @field_validator("status")
    @classmethod
    def _st(cls, v):
        if v is not None and v not in ("ringing", "answered", "completed", "failed", "busy", "no_answer", "voicemail"):
            raise ValueError("invalid status")
        return v


class WebhookLogOut(ORM):
    id: int
    provider: str
    endpoint: str
    method: str
    received_at: datetime
    request_id: str | None
    call_attempt_id: int | None
    ok: bool
    result: str
    payload: dict
