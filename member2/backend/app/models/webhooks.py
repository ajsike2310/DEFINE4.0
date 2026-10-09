"""Received provider callbacks, kept (masked) so integration problems can be diagnosed from real payloads."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base, UTCDateTime, utcnow
from ._constraints import false_default, now_default


class WebhookLog(Base):
    __tablename__ = "webhook_logs"
    __table_args__ = (
        Index("ix_webhook_logs_received_at", "received_at"),              # newest first, retention pruning
        Index("ix_webhook_logs_call_attempt_id", "call_attempt_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    endpoint: Mapped[str] = mapped_column(String(30))                     # status | response
    method: Mapped[str] = mapped_column(String(8))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=now_default())
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    call_attempt_id: Mapped[int | None] = mapped_column(ForeignKey("call_attempts.id", ondelete="SET NULL"), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false_default())
    result: Mapped[str] = mapped_column(String(100), default="", server_default="")     # applied | duplicate | error code ...
    payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))   # masked; never the token
