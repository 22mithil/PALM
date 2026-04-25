"""
Curriculum topics routes.

GET /api/v1/topics?grade=5  — Get all topics for a grade
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.curriculum import CurriculumTopic

router = APIRouter()


@router.get("/", summary="Get topics for a grade")
async def get_topics(
    grade: int = Query(..., ge=1, le=5, description="Grade level (1-5)"),
    db: AsyncSession = Depends(get_db),
):
    """Return all curriculum topics for the given grade, ordered by ID."""
    result = await db.execute(
        select(CurriculumTopic)
        .where(CurriculumTopic.grade == grade)
        .order_by(CurriculumTopic.id)
    )
    rows = result.scalars().all()
    return [
        {
            "id": row.id,
            "grade": row.grade,
            "topic": row.topic,
            "subtopic": row.subtopic,
            "difficulty": row.difficulty,
            "description": row.description,
        }
        for row in rows
    ]
