"""
Session Event Logger — Async, throttled event pipeline.

Persists meaningful perception changes to the ``session_events`` table
using async SQLAlchemy.  Designed to be called *after* the
:class:`ChangeDetector` confirms a meaningful delta.

Key properties
~~~~~~~~~~~~~~
* **Non-blocking**: writes are dispatched as fire-and-forget
  ``asyncio.Task``s — callers never wait for DB I/O.
* **Throttled**: at most one event per ``event_type`` per second per
  session, eliminating duplicate spam from noisy perception streams.
* **Safe**: DB errors are logged but never propagate to the caller.

Usage::

    from app.services.event_logger import event_logger

    await event_logger.log_emotion(session_id, "happy", "on_screen")
    await event_logger.log_gaze(session_id, "off_screen")
    await event_logger.log_query(session_id, "What is photosynthesis?")
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.session import Session
from app.models.session_event import SessionEvent

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────

_THROTTLE_INTERVAL: float = 1.0  # seconds — max 1 event/sec per type per session


# ── Logger ───────────────────────────────────────────────────────────────


class EventLogger:
    """Async, throttled session-event writer.

    Maintains a per-(session, event_type) timestamp map for throttling.
    All DB writes run in detached background tasks so the caller's
    hot path (WebSocket loop) is never blocked.
    """

    def __init__(self, throttle_interval: float = _THROTTLE_INTERVAL) -> None:
        self._throttle_interval = throttle_interval

        # (session_id, event_type) → last-emitted epoch
        self._last_emitted: dict[tuple[str, str], float] = {}

    # ── Public API ───────────────────────────────────────────────────

    async def log_emotion(
        self,
        session_id: str,
        emotion_label: str,
        gaze_status: str = "",
    ) -> None:
        """Log an emotion_event (fire-and-forget, throttled)."""
        if not self._should_emit(session_id, "emotion_event"):
            return

        self._dispatch(
            session_id=session_id,
            event_type="emotion_event",
            emotion_label=emotion_label,
            gaze_status=gaze_status,
        )

    async def log_gaze(
        self,
        session_id: str,
        gaze_status: str,
        emotion_label: str = "",
    ) -> None:
        """Log a gaze_event (fire-and-forget, throttled)."""
        if not self._should_emit(session_id, "gaze_event"):
            return

        self._dispatch(
            session_id=session_id,
            event_type="gaze_event",
            gaze_status=gaze_status,
            emotion_label=emotion_label,
        )

    async def log_query(
        self,
        session_id: str,
        query_text: str,
    ) -> None:
        """Log a student_query event (fire-and-forget, throttled)."""
        if not query_text or not query_text.strip():
            return

        if not self._should_emit(session_id, "student_query"):
            return

        self._dispatch(
            session_id=session_id,
            event_type="student_query",
            query_text=query_text.strip(),
        )

    async def log_response(
        self,
        session_id: str,
        query_text: str,
        response_text: str,
        agent_used: str = "",
    ) -> None:
        """Log a complete dialogue turn (query + response).

        Not throttled — every interaction should be persisted for
        chat history / session continuation.
        """
        self._dispatch(
            session_id=session_id,
            event_type="dialogue_turn",
            query_text=query_text.strip() if query_text else "",
            response_text=response_text,
            agent_used=agent_used,
        )

    # ── Throttle ─────────────────────────────────────────────────────

    def _should_emit(self, session_id: str, event_type: str) -> bool:
        """Return ``True`` if enough time has elapsed since the last emit."""
        key = (session_id, event_type)
        now = time.monotonic()
        last = self._last_emitted.get(key, 0.0)

        if (now - last) < self._throttle_interval:
            return False

        self._last_emitted[key] = now
        return True

    # ── Background dispatch ──────────────────────────────────────────

    def _dispatch(
        self,
        session_id: str,
        event_type: str,
        emotion_label: str = "",
        gaze_status: str = "",
        query_text: str = "",
        response_text: str = "",
        agent_used: str = "",
    ) -> None:
        """Create a fire-and-forget background task for the DB write."""
        asyncio.create_task(
            self._write(
                session_id=session_id,
                event_type=event_type,
                emotion_label=emotion_label or None,
                gaze_status=gaze_status or None,
                query_text=query_text or None,
                response_text=response_text or None,
                agent_used=agent_used or None,
            ),
            name=f"event-log-{session_id}-{event_type}",
        )

    async def _write(
        self,
        session_id: str,
        event_type: str,
        emotion_label: Optional[str],
        gaze_status: Optional[str],
        query_text: Optional[str],
        response_text: Optional[str] = None,
        agent_used: Optional[str] = None,
    ) -> None:
        """Persist a single event row.  Errors are swallowed to avoid
        crashing the caller's task tree."""
        try:
            uuid.UUID(session_id)
        except ValueError:
            logger.error(
                "Invalid UUID '%s' provided for session_event insert. Aborting.",
                session_id,
            )
            return

        try:
            async with async_session_factory() as session:
                # Guard: skip if the session row hasn't been created yet
                # (video/audio WS may fire events before tutor WS persists it)
                exists = await session.execute(
                    select(Session.id).where(
                        Session.id == uuid.UUID(session_id)
                    )
                )
                if exists.scalar_one_or_none() is None:
                    logger.debug(
                        "Session %s not yet in DB — skipping %s event",
                        session_id,
                        event_type,
                    )
                    return

                event = SessionEvent(
                    session_id=session_id,
                    event_type=event_type,
                    emotion_label=emotion_label,
                    gaze_status=gaze_status,
                    query_text=query_text,
                    response_text=response_text,
                    agent_used=agent_used,
                )
                session.add(event)
                await session.commit()

                logger.debug(
                    "Logged %s  session=%s  emotion=%s  gaze=%s  agent=%s",
                    event_type,
                    session_id,
                    emotion_label,
                    gaze_status,
                    agent_used,
                )
        except Exception as exc:
            logger.error(
                "Failed to log %s  session=%s: %s",
                event_type,
                session_id,
                exc,
                exc_info=True,
            )

    # ── Housekeeping ─────────────────────────────────────────────────

    def clear_session(self, session_id: str) -> None:
        """Remove throttle state for a disconnected session."""
        keys_to_remove = [
            k for k in self._last_emitted if k[0] == session_id
        ]
        for k in keys_to_remove:
            del self._last_emitted[k]

    def clear_all(self) -> None:
        """Reset all throttle state."""
        self._last_emitted.clear()


# ── Singleton ────────────────────────────────────────────────────────────

event_logger = EventLogger()
