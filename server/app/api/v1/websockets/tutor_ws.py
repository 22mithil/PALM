"""
Tutor WebSocket — /ws/tutor/{session_id}

Main tutoring pipeline endpoint.  Receives a trigger (from UI text
input or an STT-generated transcript), builds a ``StatePrompt``,
passes it through the LangGraph Orchestrator, and **streams** the
response back token-by-token over the WebSocket.

Wire Protocol
~~~~~~~~~~~~~

Client → Server (trigger)::

    {
      "type": "trigger",
      "payload": {
        "student_id": "uuid-string",       // required
        "query": "optional text override"  // omit to use latest STT
      }
    }

Server → Client (streaming tokens)::

    {
      "type": "token",
      "payload": { "token": "word ", "done": false }
    }

Server → Client (stream finished)::

    {
      "type": "token",
      "payload": { "token": "", "done": true }
    }

Server → Client (final summary)::

    {
      "type": "response_complete",
      "payload": {
        "full_text": "...",
        "agent_used": "hint_agent",
        "mastery_delta": 0.05
      }
    }

Server → Client (error)::

    {
      "type": "error",
      "payload": { "message": "..." }
    }

Streaming strategy
~~~~~~~~~~~~~~~~~~
The Orchestrator pipeline (router → agent node(s)) runs to completion
first, producing the full response text.  Tokens are then streamed
word-by-word with a small inter-token delay to provide a natural
typing feel.  This avoids modifying the existing agent architecture
while delivering a streaming UX.

For true LLM-level token streaming in the future, agents can expose
a ``stream()`` method that yields from ``stream_response()`` and the
executor can be swapped to ``compiled_graph.astream_events()``.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.db.session import async_session_factory
from app.schemas.session import SessionCreate
from app.services.session_service import create_session, get_session_by_id
from app.services.student_service import get_student_by_id
from app.models.student import Student
from app.orchestrator import run_orchestrator
from app.state.context_manager import context_aggregator
from app.state.state_prompt_builder import build_state_prompt_from_session

logger = logging.getLogger(__name__)
router = APIRouter()

# Inter-token delay for word-level streaming (seconds)
_STREAM_TOKEN_DELAY: float = 0.025


# ── Helpers ──────────────────────────────────────────────────────────────


async def _send_error(ws: WebSocket, message: str) -> None:
    """Send a typed error frame (best-effort, swallows send failures)."""
    try:
        await ws.send_json({
            "type": "error",
            "payload": {"message": message},
        })
    except Exception:
        pass


async def _stream_tokens(ws: WebSocket, text: str) -> None:
    """Stream *text* to the client word-by-word.

    Each word is sent as a ``token`` frame with ``done=false``.
    After the last word a sentinel frame with ``done=true`` is sent.
    """
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

    # Done sentinel
    await ws.send_json({
        "type": "token",
        "payload": {"token": "", "done": True},
    })


async def _compute_mastery_delta(
    student_id: str,
    session_id: str,
    old_mastery: float,
) -> float:
    """Re-fetch mastery after orchestration to compute the delta.

    Returns 0.0 on any failure so the pipeline is never blocked.
    """
    try:
        async with async_session_factory() as db:
            post_prompt = await build_state_prompt_from_session(
                student_id=student_id,
                session_id=session_id,
                db=db,
            )
            return round(post_prompt.mastery_score - old_mastery, 4)
    except Exception:
        logger.debug(
            "Mastery delta computation skipped  session=%s", session_id
        )
        return 0.0


# ── WebSocket Endpoint ───────────────────────────────────────────────────


@router.websocket("/ws/tutor/{session_id}")
async def tutor_websocket(
    websocket: WebSocket,
    session_id: str,
    grade: int = 5,
    topic: str = "Fractions",
):
    """Accept a WebSocket, listen for triggers, and stream tutor responses.

    The connection stays open for the lifetime of the tutoring session.
    Each ``trigger`` message kicks off one orchestrator cycle whose
    response is streamed back incrementally.
    """
    await websocket.accept()
    logger.info(
        "🎓  Tutor WS connected  session=%s  client=%s",
        session_id,
        websocket.client.host if websocket.client else "unknown",
    )

    interactions: int = 0

    try:
        while True:
            # ── 1. Receive trigger ─────────────────────────────────
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
                await _send_error(
                    websocket, "student_id is required in trigger payload"
                )
                continue

            interactions += 1
            t_start = time.perf_counter()

            logger.info(
                "🎓  Trigger #%d  session=%s  student=%s  query=%s",
                interactions,
                session_id,
                student_id,
                repr((query_override or "<stt>")[:80]),
            )

            # ── 1.5. Ensure session is persisted to DB ─────────────────
            try:
                async with async_session_factory() as db:
                    try:
                        await get_session_by_id(db, uuid.UUID(session_id))
                    except HTTPException as exc:
                        if exc.status_code == 404:
                            try:
                                await get_student_by_id(db, uuid.UUID(student_id))
                            except HTTPException as student_exc:
                                if student_exc.status_code == 404:
                                    logger.info(f"Auto-creating placeholder student {student_id}")
                                    dummy_student = Student(
                                        id=uuid.UUID(student_id),
                                        name="Test Student",
                                        grade=grade,
                                        age=10,
                                    )
                                    db.add(dummy_student)
                                    await db.flush()
                                else:
                                    raise
                            await create_session(
                                db,
                                SessionCreate(
                                    student_id=uuid.UUID(student_id),
                                    grade=grade,
                                    topic=topic,
                                ),
                                session_id_override=uuid.UUID(session_id),
                            )
                        else:
                            raise
            except Exception as exc:
                logger.error(
                    "🎓  Failed to initialize DB session  session=%s: %s",
                    session_id,
                    exc,
                )

            # ── 2. Build StatePrompt ───────────────────────────────
            try:
                async with async_session_factory() as db:
                    state_prompt = await build_state_prompt_from_session(
                        student_id=student_id,
                        session_id=session_id,
                        db=db,
                    )
            except Exception as exc:
                logger.error(
                    "🎓  StatePrompt build failed  session=%s: %s",
                    session_id,
                    exc,
                    exc_info=True,
                )
                await _send_error(websocket, "Failed to build session context")
                continue

            # Apply query override (UI text input) if present
            if query_override:
                state_prompt = state_prompt.model_copy(
                    update={"query": query_override}
                )

            old_mastery = state_prompt.mastery_score

            # ── 3. Pass to Orchestrator ────────────────────────────
            try:
                result = await run_orchestrator(state_prompt)
            except Exception as exc:
                logger.error(
                    "🎓  Orchestrator failed  session=%s: %s",
                    session_id,
                    exc,
                    exc_info=True,
                )
                await _send_error(
                    websocket, "Orchestrator encountered an error"
                )
                continue

            orchestrator_ms = (time.perf_counter() - t_start) * 1000
            full_text = result.final_response

            logger.info(
                "🎓  Orchestrator done  session=%s  route=%s  agent=%s  "
                "latency=%.0fms  chars=%d",
                session_id,
                result.route,
                result.agent_used,
                orchestrator_ms,
                len(full_text),
            )

            # ── 4. Stream LLM response tokens ─────────────────────
            await _stream_tokens(websocket, full_text)

            # ── 5. Compute mastery delta ───────────────────────────
            mastery_delta = await _compute_mastery_delta(
                student_id, session_id, old_mastery
            )

            # ── 6. Send response_complete ──────────────────────────
            await websocket.send_json({
                "type": "response_complete",
                "payload": {
                    "full_text": full_text,
                    "agent_used": result.agent_used,
                    "mastery_delta": mastery_delta,
                },
            })

            # ── 7. Push response into context history ──────────────
            await context_aggregator.push_response(session_id, full_text)

            # ── 8. Log dialogue turn for chat history ──────────────
            await event_logger.log_response(
                session_id=session_id,
                query_text=query_override or state_prompt.query,
                response_text=full_text,
                agent_used=result.agent_used,
            )

            total_ms = (time.perf_counter() - t_start) * 1000
            logger.info(
                "🎓  Response delivered  session=%s  agent=%s  "
                "total=%.0fms  mastery_delta=%.4f",
                session_id,
                result.agent_used,
                total_ms,
                mastery_delta,
            )

    except WebSocketDisconnect:
        logger.info(
            "🎓  Tutor WS disconnected  session=%s  interactions=%d",
            session_id,
            interactions,
        )
    except Exception as exc:
        logger.error(
            "🎓  Tutor WS error  session=%s: %s",
            session_id,
            exc,
            exc_info=True,
        )
    finally:
        logger.info(
            "🎓  Tutor WS closed  session=%s  total_interactions=%d",
            session_id,
            interactions,
        )
