from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from ..core.db import Base, UTCDateTime, utcnow


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500), default="")
    # Organiser-APPROVED facts only, e.g. {"venue": "...", "schedule": "..."}. Missing key = unknown;
    # the system never invents or infers values.
    approved_info: Mapped[dict] = mapped_column(JSON, default=dict)
    organizer_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(String(50), default="attendance_confirmation")
    messages: Mapped[dict] = mapped_column(JSON)          # {"en": "...", "ml": "..."}
    languages: Mapped[list] = mapped_column(JSON)         # first = default
    status: Mapped[str] = mapped_column(String(20), default="draft")
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    require_consent: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    recipients: Mapped[list["Recipient"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class Recipient(Base):
    __tablename__ = "recipients"
    __table_args__ = (UniqueConstraint("campaign_id", "phone", name="uq_recipient_campaign_phone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    external_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)  # participant identifier
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(20))        # E.164
    preferred_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    segment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(20), default="unknown")  # granted|unknown|revoked
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str] = mapped_column(String(30), default="pending")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    campaign: Mapped[Campaign] = relationship(back_populates="recipients")
    attempts: Mapped[list["CallAttempt"]] = relationship(back_populates="recipient", order_by="CallAttempt.attempt_number")


class CallAttempt(Base):
    __tablename__ = "call_attempts"
    __table_args__ = (UniqueConstraint("recipient_id", "attempt_number", name="uq_attempt_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(10), default="main")   # main | clarify
    call_language: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    recipient: Mapped[Recipient] = relationship(back_populates="attempts")
    intents: Mapped[list["IntentResult"]] = relationship(back_populates="attempt")


class ProviderEvent(Base):
    """Ledger of processed provider events; unique key gives duplicate protection."""
    __tablename__ = "provider_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_provider_event"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    event_id: Mapped[str] = mapped_column(String(200))
    call_attempt_id: Mapped[int | None] = mapped_column(ForeignKey("call_attempts.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(String(100), default="applied")
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class IntentResult(Base):
    __tablename__ = "intent_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_attempt_id: Mapped[int] = mapped_column(ForeignKey("call_attempts.id"), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id"), index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    intent: Mapped[str] = mapped_column(String(30))
    score: Mapped[float] = mapped_column(Float)           # internal heuristic, NOT a probability
    method: Mapped[str] = mapped_column(String(10))       # dtmf | rules | none
    detected_language: Mapped[str] = mapped_column(String(10))
    evidence: Mapped[str] = mapped_column(Text, default="")  # matched phrases only, no full transcript
    notes: Mapped[list] = mapped_column(JSON, default=list)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    next_action: Mapped[str] = mapped_column(String(30))
    processing_status: Mapped[str] = mapped_column(String(20), default="processed")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    attempt: Mapped[CallAttempt] = relationship(back_populates="intents")


class FollowUp(Base):
    __tablename__ = "follow_ups"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id"), index=True)
    source_intent_id: Mapped[int | None] = mapped_column(ForeignKey("intent_results.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(30))  # callback | human_review | send_information | clarification
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|scheduled|completed|cancelled
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Lead(Base):
    """A prospective participant captured for an event BEFORE any call. Only consented, self-supplied or
    organiser-imported contacts belong here; nothing is scraped or bought. Converting a lead creates a Recipient."""
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("event_id", "phone", name="uq_lead_event_phone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(20))        # E.164
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    interest: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(20), default="unknown")   # granted|unknown|revoked
    status: Mapped[str] = mapped_column(String(20), default="new")   # new|contacted|qualified|converted|lost
    notes: Mapped[str] = mapped_column(String(500), default="")
    recipient_id: Mapped[int | None] = mapped_column(ForeignKey("recipients.id"), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ImportRun(Base):
    """One CSV import (participants or leads): how many rows arrived, how many were accepted, and why not."""
    __tablename__ = "import_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))         # participants | leads
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(200), default="")
    rows_total: Mapped[int] = mapped_column(Integer)
    imported: Mapped[int] = mapped_column(Integer)
    rejected: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[dict] = mapped_column(JSON, default=dict)   # {reason: count}
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
