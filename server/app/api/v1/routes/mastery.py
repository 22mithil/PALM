"""
Mastery routes — student progress retrieval and section reset.

GET    /api/v1/mastery/{student_id}                          — Get all progress
POST   /api/v1/mastery/{student_id}/{chapter_id}/reset-section — Reset a single section for review
"""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.mastery import StudentProgress

router = APIRouter()


class ResetSectionRequest(BaseModel):
    section_id: str


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
            "was_completed": row.was_completed,
            "last_updated": row.last_updated.isoformat() if row.last_updated else None,
        }
        for row in rows
    ]


@router.post(
    "/{student_id}/{chapter_id}/reset-section",
    summary="Reset a single section for review practice",
)
async def reset_section(
    student_id: str,
    chapter_id: int,
    payload: ResetSectionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset one section to not_started and set it as current. Does NOT touch was_completed."""
    result = await db.execute(
        select(StudentProgress).where(
            StudentProgress.student_id == uuid.UUID(student_id),
            StudentProgress.chapter_id == chapter_id,
        )
    )
    progress = result.scalars().first()
    if not progress:
        return {"error": "Progress record not found"}

    # Reset the specific section
    statuses = dict(progress.section_statuses or {})
    if payload.section_id in statuses:
        statuses[payload.section_id] = {"status": "not_started"}
    progress.section_statuses = statuses
    progress.current_section_id = payload.section_id

    # Recompute completion
    if progress.was_completed:
        progress.completion_percent = 100.0
    else:
        total = len(statuses)
        mastered = sum(1 for s in statuses.values() if isinstance(s, dict) and s.get("status") == "mastered")
        progress.completion_percent = round((mastered / total) * 100, 1) if total > 0 else 0.0

    # was_completed stays True — never reset

    await db.commit()
    await db.refresh(progress)

    return {
        "chapter_id": progress.chapter_id,
        "current_section_id": progress.current_section_id,
        "completion_percent": progress.completion_percent,
        "was_completed": progress.was_completed,
    }
