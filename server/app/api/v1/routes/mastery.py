"""
Mastery routes — placeholder.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/{student_id}", summary="Get full mastery breakdown by topic")
async def get_mastery(student_id: str):
    return []


@router.post("/{student_id}/update", summary="Update mastery score after interaction")
async def update_mastery(student_id: str):
    return {"detail": "Not implemented"}
