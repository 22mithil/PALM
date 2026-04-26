"""
Curriculum routes — chapters and sections.

GET /api/v1/topics?grade=5  — Get all chapters for a grade
GET /api/v1/topics/{chapter_id}/sections — Get sections for a chapter
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.curriculum import Chapter, ChapterSection

router = APIRouter()


@router.get("/", summary="Get chapters for a grade")
async def get_topics(
    grade: int = Query(..., ge=1, le=5, description="Grade level (1-5)"),
    db: AsyncSession = Depends(get_db),
):
    """Return all chapters for the given grade."""
    result = await db.execute(
        select(Chapter)
        .where(Chapter.grade == grade)
        .order_by(Chapter.chapter_id)
    )
    rows = result.scalars().all()
    return [
        {
            "id": row.chapter_id,
            "grade": row.grade,
            "topic": row.chapter_name,
            "subject": row.subject,
            "section_count": len(row.section_ids) if row.section_ids else 0,
        }
        for row in rows
    ]


@router.get("/{chapter_id}/sections", summary="Get sections for a chapter")
async def get_chapter_sections(
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return all sections for a chapter, ordered by position."""
    result = await db.execute(
        select(ChapterSection)
        .where(ChapterSection.chapter_id == chapter_id)
        .order_by(ChapterSection.order)
    )
    rows = result.scalars().all()
    return [
        {
            "section_id": row.section_id,
            "order": row.order,
            "concept": row.concept,
            "title": row.title,
            "difficulty": row.difficulty,
        }
        for row in rows
    ]
