"""
MasteryScore ORM model.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.student import Student


class MasteryScore(Base):
    __tablename__ = "mastery_scores"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    subtopic: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    score: Mapped[float] = mapped_column(Float, server_default=text("0.0"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )

    # ── Constraints & Indexes ────────────────────────────────────────
    __table_args__ = (
        CheckConstraint("score BETWEEN 0.0 AND 1.0", name="ck_mastery_score_range"),
        UniqueConstraint(
            "student_id", "grade", "topic", "subtopic",
            name="uq_mastery_student_topic",
        ),
        Index("idx_mastery_student", "student_id", "grade", "topic"),
    )

    # ── Relationships ────────────────────────────────────────────────
    student: Mapped["Student"] = relationship(back_populates="mastery_scores")

    def __repr__(self) -> str:
        return (
            f"<MasteryScore(student={self.student_id!s}, "
            f"topic={self.topic!r}, score={self.score})>"
        )
