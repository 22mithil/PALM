"""
CurriculumTopic ORM model.
"""

from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CurriculumTopic(Base):
    __tablename__ = "curriculum_topics"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    subtopic: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    prerequisite_topic_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("curriculum_topics.id"),
        nullable=True,
    )
    difficulty: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Constraints ──────────────────────────────────────────────────
    __table_args__ = (
        CheckConstraint(
            "difficulty BETWEEN 1 AND 5",
            name="ck_curriculum_difficulty",
        ),
    )

    # ── Self-referential relationship ────────────────────────────────
    prerequisite: Mapped[Optional["CurriculumTopic"]] = relationship(
        remote_side=[id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<CurriculumTopic(id={self.id}, grade={self.grade}, "
            f"topic={self.topic!r})>"
        )
