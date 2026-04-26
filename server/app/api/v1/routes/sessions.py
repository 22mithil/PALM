"""
Session API routes.

POST   /api/v1/sessions                       — Start a new learning session
GET    /api/v1/sessions/{id}                  — Get session details
GET    /api/v1/sessions/student/{student_id}  — List all sessions for a student
GET    /api/v1/sessions/{id}/events           — Get chat history (from last_10_messages)
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.session import StudentSession
from app.schemas.session import SessionCreate, SessionResponse
from app.services import session_service

router = APIRouter()


@router.post(
    "/",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new learning session",
)
async def create_session(
    payload: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    session = await session_service.create_session(
        db,
        student_id=payload.student_id,
        chapter_id=payload.chapter_id,
        grade=payload.grade,
    )
    return session


@router.get(
    "/student/{student_id}",
    summary="List all sessions for a student",
)
async def list_student_sessions(
    student_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudentSession)
        .where(StudentSession.student_id == uuid.UUID(student_id))
        .order_by(StudentSession.started_at.desc())
    )
    sessions = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "chapter_id": s.chapter_id,
            "grade": s.grade,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "turn_count": s.turn_count,
            "session_summary": s.session_summary,
        }
        for s in sessions
    ]


@router.get(
    "/{session_id}/events",
    summary="Get chat history for a session",
)
async def get_session_events(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return the last_10_messages JSONB from the session."""
    result = await db.execute(
        select(StudentSession)
        .where(StudentSession.id == uuid.UUID(session_id))
    )
    session = result.scalars().first()
    if session is None:
        return []
    return session.last_10_messages or []


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get session details",
)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    session = await session_service.get_session_by_id(db, session_id)
    return session
