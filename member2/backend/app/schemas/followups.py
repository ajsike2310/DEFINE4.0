"""Follow-up and queue schemas."""
from datetime import datetime

from pydantic import BaseModel, field_validator
from .common import ORM


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
