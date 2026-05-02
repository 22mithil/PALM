"""
Migrate to structured DB architecture.

- Drop old tables: mastery_scores, session_events, sessions, curriculum_topics
- Create new tables: chapters, chapter_sections, student_sessions, student_progress
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "bc11f2e73437"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Drop old tables (if they exist) ──────────────────────────────
    op.execute("DROP TABLE IF EXISTS session_events CASCADE")
    op.execute("DROP TABLE IF EXISTS mastery_scores CASCADE")
    op.execute("DROP TABLE IF EXISTS sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS curriculum_topics CASCADE")

    # ── Create chapters ──────────────────────────────────────────────
    op.create_table(
        "chapters",
        sa.Column("chapter_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("chapter_name", sa.String(200), nullable=False),
        sa.Column("grade", sa.SmallInteger(), nullable=False),
        sa.Column("subject", sa.String(100), nullable=False, server_default="Mathematics"),
        sa.Column("section_ids", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("chapter_id"),
        sa.CheckConstraint("grade BETWEEN 1 AND 5", name="ck_chapters_grade"),
    )

    # ── Create chapter_sections ──────────────────────────────────────
    op.create_table(
        "chapter_sections",
        sa.Column("section_id", sa.String(50), nullable=False),
        sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("chapters.chapter_id", ondelete="CASCADE"), nullable=False),
        sa.Column("order", sa.SmallInteger(), nullable=False),
        sa.Column("concept", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="intro"),
        sa.Column("prerequisite_concepts", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("examples", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("common_misconceptions", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("hint_progression", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("quiz_questions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("section_id"),
    )

    # ── Create student_sessions ──────────────────────────────────────
    op.create_table(
        "student_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("chapters.chapter_id", ondelete="SET NULL"), nullable=True),
        sa.Column("grade", sa.SmallInteger(), nullable=False, server_default=sa.text("5")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("turn_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("session_summary", sa.Text(), nullable=True),
        sa.Column("last_10_messages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("asked_questions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Create student_progress ──────────────────────────────────────
    op.create_table(
        "student_progress",
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("chapters.chapter_id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_section_id", sa.String(50), nullable=False),
        sa.Column("section_statuses", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("completion_percent", sa.Float(), server_default=sa.text("0.0")),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("student_id", "chapter_id"),
    )


def downgrade() -> None:
    op.drop_table("student_progress")
    op.drop_table("student_sessions")
    op.drop_table("chapter_sections")
    op.drop_table("chapters")
