"""
Curriculum routes — placeholder.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/topics", summary="List all topics for a grade")
async def list_topics(grade: int):
    return []


@router.get("/next", summary="Get recommended next topic")
async def next_topic(student_id: str):
    return {"detail": "Not implemented"}
