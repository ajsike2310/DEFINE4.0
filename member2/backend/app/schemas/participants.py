"""Participant, call attempt and response schemas."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from .common import ORM, SUPPORTED_LANGUAGES, normalize_phone


class RecipientIn(BaseModel):
    external_ref: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    phone: str
    preferred_language: str | None = None
    segment: str | None = None
    consent_status: str = "unknown"

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return normalize_phone(v)

    @field_validator("preferred_language")
    @classmethod
    def _lang(cls, v):
        if v in (None, ""):
            return None
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"preferred_language must be one of {sorted(SUPPORTED_LANGUAGES)}")
        return v

    @field_validator("consent_status")
    @classmethod
    def _consent(cls, v):
        if v not in ("granted", "unknown", "revoked"):
            raise ValueError("consent_status must be granted|unknown|revoked")
        return v


class RecipientOut(ORM):
    id: int
    campaign_id: int
    external_ref: str | None = None
    name: str
    phone: str
    preferred_language: str | None
    segment: str | None
    consent_status: str
    opted_out: bool
    outcome: str
    is_demo: bool
    created_at: datetime


class AttemptOut(ORM):
    id: int
    campaign_id: int
    recipient_id: int
    provider: str
    is_simulated: bool
    provider_call_id: str | None
    attempt_number: int
    mode: str = "main"
    call_language: str
    status: str
    started_at: datetime | None
    answered_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None
    next_retry_at: datetime | None


class IntentOut(ORM):
    id: int
    call_attempt_id: int
    recipient_id: int
    campaign_id: int
    intent: str
    score: float
    method: str
    detected_language: str
    evidence: str
    notes: list
    needs_review: bool
    next_action: str
    processing_status: str
    created_at: datetime
