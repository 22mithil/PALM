"""
Session API routes.

POST   /api/v1/sessions                       — Start a new learning session
GET    /api/v1/sessions/{id}                  — Get session details
PATCH  /api/v1/sessions/{id}/end              — End and summarize a session
GET    /api/v1/sessions/student/{student_id}  — List all sessions for a student
GET    /api/v1/sessions/{id}/events           — Get chat history for a session
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.session import Session
from app.models.session_event import SessionEvent
from app.schemas.session import SessionCreate, SessionEnd, SessionResponse
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
    """Start a new tutoring session for a student.

    Creates a session row with ``difficulty_level = 1`` (easiest).
    Validates that the referenced student exists.
    """
    session = await session_service.create_session(db, payload)
    return session


@router.get(
    "/student/{student_id}",
    summary="List all sessions for a student",
)
async def list_student_sessions(
    student_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return all sessions for a student, ordered by most recent first.

    Includes topic, timestamps, turn count, and summary.
    Used by the frontend to show session history and enable topic continuation.
    """
    result = await db.execute(
        select(Session)
        .where(Session.student_id == uuid.UUID(student_id))
        .order_by(Session.started_at.desc())
    )
    sessions = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "grade": s.grade,
            "topic": s.topic,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "total_turns": s.total_turns,
            "summary": s.summary,
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
    """Return all events for a session, ordered chronologically.

    Includes dialogue turns (query + response pairs), emotion/gaze events,
    and agent metadata. Used to restore a previous conversation when a
    student resumes a topic.
    """
    result = await db.execute(
        select(SessionEvent)
        .where(SessionEvent.session_id == uuid.UUID(session_id))
        .order_by(SessionEvent.timestamp)
    )
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "query_text": e.query_text,
            "response_text": e.response_text,
            "agent_used": e.agent_used,
            "emotion_label": e.emotion_label,
            "gaze_status": e.gaze_status,
            "is_correct": e.is_correct,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in events
    ]


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get session details",
)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a session by its UUID. Returns 404 if not found."""
    session = await session_service.get_session_by_id(db, session_id)
    return session


@router.patch(
    "/{session_id}/end",
    response_model=SessionResponse,
    summary="End and summarize a session",
)
async def end_session(
    session_id: uuid.UUID,
    payload: Optional[SessionEnd] = Body(None),
    db: AsyncSession = Depends(get_db),
):
    """End an active session.

    Sets ``ended_at`` to the current timestamp and optionally stores
    an LLM-generated session summary. Returns 409 if the session
    has already ended.
    """
    session = await session_service.end_session(db, session_id, payload)
    return session
