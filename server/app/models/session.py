"""
StudentSession ORM model.

Replaces the old ``Session`` model. Key changes:
- References ``chapter_id`` instead of ``topic``
- Stores ``last_10_messages`` as JSONB instead of separate events table
- Stores ``asked_questions`` as JSONB for quiz tracking
- ``session_summary`` replaces ``summary``
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional


from sqlalchemy import Boolean, Float, ForeignKey, Integer, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.student import Student


class StudentSession(Base):
    __tablename__ = "student_sessions"

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
    chapter_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chapters.chapter_id", ondelete="SET NULL"),
        nullable=True,
    )
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("5"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    turn_count: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
    )
    session_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_10_messages: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    all_messages: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    asked_questions: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # ── Relationships ────────────────────────────────────────────────
    student: Mapped["Student"] = relationship(back_populates="sessions")

    def __repr__(self) -> str:
        return f"<StudentSession(id={self.id!s}, chapter={self.chapter_id})>"
