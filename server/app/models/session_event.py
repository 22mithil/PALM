"""
SessionEvent ORM model.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.session import Session


class SessionEvent(Base):
    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    event_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    emotion_label: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    gaze_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    agent_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    query_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # ── Indexes ──────────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_events_session", "session_id"),
    )

    # ── Relationships ────────────────────────────────────────────────
    session: Mapped["Session"] = relationship(back_populates="events")

    def __repr__(self) -> str:
        return f"<SessionEvent(id={self.id}, type={self.event_type!r})>"
