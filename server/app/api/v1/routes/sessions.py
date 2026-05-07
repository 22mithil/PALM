"""
Session API routes.

POST   /api/v1/sessions                       — Start a new learning session
GET    /api/v1/sessions/{id}                  — Get session details
GET    /api/v1/sessions/student/{student_id}  — List all sessions for a student
GET    /api/v1/sessions/{id}/events           — Get chat history (paginated from all_messages)
PATCH  /api/v1/sessions/{id}/end              — End a session and record duration
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.session import StudentSession
from app.schemas.session import SessionCreate, SessionResponse
from app.services import session_service

router = APIRouter()
logger = logging.getLogger(__name__)


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
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "turn_count": s.turn_count,
            "duration_seconds": s.duration_seconds,
            "session_summary": s.session_summary,
            "message_count": len(s.all_messages) if s.all_messages else 0,
        }
        for s in sessions
    ]


@router.get(
    "/{session_id}/events",
    summary="Get chat history for a session (paginated)",
)
async def get_session_events(
    session_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return paginated messages from all_messages, falling back to last_10_messages."""
    result = await db.execute(
        select(StudentSession)
        .where(StudentSession.id == uuid.UUID(session_id))
    )
    session = result.scalars().first()
    if session is None:
        return {"total": 0, "messages": []}

    all_msgs = session.all_messages or session.last_10_messages or []
    total = len(all_msgs)
    # Return slice from offset
    sliced = all_msgs[offset:offset + limit]
    return {"total": total, "messages": sliced}


@router.patch(
    "/{session_id}/end",
    summary="End a session and record duration",
)
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Set ended_at and compute duration_seconds."""
    result = await db.execute(
        select(StudentSession)
        .where(StudentSession.id == uuid.UUID(session_id))
    )
    session = result.scalars().first()
    if session is None:
        return {"error": "Session not found"}

    now = datetime.now(timezone.utc)
    session.ended_at = now
    if session.started_at:
        delta = now - session.started_at.replace(tzinfo=timezone.utc) if session.started_at.tzinfo is None else now - session.started_at
        session.duration_seconds = int(delta.total_seconds())
    else:
        session.duration_seconds = 0

    await db.commit()
    await db.refresh(session)

    # ── Trigger evaluation analysis ──────────────────────────────
    try:
        from app.evaluation.session_analyzer import analyze_session
        eval_metrics = analyze_session(session_id, session_type="live")
        logger.info("Session evaluation complete: %s", eval_metrics.get("report_path", "N/A"))
    except Exception:
        logger.debug("Session evaluation failed (non-critical)", exc_info=True)

    return {
        "id": str(session.id),
        "ended_at": session.ended_at.isoformat(),
        "duration_seconds": session.duration_seconds,
    }


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
