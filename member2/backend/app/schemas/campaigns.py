"""Campaign schemas."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator
from .common import ORM, SUPPORTED_LANGUAGES, PURPOSES


class ScheduleIn(BaseModel):
    scheduled_at: datetime


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


class DuplicateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    copy_participants: bool = True
