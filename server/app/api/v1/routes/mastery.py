"""
Mastery routes — student mastery score retrieval.

GET    /api/v1/mastery/{student_id}     — Get all mastery scores for a student
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.mastery import MasteryScore

router = APIRouter()


@router.get("/{student_id}", summary="Get full mastery breakdown by topic")
async def get_mastery(
    student_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return all mastery scores for a student, grouped by topic.

    Returns a list of objects with topic, grade, score (0.0–1.0),
    attempt count, and last update timestamp.
    """
    result = await db.execute(
        select(MasteryScore)
        .where(MasteryScore.student_id == uuid.UUID(student_id))
        .order_by(MasteryScore.grade, MasteryScore.topic)
    )
    rows = result.scalars().all()
    return [
        {
            "topic": row.topic,
            "grade": row.grade,
            "score": round(row.score, 3),
            "attempts": row.attempts,
            "last_updated": row.last_updated.isoformat() if row.last_updated else None,
        }
        for row in rows
    ]
