"""
Session service — DB operations for student learning sessions.

Updated for the new ``student_sessions`` table with JSONB messages
and chapter-based sessions.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import StudentSession

logger = logging.getLogger(__name__)


async def create_session(
    db: AsyncSession,
    student_id: uuid.UUID,
    chapter_id: int,
    grade: int = 5,
    session_id_override: uuid.UUID | None = None,
) -> StudentSession:
    """Create a new learning session."""
    kwargs: dict = dict(
        student_id=student_id,
        chapter_id=chapter_id,
        grade=grade,
    )
    if session_id_override is not None:
        kwargs["id"] = session_id_override

    session = StudentSession(**kwargs)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    logger.info(
        "Created session=%s for student=%s chapter=%d",
        session.id, student_id, chapter_id,
    )
    return session


async def get_session_by_id(db: AsyncSession, session_id: uuid.UUID) -> StudentSession:
    """Fetch a single session by UUID. Raises 404 if not found."""
    result = await db.execute(
        select(StudentSession).where(StudentSession.id == session_id)
    )
    session = result.scalars().first()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return session


async def get_student_sessions(
    db: AsyncSession, student_id: uuid.UUID
) -> list[StudentSession]:
    """Fetch all sessions for a student."""
    result = await db.execute(
        select(StudentSession)
        .where(StudentSession.student_id == student_id)
        .order_by(StudentSession.started_at.desc())
    )
    return list(result.scalars().all())
