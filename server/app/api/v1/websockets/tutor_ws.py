"""
Tutor WebSocket — /ws/tutor/{session_id}

Receives triggers from the frontend, runs the linear pipeline,
and streams the response back token-by-token.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.db.session import async_session_factory
from app.models.session import StudentSession
from app.models.student import Student
from app.pipeline.runner import run_turn_pipeline
from app.services.session_context import session_context_manager

logger = logging.getLogger(__name__)
router = APIRouter()

_STREAM_TOKEN_DELAY: float = 0.025


async def _send_error(ws: WebSocket, message: str) -> None:
    try:
        await ws.send_json({"type": "error", "payload": {"message": message}})
    except Exception:
        pass


async def _stream_tokens(ws: WebSocket, text: str) -> None:
    words = text.split(" ")
    for idx, word in enumerate(words):
        is_last = idx == len(words) - 1
        token = word if is_last else word + " "
        await ws.send_json({
            "type": "token",
            "payload": {"token": token, "done": False},
        })
        if not is_last:
            await asyncio.sleep(_STREAM_TOKEN_DELAY)
    await ws.send_json({
        "type": "token",
        "payload": {"token": "", "done": True},
    })


@router.websocket("/ws/tutor/{session_id}")
async def tutor_websocket(
    websocket: WebSocket,
    session_id: str,
    grade: int = 5,
    topic: str = "Fractions",
):
    await websocket.accept()
    logger.info(
        "🎓  Tutor WS connected  session=%s  client=%s",
        session_id,
        websocket.client.host if websocket.client else "unknown",
    )

    await session_context_manager.get_or_create(session_id)
    interactions: int = 0

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            if msg_type != "trigger":
                await _send_error(
                    websocket,
                    f"Expected message type 'trigger', got '{msg_type}'",
                )
                continue

            payload = msg.get("payload") or {}
            student_id: str | None = payload.get("student_id")
            query_override: str | None = payload.get("query")

            if not student_id:
                await _send_error(websocket, "student_id is required in trigger payload")
                continue

            interactions += 1
            t_start = time.perf_counter()

            logger.info(
                "🎓  Trigger #%d  session=%s  student=%s  query=%s",
                interactions, session_id, student_id,
                repr((query_override or "<stt>")[:80]),
            )

            # ── Ensure session exists in DB ──────────────────────────
            try:
                async with async_session_factory() as db:
                    from sqlalchemy import select
                    result = await db.execute(
                        select(StudentSession).where(
                            StudentSession.id == uuid.UUID(session_id)
                        )
                    )
                    existing = result.scalars().first()

                    if not existing:
                        # Check student exists
                        student_result = await db.execute(
                            select(Student).where(
                                Student.id == uuid.UUID(student_id)
                            )
                        )
                        student = student_result.scalars().first()

                        if not student:
                            logger.info("Auto-creating placeholder student %s", student_id)
                            student = Student(
                                id=uuid.UUID(student_id),
                                name="Test Student",
                                email=f"test_{student_id[:8]}@palm.local",
                                password_hash="placeholder_no_login",
                                grade=grade,
                                age=10,
                            )
                            db.add(student)
                            await db.flush()

                        # Determine chapter_id from topic or default to 2 (Fractions)
                        from app.models.curriculum import Chapter
                        chapter_result = await db.execute(
                            select(Chapter).where(Chapter.chapter_name == topic)
                        )
                        chapter = chapter_result.scalars().first()
                        chapter_id = chapter.chapter_id if chapter else 2

                        new_session = StudentSession(
                            id=uuid.UUID(session_id),
                            student_id=uuid.UUID(student_id),
                            chapter_id=chapter_id,
                            grade=grade,
                        )
                        db.add(new_session)
                        await db.commit()
                        logger.info("Created session %s for chapter %d", session_id, chapter_id)
            except Exception as exc:
                logger.error("Failed to init DB session: %s", exc, exc_info=True)

            # ── Run pipeline ─────────────────────────────────────────
            student_message = query_override or ""

            # Extract response_time_ms from payload (Issue 4)
            response_time_ms = payload.get("response_time_ms")

            # If no query override, try getting transcript from session context
            if not student_message.strip():
                session_ctx = session_context_manager.get(session_id)
                if session_ctx:
                    student_message = await session_ctx.get_recent_transcript(n=1)

            completion_pct = 0.0
            try:
                async with async_session_factory() as db:
                    full_text = await run_turn_pipeline(
                        student_id=student_id,
                        session_id=session_id,
                        student_message=student_message,
                        db=db,
                        response_time_ms=response_time_ms,
                    )
                    await db.commit()

                    # Fetch updated completion after pipeline
                    from sqlalchemy import select as sa_select
                    from app.models.mastery import StudentProgress
                    from app.models.session import StudentSession as SessModel
                    sess_r = await db.execute(
                        sa_select(SessModel).where(SessModel.id == uuid.UUID(session_id))
                    )
                    sess_obj = sess_r.scalars().first()
                    if sess_obj and sess_obj.chapter_id:
                        prog_r = await db.execute(
                            sa_select(StudentProgress).where(
                                StudentProgress.student_id == uuid.UUID(student_id),
                                StudentProgress.chapter_id == sess_obj.chapter_id,
                            )
                        )
                        prog_obj = prog_r.scalars().first()
                        if prog_obj:
                            completion_pct = prog_obj.completion_percent or 0.0
            except Exception as exc:
                logger.error(
                    "🎓  Pipeline failed  session=%s: %s",
                    session_id, exc, exc_info=True,
                )
                await _send_error(websocket, "Pipeline encountered an error")
                continue

            orchestrator_ms = (time.perf_counter() - t_start) * 1000
            logger.info(
                "🎓  Pipeline done  session=%s  latency=%.0fms  chars=%d",
                session_id, orchestrator_ms, len(full_text),
            )

            # ── Stream tokens ────────────────────────────────────────
            await _stream_tokens(websocket, full_text)

            # ── Send response_complete ───────────────────────────────
            await websocket.send_json({
                "type": "response_complete",
                "payload": {
                    "full_text": full_text,
                    "agent_used": "pipeline",
                    "mastery_delta": 0.0,
                    "completion_percent": completion_pct,
                },
            })

            total_ms = (time.perf_counter() - t_start) * 1000
            logger.info(
                "🎓  Response delivered  session=%s  total=%.0fms",
                session_id, total_ms,
            )

    except WebSocketDisconnect:
        logger.info(
            "🎓  Tutor WS disconnected  session=%s  interactions=%d",
            session_id, interactions,
        )
    except Exception as exc:
        logger.error(
            "🎓  Tutor WS error  session=%s: %s",
            session_id, exc, exc_info=True,
        )
    finally:
        logger.info(
            "🎓  Tutor WS closed  session=%s  total_interactions=%d",
            session_id, interactions,
        )
