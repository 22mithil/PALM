"""
Curriculum ORM models — Chapter + ChapterSection.

Replaces the old ``CurriculumTopic`` with a structured two-table
schema that stores full pedagogical content per section.
"""

from typing import Optional

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Chapter(Base):
    __tablename__ = "chapters"

    chapter_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=False,  # manually assigned from seed data
    )
    chapter_name: Mapped[str] = mapped_column(String(200), nullable=False)
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False, server_default="Mathematics")
    section_ids: Mapped[list] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default="{}",
    )

    # ── Constraints ──────────────────────────────────────────────────
    __table_args__ = (
        CheckConstraint("grade BETWEEN 1 AND 5", name="ck_chapters_grade"),
    )

    # ── Relationships ────────────────────────────────────────────────
    sections: Mapped[list["ChapterSection"]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ChapterSection.order",
    )

    def __repr__(self) -> str:
        return f"<Chapter(id={self.chapter_id}, name={self.chapter_name!r})>"


class ChapterSection(Base):
    __tablename__ = "chapter_sections"

    section_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )
    chapter_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chapters.chapter_id", ondelete="CASCADE"),
        nullable=False,
    )
    order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    concept: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    difficulty: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="intro"
    )
    prerequisite_concepts: Mapped[list] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default="{}",
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    examples: Mapped[list] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    common_misconceptions: Mapped[list] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    hint_progression: Mapped[list] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    quiz_questions: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )

    # ── Relationships ────────────────────────────────────────────────
    chapter: Mapped["Chapter"] = relationship(back_populates="sections")

    def __repr__(self) -> str:
        return (
            f"<ChapterSection(id={self.section_id!r}, "
            f"title={self.title!r})>"
        )
