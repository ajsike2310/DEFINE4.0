"""Lead generation and import bookkeeping."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base, UTCDateTime, utcnow
from ._constraints import PHONE_CHECK, false_default, now_default, one_of
from .enums import Consent, ImportKind, LeadSource, LeadStatus


class Lead(Base):
    """A prospective participant captured for an event BEFORE any call. Only consented, self-supplied or
    organiser-imported contacts belong here; nothing is scraped or bought. Converting a lead creates a Recipient."""
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("event_id", "phone", name="uq_lead_event_phone"),               # also serves event_id
        one_of("source", LeadSource), one_of("status", LeadStatus), one_of("consent_status", Consent),
        CheckConstraint(PHONE_CHECK, name="phone_e164"),
        Index("ix_leads_event_id_status", "event_id", "status"),
        Index("ix_leads_phone", "phone"),                                                 # suppression lookups
        Index("ix_leads_recipient_id", "recipient_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(20))        # E.164
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="manual", server_default="manual")
    interest: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(20), default="unknown", server_default="unknown")
    status: Mapped[str] = mapped_column(String(20), default="new", server_default="new")
    notes: Mapped[str] = mapped_column(String(500), default="", server_default="")
    recipient_id: Mapped[int | None] = mapped_column(ForeignKey("recipients.id", ondelete="SET NULL"), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false_default())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=now_default())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow,
                                                 server_default=now_default())


class ImportRun(Base):
    """One CSV import (participants or leads): how many rows arrived, how many were accepted, and why not."""
    __tablename__ = "import_runs"
    __table_args__ = (
        one_of("kind", ImportKind),
        CheckConstraint("rows_total >= 0 AND imported >= 0 AND rejected >= 0 AND imported + rejected <= rows_total",
                        name="counts_consistent"),
        Index("ix_import_runs_event_id_kind", "event_id", "kind"),
        Index("ix_import_runs_campaign_id", "campaign_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))         # participants | leads
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(200), default="", server_default="")
    rows_total: Mapped[int] = mapped_column(Integer)
    imported: Mapped[int] = mapped_column(Integer)
    rejected: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))   # {reason: count}
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false_default())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=now_default())
