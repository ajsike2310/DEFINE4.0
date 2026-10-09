"""The calling aggregate: campaigns, their participants, call attempts, responses and follow-ups."""
from datetime import datetime

from sqlalchemy import (JSON, Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base, UTCDateTime, utcnow
from ._constraints import PHONE_CHECK, false_default, now_default, one_of
from .enums import (CallMode, CallStatus, CampaignStatus, Consent, EventKind, FollowUpAction, FollowUpStatus, Intent,
                    IntentMethod, Outcome, Purpose)


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        one_of("status", CampaignStatus), one_of("purpose", Purpose),
        CheckConstraint("max_attempts BETWEEN 1 AND 5", name="max_attempts_range"),
        Index("ix_campaigns_event_id_status", "event_id", "status"),          # event pages, overview
        Index("ix_campaigns_status_scheduled_at", "status", "scheduled_at"),  # scheduler: what is due
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(String(50), default="attendance_confirmation",
                                         server_default="attendance_confirmation")
    messages: Mapped[dict] = mapped_column(JSON)          # {"en": "...", "ml": "..."}
    languages: Mapped[list] = mapped_column(JSON)         # first = default
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    require_consent: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false_default())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=now_default())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow,
                                                 server_default=now_default())
    recipients: Mapped[list["Recipient"]] = relationship(back_populates="campaign", cascade="all, delete-orphan",
                                                         passive_deletes=True)


class Recipient(Base):
    __tablename__ = "recipients"
    __table_args__ = (
        UniqueConstraint("campaign_id", "phone", name="uq_recipient_campaign_phone"),     # also serves campaign_id
        one_of("consent_status", Consent), one_of("outcome", Outcome),
        CheckConstraint(PHONE_CHECK, name="phone_e164"),
        # Not a CHECK on purpose: "opted out => outcome opted_out and consent revoked" is enforced in code and audited by
        # the quality page's `optout_wins` integrity check, whose test must be able to plant a violation.
        Index("ix_recipients_campaign_id_outcome", "campaign_id", "outcome"),
        Index("ix_recipients_phone", "phone"),                                              # suppression lookups
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    external_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)  # participant identifier
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(20))        # E.164
    preferred_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    segment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(20), default="unknown", server_default="unknown")
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false_default())
    outcome: Mapped[str] = mapped_column(String(30), default="pending", server_default="pending")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false_default())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=now_default())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow,
                                                 server_default=now_default())
    campaign: Mapped[Campaign] = relationship(back_populates="recipients")
    attempts: Mapped[list["CallAttempt"]] = relationship(back_populates="recipient",
                                                         order_by="CallAttempt.attempt_number",
                                                         cascade="all, delete-orphan", passive_deletes=True)


class CallAttempt(Base):
    __tablename__ = "call_attempts"
    __table_args__ = (
        UniqueConstraint("recipient_id", "attempt_number", name="uq_attempt_number"),     # also serves recipient_id
        one_of("mode", CallMode), one_of("status", CallStatus),
        CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        Index("ix_call_attempts_campaign_id_status", "campaign_id", "status"),
        # A provider's call id identifies exactly one attempt (provider webhooks look attempts up by it).
        Index("uq_call_attempts_provider_call", "provider", "provider_call_id", unique=True,
              sqlite_where=text("provider_call_id IS NOT NULL")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false_default())
    provider_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(10), default="main", server_default="main")   # main | clarify
    call_language: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=now_default())
    recipient: Mapped[Recipient] = relationship(back_populates="attempts")
    intents: Mapped[list["IntentResult"]] = relationship(back_populates="attempt", cascade="all, delete-orphan",
                                                         passive_deletes=True)


class ProviderEvent(Base):
    """Ledger of processed provider events; unique key gives duplicate protection."""
    __tablename__ = "provider_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_provider_event"),
        one_of("kind", EventKind),
        Index("ix_provider_events_call_attempt_id", "call_attempt_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    event_id: Mapped[str] = mapped_column(String(200))
    call_attempt_id: Mapped[int | None] = mapped_column(ForeignKey("call_attempts.id", ondelete="SET NULL"),
                                                        nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(String(100), default="applied", server_default="applied")
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=now_default())


class IntentResult(Base):
    __tablename__ = "intent_results"
    __table_args__ = (
        UniqueConstraint("call_attempt_id", name="uq_intent_results_call_attempt_id"),   # one response per call
        one_of("intent", Intent), one_of("method", IntentMethod),
        CheckConstraint("score BETWEEN 0 AND 1", name="score_range"),
        Index("ix_intent_results_recipient_id_id", "recipient_id", "id"),
        Index("ix_intent_results_campaign_id_intent", "campaign_id", "intent"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    call_attempt_id: Mapped[int] = mapped_column(ForeignKey("call_attempts.id", ondelete="CASCADE"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id", ondelete="CASCADE"))
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    intent: Mapped[str] = mapped_column(String(30))
    score: Mapped[float] = mapped_column(Float)           # internal heuristic, NOT a probability
    method: Mapped[str] = mapped_column(String(10))       # dtmf | rules | none
    detected_language: Mapped[str] = mapped_column(String(10))
    evidence: Mapped[str] = mapped_column(Text, default="", server_default="")  # matched phrases only, no transcript
    notes: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false_default())
    next_action: Mapped[str] = mapped_column(String(30))
    processing_status: Mapped[str] = mapped_column(String(20), default="processed", server_default="processed")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=now_default())
    attempt: Mapped[CallAttempt] = relationship(back_populates="intents")


class FollowUp(Base):
    __tablename__ = "follow_ups"
    __table_args__ = (
        one_of("action_type", FollowUpAction), one_of("status", FollowUpStatus),
        Index("ix_follow_ups_campaign_id_status", "campaign_id", "status"),
        Index("ix_follow_ups_recipient_id_status", "recipient_id", "status"),
        Index("ix_follow_ups_source_intent_id", "source_intent_id"),
        Index("ix_follow_ups_status_scheduled_at", "status", "scheduled_at"),   # the work queue, due callbacks
        # At most one open human-review task per participant.
        Index("uq_follow_ups_open_review", "recipient_id", unique=True,
              sqlite_where=text("action_type = 'human_review' AND status IN ('pending', 'scheduled')")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id", ondelete="CASCADE"))
    source_intent_id: Mapped[int | None] = mapped_column(ForeignKey("intent_results.id", ondelete="SET NULL"),
                                                         nullable=True)
    action_type: Mapped[str] = mapped_column(String(30))  # callback | human_review | send_information | clarification
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=now_default())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow,
                                                 server_default=now_default())
