"""
Student ORM model.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.mastery import StudentProgress
    from app.models.session import StudentSession


class Student(Base):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    age: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    streak: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=datetime.utcnow,
    )
    last_login_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Constraints ──────────────────────────────────────────────────
    __table_args__ = (
        CheckConstraint("grade BETWEEN 1 AND 5", name="ck_students_grade"),
        UniqueConstraint("email", name="uq_students_email"),
    )

    # ── Relationships ────────────────────────────────────────────────
    sessions: Mapped[list["StudentSession"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    progress: Mapped[list["StudentProgress"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Student(id={self.id!s}, name={self.name!r}, grade={self.grade})>"
