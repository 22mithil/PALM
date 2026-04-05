"""
Session service layer — all DB operations for learning sessions.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.schemas.session import SessionCreate, SessionEnd
from app.services.student_service import get_student_by_id


async def create_session(db: AsyncSession, payload: SessionCreate) -> Session:
    """Start a new learning session.

    Validates that the student exists, then creates a session row
    with difficulty_level = 1 (easiest).
    """
    # Verify student exists (raises 404 if not)
    await get_student_by_id(db, payload.student_id)

    session = Session(
        student_id=payload.student_id,
        grade=payload.grade,
        topic=payload.topic,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def get_session_by_id(db: AsyncSession, session_id: uuid.UUID) -> Session:
    """Fetch a single session by UUID. Raises 404 if not found."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalars().first()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return session


async def end_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    payload: SessionEnd | None = None,
) -> Session:
    """End an active session.

    Sets ``ended_at`` to now and optionally stores an LLM-generated summary.
    """
    session = await get_session_by_id(db, session_id)

    if session.ended_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session has already ended",
        )

    session.ended_at = datetime.now(timezone.utc)
    session.summary = (
        payload.summary
        if payload and payload.summary
        else f"Session on {session.topic or 'general'} ended."
    )

    await db.flush()
    await db.refresh(session)
    return session
