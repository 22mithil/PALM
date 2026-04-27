"""
StudentProgress ORM model.

Tracks a student's advancement through a chapter:
which section they're on, per-section mastery status,
and overall completion percentage.

Replaces the old ``MasteryScore`` model.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.student import Student


class StudentProgress(Base):
    __tablename__ = "student_progress"

    # ── Composite PK ─────────────────────────────────────────────────
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="CASCADE"),
        primary_key=True,
    )
    chapter_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chapters.chapter_id", ondelete="CASCADE"),
        primary_key=True,
    )

    # ── Progress fields ──────────────────────────────────────────────
    current_section_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    section_statuses: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    completion_percent: Mapped[float] = mapped_column(
        Float,
        server_default=text("0.0"),
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    was_completed: Mapped[bool] = mapped_column(
        server_default=text("false"),
    )

    # ── Relationships ────────────────────────────────────────────────
    student: Mapped["Student"] = relationship(back_populates="progress")

    def __repr__(self) -> str:
        return (
            f"<StudentProgress(student={self.student_id!s}, "
            f"chapter={self.chapter_id}, "
            f"section={self.current_section_id!r})>"
        )
