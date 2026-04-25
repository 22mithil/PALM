"""
Session ORM model.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, Integer, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.session_event import SessionEvent
    from app.models.student import Student


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    topic: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_turns: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    performance_result: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mastery_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    # ── Indexes ──────────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_sessions_student", "student_id"),
    )

    # ── Relationships ────────────────────────────────────────────────
    student: Mapped["Student"] = relationship(back_populates="sessions")
    events: Mapped[list["SessionEvent"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Session(id={self.id!s}, topic={self.topic!r})>"
