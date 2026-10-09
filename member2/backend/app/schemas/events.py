"""Event schemas."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from .common import ORM


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
