"""
Mastery routes — student progress retrieval.

GET    /api/v1/mastery/{student_id}     — Get all progress for a student
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.mastery import StudentProgress

router = APIRouter()


@router.get("/{student_id}", summary="Get full progress breakdown by chapter")
async def get_mastery(
    student_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return all progress records for a student, grouped by chapter."""
    result = await db.execute(
        select(StudentProgress)
        .where(StudentProgress.student_id == uuid.UUID(student_id))
    )
    rows = result.scalars().all()
    return [
        {
            "chapter_id": row.chapter_id,
            "current_section_id": row.current_section_id,
            "section_statuses": row.section_statuses,
            "completion_percent": round(row.completion_percent or 0, 1),
            "last_updated": row.last_updated.isoformat() if row.last_updated else None,
        }
        for row in rows
    ]
