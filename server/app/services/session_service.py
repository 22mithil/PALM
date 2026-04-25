"""
Session service layer — all DB operations for learning sessions.

Key design decisions:
  • **One session per topic per student.**  ``create_session`` first looks for
    an existing session with the same ``(student_id, topic)``.  If found it
    clears ``ended_at`` so the student can resume, and returns it.
  • **Accumulative duration.**  ``end_session`` *adds* the new
    ``duration_seconds`` to the running total rather than overwriting.
  • **Pausable sessions.**  ``end_session`` no longer raises 409 when the
    session was already ended — it simply re-stamps ``ended_at`` and
    accumulates the latest metrics.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.integrations.fastrouter.llm import generate_response
from app.models.session import Session
from app.models.session_event import SessionEvent
from app.schemas.session import SessionCreate, SessionEnd
from app.services.student_service import get_student_by_id

logger = logging.getLogger(__name__)


async def create_session(
    db: AsyncSession,
    payload: SessionCreate,
    session_id_override: uuid.UUID | None = None,
) -> Session:
    """Start or resume a learning session.

    If a session already exists for the same ``(student_id, topic)``, it is
    resumed: ``ended_at`` is cleared so the student picks up where they
    left off.  Otherwise a brand-new session row is created.

    Parameters
    ----------
    session_id_override:
        If provided, the session row is created with this specific UUID
        instead of relying on the DB default.  Used by the WebSocket
        handler so the session_id from the URL matches the DB row.
    """
    # Verify student exists (raises 404 if not)
    await get_student_by_id(db, payload.student_id)

    # ── Check for an existing session on this topic ──────────────────
    if payload.topic:
        result = await db.execute(
            select(Session)
            .where(
                Session.student_id == payload.student_id,
                Session.topic == payload.topic,
            )
            .order_by(Session.started_at.desc())
            .limit(1)
        )
        existing = result.scalars().first()

        if existing is not None:
            # Resume: clear ended_at so it's treated as active again
            if existing.ended_at is not None:
                existing.ended_at = None
                await db.flush()
                await db.refresh(existing)
            logger.info(
                "Resuming existing session=%s for student=%s topic=%s",
                existing.id, payload.student_id, payload.topic,
            )
            return existing

    # ── No existing session — create a new one ───────────────────────
    kwargs: dict = dict(
        student_id=payload.student_id,
        grade=payload.grade,
        topic=payload.topic,
    )
    if session_id_override is not None:
        kwargs["id"] = session_id_override

    session = Session(**kwargs)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    logger.info(
        "Created new session=%s for student=%s topic=%s",
        session.id, payload.student_id, payload.topic,
    )
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


async def _generate_session_summary_task(session_id: uuid.UUID):
    """Background task to generate a session summary via LLM."""
    async with async_session_factory() as db:
        try:
            # 1. Fetch chat events
            result = await db.execute(
                select(SessionEvent)
                .where(SessionEvent.session_id == session_id)
                .order_by(SessionEvent.timestamp)
            )
            events = result.scalars().all()
            
            chat_history = ""
            for e in events:
                if e.query_text: chat_history += f"Student: {e.query_text}\n"
                if e.response_text: chat_history += f"Tutor: {e.response_text}\n"
                
            # 2. Generate summary
            if not chat_history.strip():
                summary = "No chat messages recorded during this session."
            else:
                prompt = (
                    "Summarize the following tutoring session in 2-3 sentences. "
                    "Focus strictly on what the student learned and any struggles they had.\n\n"
                    f"{chat_history}"
                )
                summary = await generate_response(prompt)
                
            # 3. Save to DB
            session_result = await db.execute(select(Session).where(Session.id == session_id))
            session = session_result.scalars().first()
            if session:
                session.summary = summary
                await db.commit()
                logger.info("Generated summary for session %s", session_id)
        except Exception as e:
            logger.error("Failed to generate session summary for %s: %s", session_id, e)


async def end_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    payload: SessionEnd | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> Session:
    """Pause / end an active session.

    • Sets ``ended_at`` to now.
    • **Accumulates** ``duration_seconds`` so multiple visits sum up.
    • Saves the latest ``mastery_score`` and ``performance_result``.
    • Does **not** raise 409 if the session was already ended — the user
      can pause and resume freely.
    """
    session = await get_session_by_id(db, session_id)

    session.ended_at = datetime.now(timezone.utc)

    # Set placeholder summary while generating
    session.summary = "Loading summary..."

    if payload:
        # Accumulate duration
        if payload.duration_seconds is not None:
            session.duration_seconds = (
                (session.duration_seconds or 0) + payload.duration_seconds
            )

        # Save latest mastery score
        if payload.mastery_score is not None:
            session.mastery_score = payload.mastery_score

        # Save performance result
        if payload.performance_result is not None:
            session.performance_result = payload.performance_result

    await db.flush()
    await db.refresh(session)
    logger.info(
        "Ended session=%s  duration=%s  mastery=%s",
        session.id, session.duration_seconds, session.mastery_score,
    )
    
    # Trigger background summary generation
    if background_tasks:
        background_tasks.add_task(_generate_session_summary_task, session_id)
        
    return session
