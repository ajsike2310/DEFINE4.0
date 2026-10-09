"""Lead schemas."""
import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ..models.enums import LeadSource, LeadStatus, values
from .common import ORM, SUPPORTED_LANGUAGES, normalize_phone

LEAD_SOURCES = set(values(LeadSource))
LEAD_STATUSES = values(LeadStatus)
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
