"""
Mastery service — DB operations for student progress.

Updated to work with the ``student_progress`` table instead of
the old ``mastery_scores`` table.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mastery import StudentProgress

logger = logging.getLogger(__name__)


async def get_progress(
    db: AsyncSession,
    student_id: uuid.UUID,
    chapter_id: int,
) -> StudentProgress | None:
    """Fetch progress for a student + chapter."""
    result = await db.execute(
        select(StudentProgress).where(
            StudentProgress.student_id == student_id,
            StudentProgress.chapter_id == chapter_id,
        )
    )
    return result.scalars().first()


async def get_all_progress(
    db: AsyncSession,
    student_id: uuid.UUID,
) -> list[StudentProgress]:
    """Fetch all progress records for a student."""
    result = await db.execute(
        select(StudentProgress).where(
            StudentProgress.student_id == student_id,
        )
    )
    return list(result.scalars().all())


async def upsert_progress(
    db: AsyncSession,
    student_id: uuid.UUID,
    chapter_id: int,
    current_section_id: str,
    section_statuses: dict,
    completion_percent: float = 0.0,
) -> StudentProgress:
    """Create or update a progress record."""
    existing = await get_progress(db, student_id, chapter_id)

    if existing:
        existing.current_section_id = current_section_id
        existing.section_statuses = section_statuses
        existing.completion_percent = completion_percent
        existing.last_updated = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(existing)
        return existing

    row = StudentProgress(
        student_id=student_id,
        chapter_id=chapter_id,
        current_section_id=current_section_id,
        section_statuses=section_statuses,
        completion_percent=completion_percent,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row
