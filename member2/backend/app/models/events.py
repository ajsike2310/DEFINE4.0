from datetime import datetime

from sqlalchemy import JSON, Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base, UTCDateTime, utcnow
from ._constraints import false_default, now_default


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500), default="", server_default="")
    # Organiser-APPROVED facts only, e.g. {"venue": "...", "schedule": "..."}. Missing key = unknown;
    # the system never invents or infers values.
    approved_info: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    organizer_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false_default())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, server_default=now_default())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow,
                                                 server_default=now_default())
