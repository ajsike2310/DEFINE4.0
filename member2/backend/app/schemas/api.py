import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SUPPORTED_LANGUAGES = {"en": "English", "ml": "Malayalam"}
PURPOSES = {"attendance_confirmation", "event_announcement", "schedule_venue_update",
            "submission_deadline_reminder", "participant_followup"}
E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(raw: str) -> str:
    cleaned = re.sub(r"[\s\-().]", "", raw or "")
    if not E164.match(cleaned):
        raise ValueError("phone must be E.164, e.g. +919876543210")
    return cleaned


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


INFO_KEYS = ("venue", "schedule", "reporting_time", "submission_deadline")


def _clean_info(v: dict[str, str]) -> dict[str, str]:
    bad = [k for k in v if k not in INFO_KEYS]
    if bad:
        raise ValueError(f"approved_info keys must be among {', '.join(INFO_KEYS)}")
    return {k: s.strip() for k, s in v.items() if s.strip()}


class EventIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=500)
    approved_info: dict[str, str] = Field(default_factory=dict)   # e.g. venue, schedule
    organizer_contact: str | None = Field(default=None, max_length=200)

    @field_validator("approved_info")
    @classmethod
    def _info(cls, v):
        return _clean_info(v)


class EventPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    approved_info: dict[str, str] | None = None
    organizer_contact: str | None = Field(default=None, max_length=200)

    @field_validator("approved_info")
    @classmethod
    def _info(cls, v):
        return _clean_info(v) if v is not None else v


class EventOut(ORM):
    id: int
    name: str
    description: str
    approved_info: dict
    organizer_contact: str | None
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    campaign_count: int = 0


class CampaignIn(BaseModel):
    event_id: int
    name: str = Field(min_length=2, max_length=200)
    purpose: str = "attendance_confirmation"
    messages: dict[str, str]
    languages: list[str] = Field(min_length=1)
    scheduled_at: datetime | None = None
    max_attempts: int = Field(default=3, ge=1, le=5)
    require_consent: bool = True

    @field_validator("purpose")
    @classmethod
    def _purpose(cls, v):
        if v not in PURPOSES:
            raise ValueError(f"purpose must be one of {sorted(PURPOSES)}")
        return v

    @field_validator("languages")
    @classmethod
    def _langs(cls, v):
        bad = [x for x in v if x not in SUPPORTED_LANGUAGES]
        if bad or len(set(v)) != len(v):
            raise ValueError(f"languages must be unique and in {sorted(SUPPORTED_LANGUAGES)}")
        return v

    @field_validator("scheduled_at")
    @classmethod
    def _tz(cls, v):
        if v is not None and v.tzinfo is None:
            raise ValueError("scheduled_at must include a timezone offset")
        return v

    @model_validator(mode="after")
    def _messages(self):
        for lang in self.languages:
            if not self.messages.get(lang, "").strip():
                raise ValueError(f"message required for language '{lang}'")
        return self


class CampaignPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    messages: dict[str, str] | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=5)
    scheduled_at: datetime | None = None


class CampaignOut(ORM):
    id: int
    event_id: int
    name: str
    purpose: str
    messages: dict
    languages: list
    status: str
    scheduled_at: datetime | None
    max_attempts: int
    require_consent: bool
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    recipient_count: int = 0


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


class FollowUpOut(ORM):
    id: int
    campaign_id: int
    recipient_id: int
    action_type: str
    status: str
    scheduled_at: datetime | None
    note: str
    created_at: datetime
    completed_at: datetime | None


class QueueItem(BaseModel):
    """A follow-up enriched for the organiser's work queue. `priority` 1 (highest) - 4, rule-based."""
    followup_id: int
    campaign_id: int
    campaign_name: str
    event_id: int
    recipient_id: int
    participant_name: str
    participant_ref: str | None
    reason: str
    action_type: str
    status: str
    priority: int
    priority_reason: str
    latest_outcome: str
    recommended_action: str
    can_clarify: bool = False
    clarification_attempted: bool = False
    scheduled_at: datetime | None
    note: str
    is_simulated: bool
    created_at: datetime


class FollowUpPatch(BaseModel):
    status: str | None = None
    scheduled_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        if v is not None and v not in ("pending", "scheduled", "completed", "cancelled"):
            raise ValueError("invalid status")
        return v

    @field_validator("scheduled_at")
    @classmethod
    def _tz(cls, v):
        if v is not None and v.tzinfo is None:
            raise ValueError("scheduled_at must include a timezone offset")
        return v


LEAD_SOURCES = {"registration_form", "csv_import", "manual", "referral", "walk_in"}
LEAD_STATUSES = ("new", "contacted", "qualified", "converted", "lost")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str
    email: str | None = Field(default=None, max_length=200)
    source: str = "manual"
    interest: str | None = Field(default=None, max_length=100)
    preferred_language: str | None = None
    consent_status: str = "unknown"
    notes: str = Field(default="", max_length=500)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return normalize_phone(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        v = (v or "").strip()
        if not v:
            return None
        if not _EMAIL.match(v):
            raise ValueError("email looks invalid")
        return v.lower()

    @field_validator("source")
    @classmethod
    def _source(cls, v):
        if v not in LEAD_SOURCES:
            raise ValueError(f"source must be one of {sorted(LEAD_SOURCES)}")
        return v

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


class LeadPatch(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=500)
    interest: str | None = Field(default=None, max_length=100)
    consent_status: str | None = None

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        if v is not None and v not in LEAD_STATUSES:
            raise ValueError(f"status must be one of {list(LEAD_STATUSES)}")
        return v

    @field_validator("consent_status")
    @classmethod
    def _c(cls, v):
        if v is not None and v not in ("granted", "unknown", "revoked"):
            raise ValueError("consent_status must be granted|unknown|revoked")
        return v


class LeadOut(ORM):
    id: int
    event_id: int
    name: str
    phone: str
    email: str | None
    source: str
    interest: str | None
    preferred_language: str | None
    consent_status: str
    status: str
    notes: str
    recipient_id: int | None
    is_demo: bool
    created_at: datetime
    score: int = 0
    score_reasons: list[str] = []
    campaign_id: int | None = None
    recipient_outcome: str | None = None


class ConvertIn(BaseModel):
    campaign_id: int
    lead_ids: list[int] = Field(min_length=1, max_length=500)


class DuplicateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    copy_participants: bool = True


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
